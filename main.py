"""Host-native, tracker-agnostic Symphony scheduler entrypoint."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

from agent_runner import (
    AgentAdapter,
    PiAgentAdapter,
    PiRpcAgentAdapter,
    RemoteAgentAdapter,
    RoutingAgentAdapter,
    reap_orphan_rpc_processes,
    verify_pi_rpc_support,
    verify_pi_support,
)
from claude_runner import (
    ClaudeAgentAdapter,
    reap_orphan_claude_sockets,
    verify_claude_support,
)
from code_version import resolve_code_sha
from config import ProjectBinding, SymphonyConfig
from model_catalog import load_models, resolve_model
from notifier import TelegramNotifier
from plane_adapter import ClosablePlaneTransport, HttpxPlaneTransport, build_adapter
from tracker_adapter import TrackerAdapter
from prompt_renderer import IssueData, render_prompt
from repo_host import repo_host_for
from scheduler import _resolve_mode, reconcile_startup, run_loop
from tracker_contract import TrackerContract


@dataclass
class BindingRuntime:
    name: str
    config: SymphonyConfig
    transport: ClosablePlaneTransport | None
    adapter: TrackerAdapter
    agent_adapter: AgentAdapter
    pi_adapter: AgentAdapter | None = None
    binding: ProjectBinding | None = None


def _render_candidate_prompt(
    issue,
    *,
    contract: TrackerContract | None = None,
    repo_path: Path | None = None,
    binding_type: str = "infra",
    tracker_kind: Literal["plane", "podium"] = "plane",
    resume: bool = False,
) -> str:
    workflow_path = (repo_path or Path.cwd()) / "WORKFLOW.md"
    issue_data = IssueData(
        id=issue.id,
        identifier=issue.identifier,
        name=issue.name,
        description=issue.description,
        labels=", ".join(issue.labels),
        mode=_resolve_mode(issue.labels, contract)
        if contract is not None
        else _resolve_mode(issue.labels),
        schedule_not_before=getattr(issue, "schedule_not_before", ""),
        schedule_not_after=getattr(issue, "schedule_not_after", ""),
        schedule_reason=getattr(issue, "schedule_reason", ""),
        schedule_source=getattr(issue, "schedule_source", ""),
        schedule_late=getattr(issue, "schedule_late", ""),
        comments_md=getattr(issue, "comments_md", ""),
        context_md=getattr(issue, "context_md", ""),
        preferred_skill=getattr(issue, "preferred_skill", None),
    )
    if tracker_kind == "podium":
        return render_prompt(
            issue_data,
            path=workflow_path,
            binding_type=binding_type,
            tracker_kind="podium",
            resume=resume,
        )
    return render_prompt(issue_data, path=workflow_path, binding_type=binding_type)


def _probe_binding(config: SymphonyConfig, binding: ProjectBinding) -> None:
    binding_config = config.for_binding(binding)
    # Remote bindings dispatch pi over SSH (ADR-0012); the startup probe runs a
    # LOCAL pi in the binding's repo_path, which for a remote binding is a path
    # on the remote host (unreadable locally → it would crash startup). Skip the
    # local probe for remote bindings; remote pi readiness is the remote host's
    # concern (a remote SSH probe is a future refinement).
    if binding.default_agent == "pi" and not binding.is_remote:
        probe_provider = binding_config.pi_provider
        probe_model = binding_config.pi_model
        if binding.tracker == "podium":
            # Podium dispatch resolves provider/model from models.yml, so the
            # startup probe must exercise the catalog default, not legacy env.
            entry = resolve_model(None, load_models(), agent="pi")
            probe_provider = str(entry["provider"])
            probe_model = str(entry["id"])
        verify_pi_support(
            binding_config.pi_bin,
            probe_provider,
            probe_model,
            binding_config.homelab_repo_path,
        )
    elif binding.is_remote:
        # Non-fatal remote reachability check (ADR-0012): read the remote repo's
        # short SHA over SSH so an unreachable host / bad path surfaces at startup
        # as a warning. Never raise — a failed check must not crash the scheduler.
        try:
            sha = repo_host_for(binding).code_sha()
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "remote_repo_unreachable binding=%s host=%s error=%s",
                binding.name,
                binding.remote.host if binding.remote else "?",
                exc,
            )
        else:
            host = binding.remote.host if binding.remote else "?"
            if sha == "unknown":
                logging.getLogger(__name__).warning(
                    "remote_repo_unreachable binding=%s host=%s sha=unknown",
                    binding.name,
                    host,
                )
            else:
                logging.getLogger(__name__).info(
                    "remote_repo_reachable binding=%s host=%s sha=%s",
                    binding.name,
                    host,
                    sha,
                )


def build_binding_runtime(
    config: SymphonyConfig, binding: ProjectBinding
) -> BindingRuntime:
    """Build one binding runtime from config without startup probe side effects."""
    binding_config = config.for_binding(binding)
    if binding.tracker == "podium":
        transport = None
        # Defer the web.api.db edge for plane-only bindings.
        adapter_cls = import_module("tracker_podium").PodiumTrackerAdapter
        adapter = adapter_cls(
            binding_name=binding.name, contract=binding.tracker_contract
        )
    else:
        transport = HttpxPlaneTransport(
            binding_config.plane_api_url, binding_config.plane_api_key
        )
        adapter = build_adapter(transport, contract=binding.tracker_contract)
    pi_adapter = PiAgentAdapter(binding_config)
    pi_dispatch_adapter: AgentAdapter = (
        PiRpcAgentAdapter(binding_config) if binding.pi_mode == "rpc" else pi_adapter
    )
    remote_adapter: AgentAdapter | None = (
        RemoteAgentAdapter(config=binding_config, binding=binding)
        if binding.is_remote
        else None
    )
    return BindingRuntime(
        name=binding.name,
        config=binding_config,
        transport=transport,
        adapter=adapter,
        agent_adapter=RoutingAgentAdapter(
            binding=binding,
            pi_adapter=pi_dispatch_adapter,
            claude_adapter=ClaudeAgentAdapter(
                binding_config, persist=binding.claude_persist
            ),
            remote_adapter=remote_adapter,
        ),
        pi_adapter=pi_adapter,
        binding=binding,
    )


async def run_bindings_loop(
    config: SymphonyConfig, *, notifier: TelegramNotifier | None = None
) -> None:
    """Run the concurrent dispatcher for all bindings.

    Each binding gets its own run_loop with a per-binding _DispatchState
    (semaphore, in-flight set, poll interval). Startup reconcile runs for all
    bindings before the dispatcher loop starts.
    """
    reap_orphan_claude_sockets()
    verify_claude_support()
    reap_orphan_rpc_processes()
    rpc_binding = next(
        (b for b in config.bindings if getattr(b, "pi_mode", "one-shot") == "rpc"),
        None,
    )
    if rpc_binding is not None:
        verify_pi_rpc_support(config.pi_bin, rpc_binding.repo_path)
    runtimes = []
    for binding in config.bindings:
        _probe_binding(config, binding)
        runtimes.append(build_binding_runtime(config, binding))
    try:
        for runtime in runtimes:
            logging.getLogger(__name__).info(
                "reconcile_startup_begin binding=%s", runtime.name
            )
            try:
                cleaned = await reconcile_startup(
                    runtime.config,
                    runtime.adapter,
                    notifier=notifier,
                    binding=runtime.binding,
                )
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "reconcile_startup_failed binding=%s error=%s",
                    runtime.name,
                    exc,
                    exc_info=True,
                )
            else:
                logging.getLogger(__name__).info(
                    "reconcile_startup_done binding=%s cleaned=%d",
                    runtime.name,
                    cleaned,
                )
        # Each binding runs its own concurrent dispatcher loop.
        tasks = []
        for runtime in runtimes:
            loop_kwargs: dict[str, Any] = {
                "agent_runner": runtime.agent_adapter,
                "render_prompt": (
                    lambda issue, contract=runtime.adapter.contract, repo_path=runtime.config.homelab_repo_path, binding=runtime.binding: (
                        _render_candidate_prompt(
                            issue,
                            contract=contract,
                            repo_path=repo_path,
                            binding_type=getattr(binding, "binding_type", "infra"),
                            tracker_kind=getattr(binding, "tracker", "plane"),
                            resume=getattr(issue, "resumed", False),
                        )
                    )
                ),
                "notifier": notifier,
                "binding": runtime.binding,
            }
            if runtime.pi_adapter is not None:
                loop_kwargs["compaction_agent_runner"] = runtime.pi_adapter
            tasks.append(
                run_loop(
                    runtime.config,
                    runtime.adapter,
                    **loop_kwargs,
                )
            )
        await asyncio.gather(*tasks)
    finally:
        for runtime in runtimes:
            if runtime.transport is not None:
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
