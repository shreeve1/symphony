"""Container entrypoint for the Symphony scheduler."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from agent_runner import AgentAdapter, ClaudeAgentAdapter, PiAgentAdapter, RoutingAgentAdapter, verify_pi_support
from code_version import resolve_code_sha
from config import ProjectBinding, SymphonyConfig
from notifier import TelegramNotifier
from plane_adapter import HttpxPlaneTransport, PlaneTransport, TrackerAdapter, build_adapter
from scheduler import _resolve_mode, reconcile_startup, run_tick
from tracker_contract import TrackerContract

from prompt_renderer import IssueData, render_prompt


@dataclass
class BindingRuntime:
    name: str
    config: SymphonyConfig
    transport: PlaneTransport
    adapter: TrackerAdapter
    agent_adapter: AgentAdapter


def _render_candidate_prompt(issue, contract: TrackerContract | None = None) -> str:
    return render_prompt(
        IssueData(
            id=issue.id,
            identifier=issue.identifier,
            name=issue.name,
            description=issue.description,
            labels=", ".join(issue.labels),
            mode=_resolve_mode(issue.labels, contract) if contract is not None else _resolve_mode(issue.labels),
            schedule_not_before=getattr(issue, "schedule_not_before", ""),
            schedule_not_after=getattr(issue, "schedule_not_after", ""),
            schedule_reason=getattr(issue, "schedule_reason", ""),
            schedule_source=getattr(issue, "schedule_source", ""),
            schedule_late=getattr(issue, "schedule_late", ""),
        )
    )


def _build_binding_runtime(config: SymphonyConfig, binding: ProjectBinding) -> BindingRuntime:
    binding_config = config.for_binding(binding)
    if binding.default_agent == "pi":
        verify_pi_support(
            binding_config.pi_bin,
            binding_config.pi_provider,
            binding_config.pi_model,
            binding_config.homelab_repo_path,
        )
    transport = HttpxPlaneTransport(binding_config.plane_api_url, binding_config.plane_api_key)
    adapter = build_adapter(transport, contract=binding.tracker_contract)
    return BindingRuntime(
        name=binding.name,
        config=binding_config,
        transport=transport,
        adapter=adapter,
        agent_adapter=RoutingAgentAdapter(
            binding=binding,
            pi_adapter=PiAgentAdapter(binding_config),
            claude_adapter=ClaudeAgentAdapter(binding_config),
        ),
    )


async def run_bindings_loop(config: SymphonyConfig, *, notifier: TelegramNotifier | None = None) -> None:
    """Run one scheduler tick per binding each interval."""

    runtimes = [_build_binding_runtime(config, binding) for binding in config.bindings]
    try:
        for runtime in runtimes:
            logging.getLogger(__name__).info("reconcile_startup_begin binding=%s", runtime.name)
            cleaned = await reconcile_startup(runtime.config, runtime.adapter, notifier=notifier)
            logging.getLogger(__name__).info(
                "reconcile_startup_done binding=%s cleaned=%d",
                runtime.name,
                cleaned,
            )
        while True:
            for runtime in runtimes:
                result = await run_tick(
                    runtime.config,
                    runtime.adapter,
                    agent_runner=runtime.agent_adapter,
                    render_prompt=lambda issue, contract=runtime.adapter.contract: _render_candidate_prompt(issue, contract),
                    notifier=notifier,
                )
                logging.getLogger(__name__).info(
                    "tick_completed binding=%s dispatched=%s reason=%s issue_id=%s",
                    runtime.name,
                    str(result.dispatched).lower(),
                    result.reason,
                    result.issue_id or "",
                )
            await asyncio.sleep(config.poll_interval_ms / 1000)
    finally:
        for runtime in runtimes:
            await runtime.transport.aclose()


async def async_main() -> None:
    """Load runtime config and run Symphony forever."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = SymphonyConfig.from_env()
    code_sha = resolve_code_sha()
    logging.getLogger(__name__).info(
        "symphony_started service=symphony code_sha=%s bindings=%d",
        code_sha,
        len(config.bindings),
    )

    notifier = TelegramNotifier.from_env()
    if notifier:
        logging.getLogger(__name__).info("telegram_notifications_enabled")
    else:
        logging.getLogger(__name__).info("telegram_notifications_disabled")

    await run_bindings_loop(config, notifier=notifier)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
