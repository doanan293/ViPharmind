from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _is_test_module(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
    )


def test_src_holds_no_test_modules() -> None:
    """pytest collects tests/ only, so a test under src/ would never run."""
    stray = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if _is_test_module(path)
    )
    assert stray == []
