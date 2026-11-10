"""Every Python block in README.md appears, line for line, in code that CI checks:
tests/readme_examples.py (mypy --strict and pyright) or tests/frameworks/ (run
in real FastAPI, Flask and Django apps). Edit both together."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKED = [ROOT / "tests" / "readme_examples.py", *sorted((ROOT / "tests" / "frameworks").glob("*_app.py"))]


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def blocks() -> list[str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", readme, re.S)


def contains(haystack: list[str], needle: list[str]) -> bool:
    return any(haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


def test_the_readme_has_python_examples() -> None:
    assert len(blocks()) >= 15


@pytest.mark.parametrize("block", blocks(), ids=lambda block: block.strip().splitlines()[0][:50])
def test_each_readme_block_is_in_checked_code(block: str) -> None:
    needle = lines(block)
    assert any(contains(lines(path.read_text(encoding="utf-8")), needle) for path in CHECKED), (
        "This README block isn't in tests/readme_examples.py or tests/frameworks/ word for word:\n" + block
    )
