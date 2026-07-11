import os
from dataclasses import dataclass

import httpx

from .planning import YOUTUBE_URL_PATTERN


@dataclass(frozen=True)
class YouTubeTranscriptResult:
    text: str
    warning: str | None = None


class YouTubeTranscriptService:
    API_URL = "https://api.supadata.ai/v1/transcript"

    def fetch(self, url: str) -> YouTubeTranscriptResult:
        match = YOUTUBE_URL_PATTERN.search(url)

        if not match:
            return YouTubeTranscriptResult(
                text="",
                warning=(
                    "The detected URL is not a supported "
                    "YouTube video URL."
                ),
            )

        api_key = os.getenv("SUPADATA_API_KEY")

        if not api_key:
            return YouTubeTranscriptResult(
                text="",
                warning=(
                    "YouTube transcript fetching requires "
                    "SUPADATA_API_KEY."
                ),
            )

        try:
            response = httpx.get(
                self.API_URL,
                params={
                    "url": url,
                    "text": "true",
                    "mode": "auto",
                },
                headers={
                    "x-api-key": api_key,
                },
                timeout=90.0,
            )

            if response.status_code == 202:
                return YouTubeTranscriptResult(
                    text="",
                    warning=(
                        "The transcript is still being generated. "
                        "Please retry shortly."
                    ),
                )

            response.raise_for_status()

            data = response.json()
            content = data.get("content", "")

            if isinstance(content, list):
                content = " ".join(
                    str(item.get("text", "")).strip()
                    for item in content
                    if item.get("text")
                )

            text = str(content).strip()

            if not text:
                return YouTubeTranscriptResult(
                    text="",
                    warning="The video transcript was empty.",
                )

            return YouTubeTranscriptResult(
                text=text,
                warning=None,
            )

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error_text = exc.response.text[:300]

            return YouTubeTranscriptResult(
                text="",
                warning=(
                    "YouTube transcript API failed with "
                    f"HTTP {status_code}: {error_text}"
                ),
            )

        except Exception as exc:
            return YouTubeTranscriptResult(
                text="",
                warning=(
                    "YouTube transcript fetch failed: "
                    f"{type(exc).__name__}: {str(exc)[:300]}"
                ),
            )