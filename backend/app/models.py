from enum import Enum

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    CLARIFY = "clarify"
    EXTRACT = "extract"
    SUMMARIZE = "summarize"
    SENTIMENT = "sentiment"
    CODE_EXPLANATION = "code_explanation"
    ACTION_ITEMS = "action_items"
    COMPARE = "compare"
    CONVERSATION = "conversation"


class PlanStep(BaseModel):
    tool: str
    reason: str
    status: str = "planned"
    detail: str | None = None
    elapsed_ms: int | None = None


class ExtractedDocument(BaseModel):
    filename: str
    media_type: str
    kind: str
    text: str = ""
    confidence: float | None = None
    duration_seconds: float | None = None
    warnings: list[str] = Field(default_factory=list)


class CostEstimate(BaseModel):
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_usd: float
    note: str


class AgentResponse(BaseModel):
    status: str
    answer: str
    extracted_documents: list[ExtractedDocument] = Field(default_factory=list)
    plan: list[PlanStep] = Field(default_factory=list)
    cost_estimate: CostEstimate
    follow_up_question: str | None = None
    warnings: list[str] = Field(default_factory=list)
