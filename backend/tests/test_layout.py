from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
TEST_NAMES = ("test_", "conftest.py")


def test_src_holds_no_test_modules() -> None:
    """pytest collects tests/ only, so a test under src/ would never run."""
    stray = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if path.name.startswith(TEST_NAMES[0])
        or path.name.endswith("_test.py")
        or path.name == TEST_NAMES[1]
    )
    assert stray == []
