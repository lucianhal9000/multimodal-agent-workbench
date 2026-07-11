from dataclasses import dataclass

from youtube_transcript_api import YouTubeTranscriptApi

from .planning import YOUTUBE_URL_PATTERN


@dataclass(frozen=True)
class YouTubeTranscriptResult:
    text: str
    warning: str | None = None


class YouTubeTranscriptService:
    def fetch(self, url: str) -> YouTubeTranscriptResult:
        match = YOUTUBE_URL_PATTERN.search(url)

        if not match:
            return YouTubeTranscriptResult(
                "",
                "The detected URL is not a supported YouTube video URL.",
            )

        video_id = match.group(1)

        try:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)

            transcripts = list(transcript_list)

            if not transcripts:
                return YouTubeTranscriptResult(
                    "",
                    "No transcript tracks are available for this video.",
                )

            transcript = transcripts[0]

            fetched = transcript.fetch()

            text = " ".join(
                snippet.text.strip()
                for snippet in fetched
                if snippet.text.strip()
            )

            if not text:
                return YouTubeTranscriptResult(
                    "",
                    "The video transcript was empty.",
                )

            return YouTubeTranscriptResult(text)

        except Exception as exc:
            return YouTubeTranscriptResult(
                "",
                f"YouTube transcript fetch failed: "
                f"{type(exc).__name__}: {str(exc)[:300]}",
            )