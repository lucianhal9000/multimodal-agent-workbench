import io
import re
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from PIL import Image
from pypdf import PdfReader

from ..config import Settings
from ..models import ExtractedDocument


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
PDF_EXTENSIONS = {".pdf"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS | AUDIO_EXTENSIONS


class UnsupportedFileError(ValueError):
    pass


@dataclass(frozen=True)
class StoredUpload:
    filename: str
    content_type: str
    path: Path


def classify_file(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in PDF_EXTENSIONS:
        return "pdf"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    raise UnsupportedFileError(
        f"'{filename}' is not supported. Upload a JPG, PNG, PDF, MP3, WAV, or M4A file."
    )


def clean_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", value)).strip()


class IngestionService:
    """Extracts text from every accepted modality with useful partial failures."""

    def __init__(self, settings: Settings, openai_client: object | None = None):
        self.settings = settings
        self.openai_client = openai_client

    async def store_upload(self, upload: UploadFile, request_dir: Path) -> StoredUpload:
        filename = Path(upload.filename or "upload").name
        classify_file(filename)
        destination = request_dir / f"{uuid.uuid4().hex}_{filename}"
        total = 0
        with destination.open("wb") as target:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > self.settings.max_upload_bytes:
                    target.close()
                    destination.unlink(missing_ok=True)
                    raise ValueError(
                        f"'{filename}' exceeds the {self.settings.max_upload_mb} MB upload limit."
                    )
                target.write(chunk)
        return StoredUpload(
            filename=filename,
            content_type=upload.content_type or "application/octet-stream",
            path=destination,
        )

    def extract(self, upload: StoredUpload) -> ExtractedDocument:
        kind = classify_file(upload.filename)
        if kind == "image":
            return self._extract_image(upload)
        if kind == "pdf":
            return self._extract_pdf(upload)
        return self._extract_audio(upload)

    def _extract_image(self, upload: StoredUpload) -> ExtractedDocument:
        warnings: list[str] = []
        try:
            import pytesseract

            image = Image.open(upload.path)
            result = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT, config="--psm 6"
            )
            tokens = [token for token in result["text"] if token.strip()]
            scores = [
                float(score)
                for score in result["conf"]
                if str(score).strip() not in {"", "-1"}
            ]
            confidence = round(sum(scores) / len(scores) / 100, 2) if scores else None
            text = clean_text(" ".join(tokens))
            if not text:
                warnings.append("OCR completed but no readable text was found in the image.")
            return ExtractedDocument(
                filename=upload.filename,
                media_type=upload.content_type,
                kind="image",
                text=text,
                confidence=confidence,
                warnings=warnings,
            )
        except Exception as exc:
            return ExtractedDocument(
                filename=upload.filename,
                media_type=upload.content_type,
                kind="image",
                warnings=[f"Image OCR was unavailable: {self._safe_error(exc)}"],
            )

    def _extract_pdf(self, upload: StoredUpload) -> ExtractedDocument:
        warnings: list[str] = []
        try:
            reader = PdfReader(upload.path)
            direct_text = clean_text("\n".join(page.extract_text() or "" for page in reader.pages))
            if len(direct_text) >= 40:
                return ExtractedDocument(
                    filename=upload.filename,
                    media_type=upload.content_type,
                    kind="pdf",
                    text=direct_text,
                    confidence=1.0,
                )

            ocr_text, ocr_confidence = self._ocr_embedded_pdf_images(reader)
            if ocr_text:
                return ExtractedDocument(
                    filename=upload.filename,
                    media_type=upload.content_type,
                    kind="pdf",
                    text=ocr_text,
                    confidence=ocr_confidence,
                    warnings=["The PDF had little selectable text, so embedded-image OCR was used."],
                )
            warnings.append(
                "No selectable text was found. OCR could not read embedded page images."
            )
            return ExtractedDocument(
                filename=upload.filename,
                media_type=upload.content_type,
                kind="pdf",
                text=direct_text,
                confidence=0.0 if direct_text else None,
                warnings=warnings,
            )
        except Exception as exc:
            return ExtractedDocument(
                filename=upload.filename,
                media_type=upload.content_type,
                kind="pdf",
                warnings=[f"PDF parsing failed: {self._safe_error(exc)}"],
            )

    def _ocr_embedded_pdf_images(self, reader: PdfReader) -> tuple[str, float | None]:
        try:
            import pytesseract
        except Exception:
            return "", None
        sections: list[str] = []
        scores: list[float] = []
        for page in reader.pages:
            for image_file in page.images:
                try:
                    image = Image.open(io.BytesIO(image_file.data))
                    data = pytesseract.image_to_data(
                        image, output_type=pytesseract.Output.DICT, config="--psm 6"
                    )
                    sections.extend(token for token in data["text"] if token.strip())
                    scores.extend(
                        float(score)
                        for score in data["conf"]
                        if str(score).strip() not in {"", "-1"}
                    )
                except Exception:
                    continue
        confidence = round(sum(scores) / len(scores) / 100, 2) if scores else None
        return clean_text(" ".join(sections)), confidence

    def _extract_audio(self, upload: StoredUpload) -> ExtractedDocument:
        duration = self._wav_duration(upload.path)
        if not self.openai_client:
            return ExtractedDocument(
                filename=upload.filename,
                media_type=upload.content_type,
                kind="audio",
                duration_seconds=duration,
                warnings=[
                    "Audio transcription needs GROQ_API_KEY. Add it to the deployment environment and retry."
                ],
            )
        try:
            with upload.path.open("rb") as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model=self.settings.transcription_model,
                    file=audio_file,
                    response_format="verbose_json",
                )
            text = clean_text(getattr(response, "text", ""))
            api_duration = getattr(response, "duration", None)
            return ExtractedDocument(
                filename=upload.filename,
                media_type=upload.content_type,
                kind="audio",
                text=text,
                confidence=0.9 if text else None,
                duration_seconds=api_duration or duration,
                warnings=[] if text else ["The transcription provider returned no text."],
            )
        except Exception as exc:
            return ExtractedDocument(
                filename=upload.filename,
                media_type=upload.content_type,
                kind="audio",
                duration_seconds=duration,
                warnings=[f"Audio transcription failed: {self._safe_error(exc)}"],
            )

    @staticmethod
    def _wav_duration(path: Path) -> float | None:
        if path.suffix.lower() != ".wav":
            return None
        try:
            with wave.open(str(path), "rb") as file:
                return round(file.getnframes() / file.getframerate(), 1)
        except (wave.Error, OSError):
            return None

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return str(exc).split("\n", 1)[0][:180] or exc.__class__.__name__
