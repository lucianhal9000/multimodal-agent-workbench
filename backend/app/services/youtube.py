import os
from dataclasses import dataclass

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

from .planning import YOUTUBE_URL_PATTERN


@dataclass(frozen=True)
class YouTubeTranscriptResult:
    text: str
    warning: str | None = None


class YouTubeTranscriptService:
    def _build_api(self) -> YouTubeTranscriptApi:
        proxy_username = os.getenv("YOUTUBE_PROXY_USERNAME")
        proxy_password = os.getenv("YOUTUBE_PROXY_PASSWORD")

        if proxy_username and proxy_password:
            return YouTubeTranscriptApi(
                proxy_config=WebshareProxyConfig(
                    proxy_username=proxy_username,
                    proxy_password=proxy_password,
                )
            )

        return YouTubeTranscriptApi()

    def fetch(self, url: str) -> YouTubeTranscriptResult:
        match = YOUTUBE_URL_PATTERN.search(url)

        if not match:
            return YouTubeTranscriptResult(
                "",
                "The detected URL is not a supported YouTube video URL.",
            )

        video_id = match.group(1)

        try:
            api = self._build_api()
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