"""Container entrypoint for the Symphony scheduler."""

from __future__ import annotations

import asyncio
import logging

from agent_runner import run_agent, verify_pi_support
from code_version import resolve_code_sha
from config import SymphonyConfig
from notifier import TelegramNotifier
from plane_poller import HttpxPlaneTransport, build_adapter
from scheduler import _resolve_mode, run_loop

from homelab_router.prompt_renderer import IssueData, render_prompt


def _render_candidate_prompt(issue) -> str:
    return render_prompt(
        IssueData(
            id=issue.id,
            identifier=issue.identifier,
            name=issue.name,
            description=issue.description,
            labels=", ".join(issue.labels),
            mode=_resolve_mode(issue.labels),
            schedule_not_before=getattr(issue, "schedule_not_before", ""),
            schedule_not_after=getattr(issue, "schedule_not_after", ""),
            schedule_reason=getattr(issue, "schedule_reason", ""),
            schedule_source=getattr(issue, "schedule_source", ""),
            schedule_late=getattr(issue, "schedule_late", ""),
        )
    )


async def async_main() -> None:
    """Load runtime config and run Symphony forever."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = SymphonyConfig.from_env()
    code_sha = resolve_code_sha()
    logging.getLogger(__name__).info(
        "symphony_started service=symphony code_sha=%s", code_sha
    )
    verify_pi_support(
        config.pi_bin,
        config.pi_provider,
        config.pi_model,
        config.homelab_repo_path,
    )
    transport = HttpxPlaneTransport(config.plane_api_url, config.plane_api_key)
    def configured_agent_runner(issue, rendered_prompt):
        return run_agent(config, issue, rendered_prompt)

    notifier = TelegramNotifier.from_env()
    if notifier:
        logging.getLogger(__name__).info("telegram_notifications_enabled")
    else:
        logging.getLogger(__name__).info("telegram_notifications_disabled")

    try:
        await run_loop(
            config,
            build_adapter(
                transport,
                workspace_slug=config.plane_workspace_slug,
                project_id=config.plane_project_id,
            ),
            agent_runner=configured_agent_runner,
            render_prompt=_render_candidate_prompt,
            notifier=notifier,
        )
    finally:
        await transport.aclose()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
