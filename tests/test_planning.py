from backend.app.models import TaskType
from backend.app.services.planning import Planner


def test_missing_goal_requires_follow_up() -> None:
    decision = Planner().decide("", "[Source: notes.pdf]\nProject notes", ["pdf"])

    assert decision.task == TaskType.CLARIFY
    assert decision.follow_up_question
    assert decision.steps[0].tool == "clarification_gate"


def test_pdf_youtube_request_chains_transcript_tool() -> None:
    decision = Planner().decide(
        "Hit the YT URL in this PDF and give me a summary",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ["pdf"],
    )

    assert decision.task == TaskType.SUMMARIZE
    assert decision.needs_youtube_transcript is True
    assert [step.tool for step in decision.steps] == [
        "pdf_parser",
        "youtube_transcript_fetcher",
        "structured_summarizer",
    ]


def test_action_items_precede_generic_summary() -> None:
    decision = Planner().decide("Summarize the action items", "", ["pdf"])

    assert decision.task == TaskType.ACTION_ITEMS
    assert decision.steps[-1].tool == "action_item_extractor"


def test_explain_image_code_uses_code_reviewer() -> None:
    decision = Planner().decide("Explain", "def total(values): return sum(values)", ["image"])

    assert decision.task == TaskType.CODE_EXPLANATION
    assert decision.steps[-1].tool == "code_reviewer"
