"""Comment stamping helper — write-side header wrapper.

Every new write into ``comments_md`` is wrapped with a uniform machine-parseable
header so readers (frontend, parsers) can attribute each block to its origin
without heuristics.

Grammar (ADR-0017 §2.1)::

    ### <role> · <ISO-8601-UTC>\n\n<body>

Roles: ``agent`` | ``operator`` | ``patrol`` | ``system``

Old-format headers (``### Operator Reply (``, ``### Symphony``, ``Symphony-Schedule:``)
are NEVER rewritten — this module is write-side only.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ROLES = frozenset({"agent", "operator", "patrol", "system"})

# Regex matching every newly-stamped block header (ADR-0017 §2.1).
STAMP_HEADER_RE = re.compile(
    r"^### (agent|operator|patrol|system) · (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


def _stamp_comment(
    role: str,
    body: str,
    ts: datetime | None = None,
) -> str:
    """Wrap ``body`` with a ``### <role> · <ISO-ts>Z`` header.

    Args:
        role: One of ``agent``, ``operator``, ``patrol``, ``system``.
        body: The comment body (markdown).  Leading/trailing whitespace is
              stripped from the body, then it is placed under the header.
        ts:   Explicit timestamp (UTC); defaults to ``datetime.now(UTC)``.

    Returns:
        ``"### <role> · <ISO-ts>Z\\n\\n<body>"``

    Raises:
        ValueError: When ``role`` is not in ``VALID_ROLES``.
    """
    if role not in VALID_ROLES:
        raise ValueError(
            f"invalid stamp role {role!r}; must be one of {sorted(VALID_ROLES)}"
        )
    if ts is None:
        ts = datetime.now(timezone.utc)
    stamp = f"### {role} · {ts.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    return f"{stamp}\n\n{body.strip()}"


def _stamp_agent_comment(
    origin: object,
    body: str,
    ts: datetime | None = None,
) -> str:
    """Stamp agent output as patrol when the Issue came from patrol."""
    return _stamp_comment("patrol" if origin == "patrol" else "agent", body, ts)
