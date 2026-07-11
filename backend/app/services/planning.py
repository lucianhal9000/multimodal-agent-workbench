import re
from dataclasses import dataclass

from ..models import PlanStep, TaskType


YOUTUBE_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{6,})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PlanDecision:
    task: TaskType
    steps: list[PlanStep]
    follow_up_question: str | None = None
    needs_youtube_transcript: bool = False


class Planner:
    """Small deterministic policy layer for auditable and bounded tool use."""

    def decide(self, query: str, extracted_text: str, file_kinds: list[str]) -> PlanDecision:
        normalized = query.lower().strip()
        if not normalized:
            return PlanDecision(
                task=TaskType.CLARIFY,
                steps=[
                    PlanStep(
                        tool="clarification_gate",
                        reason="No requested outcome was supplied, so selecting a task would be a guess.",
                    )
                ],
                follow_up_question=(
                    "What would you like me to do with the uploaded content—for example, summarize, "
                    "extract text, compare it, or analyse sentiment?"
                ),
            )

        task = self._classify_task(normalized, extracted_text)
        youtube_match = YOUTUBE_URL_PATTERN.search(f"{query}\n{extracted_text}")
        needs_youtube = bool(youtube_match) and self._requests_video_content(normalized)
        steps = self._build_steps(task, file_kinds, needs_youtube)
        return PlanDecision(task=task, steps=steps, needs_youtube_transcript=needs_youtube)

    @staticmethod
    def find_youtube_url(text: str) -> str | None:
        match = YOUTUBE_URL_PATTERN.search(text)
        return match.group(0) if match else None

    @staticmethod
    def _classify_task(query: str, extracted_text: str) -> TaskType:
        if any(token in query for token in ("action item", "next step", "todo", "to-do")):
            return TaskType.ACTION_ITEMS
        if any(token in query for token in ("sentiment", "positive", "negative", "tone")):
            return TaskType.SENTIMENT
        code_markers = ("def ", "function ", "class ", "=>", "console.", "import ")
        if any(token in query for token in ("explain code", "code explain", "bug", "time complexity")) or (
            "explain" in query and any(marker in extracted_text.lower() for marker in code_markers)
        ):
            return TaskType.CODE_EXPLANATION
        if any(token in query for token in ("same topic", "compare", "difference", "similar")):
            return TaskType.COMPARE
        if any(token in query for token in ("summarize", "summary", "tl;dr", "summarise")):
            return TaskType.SUMMARIZE
        if any(token in query for token in ("extract", "transcribe", "ocr", "read the text")):
            return TaskType.EXTRACT
        return TaskType.CONVERSATION

    @staticmethod
    def _requests_video_content(query: str) -> bool:
        return any(
            token in query
            for token in ("youtube", "youtu", "yt ", "video", "transcript", "this url", "the url")
        )

    @staticmethod
    def _build_steps(task: TaskType, file_kinds: list[str], needs_youtube: bool) -> list[PlanStep]:
        steps: list[PlanStep] = []
        for kind in sorted(set(file_kinds)):
            tool = {"image": "image_ocr", "pdf": "pdf_parser", "audio": "audio_transcriber"}[kind]
            steps.append(PlanStep(tool=tool, reason=f"Extract usable text from the uploaded {kind} input."))
        if needs_youtube:
            steps.append(
                PlanStep(
                    tool="youtube_transcript_fetcher",
                    reason="A YouTube URL is present and the query explicitly asks for video content.",
                )
            )
        task_tool = {
            TaskType.EXTRACT: "clean_transcript",
            TaskType.SUMMARIZE: "structured_summarizer",
            TaskType.SENTIMENT: "sentiment_analyzer",
            TaskType.CODE_EXPLANATION: "code_reviewer",
            TaskType.ACTION_ITEMS: "action_item_extractor",
            TaskType.COMPARE: "cross_input_comparator",
            TaskType.CONVERSATION: "response_generator",
        }[task]
        steps.append(
            PlanStep(tool=task_tool, reason=f"Produce the requested {task.value.replace('_', ' ')} result."))
        return steps
