import asyncio
import tempfile
import time
from pathlib import Path

from fastapi import UploadFile

from ..config import Settings
from ..models import AgentResponse, CostEstimate, ExtractedDocument, PlanStep, TaskType
from .ingestion import IngestionService
from .planning import PlanDecision, Planner
from .text_tasks import TextTaskService
from .youtube import YouTubeTranscriptService


class AgentService:
    """Coordinates extraction, explicit planning, optional transcript fetch, and a final text task."""

    def __init__(self, settings: Settings, openai_client: object | None = None):
        self.settings = settings
        self.ingestion = IngestionService(settings, openai_client)
        self.planner = Planner()
        self.youtube = YouTubeTranscriptService()
        self.text_tasks = TextTaskService(settings, openai_client)

    async def run(self, query: str, files: list[UploadFile]) -> AgentResponse:
        if len(files) > 8:
            raise ValueError("Upload at most 8 files in a single request.")

        documents: list[ExtractedDocument] = []
        extraction_elapsed: dict[str, int] = {}
        with tempfile.TemporaryDirectory(dir=self.settings.upload_dir) as temp_dir:
            request_dir = Path(temp_dir)
            for upload in files:
                stored = await self.ingestion.store_upload(upload, request_dir)
                started = time.perf_counter()
                document = await asyncio.to_thread(self.ingestion.extract, stored)
                elapsed = round((time.perf_counter() - started) * 1000)
                extraction_elapsed[document.kind] = extraction_elapsed.get(document.kind, 0) + elapsed
                documents.append(document)

            combined_context = self._combined_context(documents)
            decision = self.planner.decide(query, combined_context, [document.kind for document in documents])
            plan = self._mark_extraction_steps(decision, extraction_elapsed)

            if decision.task == TaskType.CLARIFY:
                plan = self._complete_step(plan, "clarification_gate", "completed")
                return AgentResponse(
                    status="needs_clarification",
                    answer=decision.follow_up_question or "Could you clarify the desired outcome?",
                    follow_up_question=decision.follow_up_question,
                    extracted_documents=documents,
                    plan=plan,
                    cost_estimate=self._estimate_cost(combined_context, decision.task),
                    warnings=self._warnings(documents),
                )

            if decision.needs_youtube_transcript:
                youtube_url = self.planner.find_youtube_url(f"{query}\n{combined_context}")
                if youtube_url:
                    started = time.perf_counter()
                    result = await asyncio.to_thread(self.youtube.fetch, youtube_url)
                    elapsed = round((time.perf_counter() - started) * 1000)
                    if result.text:
                        documents.append(
                            ExtractedDocument(
                                filename="YouTube transcript",
                                media_type="text/plain",
                                kind="youtube",
                                text=result.text,
                                confidence=1.0,
                            )
                        )
                        plan = self._complete_step(
                            plan,
                            "youtube_transcript_fetcher",
                            "completed",
                            f"Transcript fetched from {youtube_url}",
                            elapsed,
                        )
                    else:
                        plan = self._complete_step(
                            plan,
                            "youtube_transcript_fetcher",
                            "degraded",
                            result.warning,
                            elapsed,
                        )

            combined_context = self._combined_context(documents)
            final_step = plan[-1].tool
            started = time.perf_counter()
            answer = await asyncio.to_thread(
                self.text_tasks.run, decision.task, query, combined_context
            )
            elapsed = round((time.perf_counter() - started) * 1000)
            plan = self._complete_step(plan, final_step, "completed", elapsed_ms=elapsed)
            return AgentResponse(
                status="completed",
                answer=answer,
                extracted_documents=documents,
                plan=plan,
                cost_estimate=self._estimate_cost(combined_context, decision.task),
                warnings=self._warnings(documents),
            )

    def _mark_extraction_steps(
        self, decision: PlanDecision, elapsed_by_kind: dict[str, int]
    ) -> list[PlanStep]:
        tool_for_kind = {"image": "image_ocr", "pdf": "pdf_parser", "audio": "audio_transcriber"}
        plan: list[PlanStep] = []
        for step in decision.steps:
            matched_kind = next(
                (kind for kind, tool in tool_for_kind.items() if tool == step.tool), None
            )
            if matched_kind:
                plan.append(
                    step.model_copy(
                        update={"status": "completed", "elapsed_ms": elapsed_by_kind.get(matched_kind, 0)}
                    )
                )
            else:
                plan.append(step)
        return plan

    @staticmethod
    def _complete_step(
        plan: list[PlanStep],
        tool: str,
        status: str,
        detail: str | None = None,
        elapsed_ms: int | None = None,
    ) -> list[PlanStep]:
        updated: list[PlanStep] = []
        for step in plan:
            if step.tool == tool:
                payload = {"status": status}
                if detail:
                    payload["detail"] = detail
                if elapsed_ms is not None:
                    payload["elapsed_ms"] = elapsed_ms
                updated.append(step.model_copy(update=payload))
            else:
                updated.append(step)
        return updated

    @staticmethod
    def _combined_context(documents: list[ExtractedDocument]) -> str:
        sections = [
            f"[Source: {document.filename} | type: {document.kind}]\n{document.text}"
            for document in documents
            if document.text.strip()
        ]
        return "\n\n".join(sections)

    @staticmethod
    def _warnings(documents: list[ExtractedDocument]) -> list[str]:
        return [warning for document in documents for warning in document.warnings]

    @staticmethod
    def _estimate_cost(context: str, task: TaskType) -> CostEstimate:
        input_tokens = max(1, len(context) // 4)
        output_tokens = 700 if task in {TaskType.SUMMARIZE, TaskType.CODE_EXPLANATION} else 300
        # Groq Llama 3.3 70B list prices are used only as a planning heuristic.
        estimate = (input_tokens * 0.59 + output_tokens * 0.79) / 1_000_000
        return CostEstimate(
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_usd=round(estimate, 5),
            note="Heuristic estimate for Groq Llama 3.3 70B text generation; transcription and external tools are excluded.",
        )
