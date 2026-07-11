import pytest

from backend.app.services.ingestion import UnsupportedFileError, classify_file


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("scan.PNG", "image"), ("agenda.pdf", "pdf"), ("lecture.M4A", "audio")],
)
def test_classify_supported_files(filename: str, expected: str) -> None:
    assert classify_file(filename) == expected


def test_rejects_unsupported_files() -> None:
    with pytest.raises(UnsupportedFileError):
        classify_file("payload.exe")
