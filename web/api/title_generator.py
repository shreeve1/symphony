"""Server-side auto-title generation from issue description via pi.

Tests stub run_func — no test depends on a live pi binary.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)
_TITLE_MAX_CHARS = 80
# Keep the create path snappy; fallback title is fine when pi is slow.
_TIMEOUT_S = 1


def generate_issue_title(
    description: str,
    *,
    run_func: Callable[..., Any] = subprocess.run,
) -> str:
    """Generate a title from the description using a one-shot pi call.

    Falls back to the first non-blank description line (trimmed to <=80 chars)
    on non-zero exit, timeout, empty stdout, or missing binary.
    """
    pi_bin = os.environ.get("PI_BIN", "pi")
    provider = os.environ.get("SYMPHONY_PI_PROVIDER", "zai")
    model = os.environ.get("SYMPHONY_PI_MODEL", "glm-5.1:high")

    prompt = (
        "Generate a short, descriptive issue title from this description."
        " Output only the plain title (<=80 characters), no quotes,"
        " no markdown, no prefix:\n\n" + description
    )
    command = [
        pi_bin,
        "--print",
        "--no-session",
        "--provider",
        provider,
        "--model",
        model,
        prompt,
    ]
    try:
        result = run_func(command, capture_output=True, text=True, timeout=_TIMEOUT_S)
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        logger.info("title_generator_pi_unavailable")
        return _fallback_title(description)

    if result.returncode != 0 or not result.stdout.strip():
        logger.info("title_generator_pi_failed returncode=%s", result.returncode)
        return _fallback_title(description)

    return _normalise(result.stdout)


def _normalise(raw: str) -> str:
    """Strip wrapping, markdown, quotes, whitespace; truncate to <=80 chars."""
    title = raw.strip()
    # Drop leading markdown heading markers.
    while title.startswith("#"):
        title = title[1:].strip()
    # Remove surrounding quotes.
    for pair in ('""', "''", "``", "“”", "‘’"):
        if len(title) >= 2 and title[0] == title[-1] == pair[0]:
            title = title[1:-1].strip()
    if len(title) > _TITLE_MAX_CHARS:
        title = title[:_TITLE_MAX_CHARS].rsplit(" ", 1)[0]
    return title.strip()


def _fallback_title(description: str) -> str:
    """First non-blank line trimmed to <=80 chars on a word boundary."""
    for line in description.splitlines():
        stripped = line.strip()
        if stripped:
            if len(stripped) > _TITLE_MAX_CHARS:
                return stripped[:_TITLE_MAX_CHARS].rsplit(" ", 1)[0]
            return stripped
    return "Untitled"
