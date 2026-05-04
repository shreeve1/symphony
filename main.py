"""Container entrypoint for the Symphony scheduler."""

from __future__ import annotations

import asyncio
import logging

from agent_runner import run_agent
from config import SymphonyConfig
from plane_poller import HttpxPlaneTransport, build_adapter
from scheduler import run_loop

from homelab_router.prompt_renderer import IssueData, render_prompt


def _render_candidate_prompt(issue) -> str:
    return render_prompt(
        IssueData(
            id=issue.id,
            identifier=issue.identifier,
            name=issue.name,
            description=issue.description,
            labels=", ".join(issue.labels),
        )
    )


async def async_main() -> None:
    """Load runtime config and run Symphony forever."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = SymphonyConfig.from_env()
    transport = HttpxPlaneTransport(config.plane_api_url, config.plane_api_key)
    def configured_agent_runner(issue, rendered_prompt):
        return run_agent(config, issue, rendered_prompt)

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
        )
    finally:
        await transport.aclose()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
