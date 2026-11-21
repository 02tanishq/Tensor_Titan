"""
Deterministic Template Response Composer.
Merges individual PartResults into a unified, numbered response.
Enforces:
1. answer_type priority: confirm_needed > handed_to_human > clarification > refusal > answer > not_found
2. Pure template joining (NEVER LLM rewrite) so numbers and arithmetic are never distorted.
3. Deduplication of sources and aggregation of tool traces.
"""

from typing import List, Tuple, Optional, Set
from app.models import (
    PartResult,
    ChatResponse,
    SourceCited,
    ToolExecutionTrace,
    PendingAction,
    HandedToHuman,
)

ANSWER_TYPE_PRIORITY = {
    "confirm_needed": 1,
    "handed_to_human": 2,
    "clarification": 3,
    "refusal": 4,
    "answer": 5,
    "not_found": 6,
    "action_done": 7
}


def compose(part_results: List[PartResult], trace_id: str) -> ChatResponse:
    """
    Deterministically compose multiple PartResults into a single final ChatResponse.
    One-line reason: Template-based numbered composition ensures zero LLM distortion of tool calculations.
    """
    if not part_results:
        return ChatResponse(
            trace_id=trace_id,
            answer_type="not_found",
            answer="No answerable request could be extracted from your query.",
            sources=[],
            tools=[],
            pending_action=None,
            handed_to_human=None
        )

    # 1. Determine overall answer_type by highest priority
    best_answer_type = min(
        part_results,
        key=lambda r: ANSWER_TYPE_PRIORITY.get(r.answer_type, 99)
    ).answer_type

    # 2. Join texts with numbered template sections if multiple parts
    if len(part_results) == 1:
        composite_answer = part_results[0].text
    else:
        sections = []
        for i, res in enumerate(part_results, start=1):
            sections.append(f"{i}. {res.text.strip()}")
        composite_answer = "\n\n".join(sections)

    # 3. Deduplicate sources
    sources: List[SourceCited] = []
    seen_sources: Set[Tuple[str, str]] = set()
    for res in part_results:
        for s in res.sources:
            pair = (s.doc_id, s.section)
            if pair not in seen_sources:
                seen_sources.add(pair)
                sources.append(s)

    # 4. Concatenate tools
    tools: List[ToolExecutionTrace] = []
    for res in part_results:
        tools.extend(res.tools)

    # 5. Extract single pending action (at most 1 per turn)
    pending_action: Optional[PendingAction] = None
    for res in part_results:
        if res.pending_action:
            pending_action = res.pending_action
            break

    # 6. Extract first handed_to_human if present
    handed_to_human: Optional[HandedToHuman] = None
    for res in part_results:
        if res.handed_to_human:
            handed_to_human = res.handed_to_human
            break

    return ChatResponse(
        trace_id=trace_id,
        answer_type=best_answer_type,
        answer=composite_answer,
        sources=sources,
        tools=tools,
        pending_action=pending_action,
        handed_to_human=handed_to_human
    )
