"""Write the real graph's Mermaid diagram into docs/ARCHITECTURE.md (docs/PRD.md, G13).

Usage, from the research-agent folder::

    python -m scripts.draw_graph

Only the text between the two marker comments changes. No API call, no cost.
"""

from pathlib import Path

from research_agent.graph import build_graph
from research_agent.observability import traced

ARCHITECTURE = Path(__file__).resolve().parent.parent / "docs" / "ARCHITECTURE.md"
START_MARKER = "<!-- graph:start -->"
END_MARKER = "<!-- graph:end -->"


@traced
def mermaid_block() -> str:
    """The fenced Mermaid block for the real graph."""
    return "```mermaid\n" + build_graph().get_graph().draw_mermaid().strip() + "\n```"


@traced
def replace_block(text: str, block: str) -> str:
    """Put ``block`` between the markers; fail loud if they are missing or out of order."""
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"{START_MARKER} / {END_MARKER} markers missing or out of order")
    head = text[: start + len(START_MARKER)]
    return f"{head}\n{block}\n{text[end:]}"


@traced
def main(path: Path = ARCHITECTURE) -> int:
    """Rewrite the diagram block in ``path``."""
    text = path.read_text(encoding="utf-8")
    path.write_text(replace_block(text, mermaid_block()), encoding="utf-8")
    print(f"Diagram written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
