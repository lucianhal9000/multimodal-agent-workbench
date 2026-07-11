from backend.app.config import Settings
from backend.app.models import TaskType
from backend.app.services.text_tasks import TextTaskService


def test_fallback_summary_has_all_required_sections() -> None:
    service = TextTaskService(Settings(), openai_client=None)
    answer = service.run(
        TaskType.SUMMARIZE,
        "Summarize this",
        "First point is important. Second point adds context. Third point concludes the discussion.",
    )

    assert "One-line summary:" in answer
    assert "Key points:" in answer
    assert "Five-sentence summary:" in answer
    assert answer.count("\n- ") == 3


def test_sentiment_fallback_returns_contract() -> None:
    service = TextTaskService(Settings(), openai_client=None)

    answer = service.run(TaskType.SENTIMENT, "Analyse sentiment", "The service was excellent and helpful.")

    assert "Label: Positive" in answer
    assert "Confidence:" in answer
    assert "Justification:" in answer

