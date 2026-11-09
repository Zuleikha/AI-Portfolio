"""Search node: runs the Stage 3 PubMed tool inside the graph (docs/PRD.md, Stage 6)."""

import httpx

from research_agent.observability import traced
from research_agent.state import GraphState
from research_agent.tools.pubmed import search_pubmed


@traced
def search_node(state: GraphState, *, client: httpx.Client | None = None) -> GraphState:
    """Graph node: reads ``query`` and ``max_results``, returns only ``search`` (G4).

    ``client`` is a test hook; leave it out in normal use.
    """
    return {"search": search_pubmed(state["query"], state["max_results"], client=client)}
