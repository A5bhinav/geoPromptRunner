"""Site-audit checkers (the §5 checker tiers).

The deterministic checkers (SSR, schema, links) are pure functions of a crawled
:class:`~src.audit.crawl.models.PageRecord` (or a set of them) → a typed verdict.
The Cat 3/4 :class:`~src.audit.checks.content_judge.ContentJudge` is the
LLM-judge tier — evidence-backed and calibrated to a gold set before use. No
checker re-fetches the live web; they read the crawl cache.
"""

from __future__ import annotations

from src.audit.checks.content_judge import (
    CONTENT_CHECKS,
    CONTENT_RUBRIC_VERSION,
    CheckVerdict,
    ContentClass,
    ContentJudge,
    ContentJudgeResult,
    finalize_check,
)
from src.audit.checks.content_primitives import (
    PRIMITIVE_CHECKS,
    ContentPrimitivesResult,
    PrimitiveCheck,
    check_content_primitives,
)
from src.audit.checks.links import (
    AnchorIssue,
    LinkGraphClass,
    LinkGraphResult,
    PageLinkInfo,
    analyze_link_graph,
)
from src.audit.checks.schema import (
    ContentMismatch,
    SchemaClass,
    SchemaResult,
    TypeFinding,
    check_schema,
)
from src.audit.checks.ssr import SSRClass, SSRResult, classify_ssr

__all__ = [
    "SSRClass",
    "SSRResult",
    "classify_ssr",
    "SchemaClass",
    "SchemaResult",
    "TypeFinding",
    "ContentMismatch",
    "check_schema",
    "LinkGraphClass",
    "LinkGraphResult",
    "PageLinkInfo",
    "AnchorIssue",
    "analyze_link_graph",
    "ContentJudge",
    "ContentJudgeResult",
    "CheckVerdict",
    "ContentClass",
    "CONTENT_CHECKS",
    "CONTENT_RUBRIC_VERSION",
    "finalize_check",
    "check_content_primitives",
    "ContentPrimitivesResult",
    "PrimitiveCheck",
    "PRIMITIVE_CHECKS",
]
