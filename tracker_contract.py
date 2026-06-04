"""Symphony-owned tracker role contract.

The scheduler branches on engine roles; this contract maps those roles to the
concrete Plane state/label names and UUIDs for one binding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TrackerRole(str, Enum):
    MODE_PLAN = "mode:plan"
    MODE_BUILD = "mode:build"
    APPROVAL_REQUIRED = "approval-required"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    STATE_TODO = "state:todo"
    STATE_IN_REVIEW = "state:in-review"
    STATE_RUNNING = "state:running"
    STATE_BLOCKED = "state:blocked"
    STATE_DONE = "state:done"


REQUIRED_LABEL_ROLES: tuple[TrackerRole, ...] = (
    TrackerRole.MODE_PLAN,
    TrackerRole.MODE_BUILD,
)
REQUIRED_STATE_ROLES: tuple[TrackerRole, ...] = (
    TrackerRole.STATE_TODO,
    TrackerRole.STATE_IN_REVIEW,
    TrackerRole.STATE_RUNNING,
    TrackerRole.STATE_BLOCKED,
    TrackerRole.STATE_DONE,
)


@dataclass(frozen=True)
class RoleBinding:
    """Concrete tracker vocabulary for one engine role."""

    name: str
    uuid: str = ""


class PlaneState(str, Enum):
    """Compatibility names for Plane issue states."""

    TODO = "Todo"
    IN_REVIEW = "In Review"
    RUNNING = "Running"
    BLOCKED = "Blocked"
    DONE = "Done"


class PlaneLabel(str, Enum):
    """Compatibility names for labels used by tests and non-engine helpers."""

    PATROL = "patrol"
    SECURITY = "security"
    INFRA = "infra"
    NETWORK = "network"
    MEDIA = "media"
    STORAGE = "storage"
    DOCKER = "docker"
    APPROVAL_REQUIRED = "approval-required"
    PLAN = "plan"
    BUILD = "build"
    APPROVED = "approved"
    SCHEDULED = "scheduled"


STATE_TO_ROLE: dict[PlaneState, TrackerRole] = {
    PlaneState.TODO: TrackerRole.STATE_TODO,
    PlaneState.IN_REVIEW: TrackerRole.STATE_IN_REVIEW,
    PlaneState.RUNNING: TrackerRole.STATE_RUNNING,
    PlaneState.BLOCKED: TrackerRole.STATE_BLOCKED,
    PlaneState.DONE: TrackerRole.STATE_DONE,
}

LABEL_TO_ROLE: dict[PlaneLabel, TrackerRole] = {
    PlaneLabel.PLAN: TrackerRole.MODE_PLAN,
    PlaneLabel.BUILD: TrackerRole.MODE_BUILD,
    PlaneLabel.APPROVAL_REQUIRED: TrackerRole.APPROVAL_REQUIRED,
    PlaneLabel.APPROVED: TrackerRole.APPROVED,
    PlaneLabel.SCHEDULED: TrackerRole.SCHEDULED,
}

ROLE_TO_COMPAT_LABEL: dict[TrackerRole, PlaneLabel] = {
    role: label for label, role in LABEL_TO_ROLE.items()
}


@dataclass(frozen=True)
class PlaneUserMapping:
    homelab_user: str
    plane_uuid: str
    plane_display_name: str
    role: str = "admin"


@dataclass(frozen=True)
class TrackerContract:
    """Role-based tracker contract for one binding."""

    version: str = "1.0"
    workspace_slug: str = "homelab"
    project_slug: str = "automations"
    project_id: str = ""
    state_roles: dict[TrackerRole, RoleBinding] = field(default_factory=dict)
    label_roles: dict[TrackerRole, RoleBinding] = field(default_factory=dict)
    extra_label_ids: dict[str, str] = field(default_factory=dict)
    users: tuple[PlaneUserMapping, ...] = (
        PlaneUserMapping(
            homelab_user="james",
            plane_uuid="0423d289-e898-43a1-8aaf-b66010dc85ac",
            plane_display_name="James",
            role="admin",
        ),
    )

    @property
    def state_ids(self) -> dict[str, str]:
        return {binding.name: binding.uuid for binding in self.state_roles.values() if binding.uuid}

    @property
    def label_ids(self) -> dict[str, str]:
        ids: dict[str, str] = dict(self.extra_label_ids)
        for binding in self.label_roles.values():
            if binding.uuid:
                ids[binding.name] = binding.uuid
        return ids

    @property
    def states(self) -> tuple[PlaneState, ...]:
        return tuple(STATE_TO_ROLE.keys())

    @property
    def labels(self) -> tuple[PlaneLabel, ...]:
        return tuple(PlaneLabel)

    @property
    def provisioned_labels(self) -> tuple[PlaneLabel, ...]:
        return tuple(PlaneLabel)

    @property
    def overlay_labels(self) -> tuple[PlaneLabel, ...]:
        return (
            PlaneLabel.SECURITY,
            PlaneLabel.INFRA,
            PlaneLabel.NETWORK,
            PlaneLabel.MEDIA,
            PlaneLabel.STORAGE,
            PlaneLabel.DOCKER,
        )

    def state_binding(self, role: TrackerRole) -> RoleBinding:
        binding = self.state_roles.get(role)
        if binding is None:
            raise ValueError(f"tracker contract missing required state role: {role.value}")
        return binding

    def label_binding(self, role: TrackerRole) -> RoleBinding:
        binding = self.label_roles.get(role)
        if binding is None:
            raise ValueError(f"tracker contract missing required label role: {role.value}")
        return binding

    def optional_label_binding(self, role: TrackerRole) -> RoleBinding | None:
        return self.label_roles.get(role)

    def state_name_for_role(self, role: TrackerRole) -> str:
        return self.state_binding(role).name

    def state_value_for_role(self, role: TrackerRole) -> str:
        binding = self.state_binding(role)
        return binding.uuid or binding.name

    def label_name_for_role(self, role: TrackerRole) -> str:
        return self.label_binding(role).name

    def label_value_for_role(self, role: TrackerRole) -> str:
        binding = self.label_binding(role)
        return binding.uuid or binding.name

    def optional_label_name_for_role(self, role: TrackerRole) -> str | None:
        binding = self.optional_label_binding(role)
        return binding.name if binding else None

    def optional_label_value_for_role(self, role: TrackerRole) -> str | None:
        binding = self.optional_label_binding(role)
        if binding is None:
            return None
        return binding.uuid or binding.name

    def label_role_for_name(self, name: str) -> TrackerRole | None:
        for role, binding in self.label_roles.items():
            if binding.name == name:
                return role
        return None

    def label_name_for_uuid(self, uuid: str) -> str | None:
        for binding in self.label_roles.values():
            if binding.uuid == uuid:
                return binding.name
        return None

    def state_names(self) -> set[str]:
        return {binding.name for binding in self.state_roles.values()}

    def label_names(self) -> set[str]:
        return {binding.name for binding in self.label_roles.values()} | set(self.extra_label_ids)

    def provisioned_label_names(self) -> set[str]:
        return {label.value for label in self.provisioned_labels}

    def overlay_label_names(self) -> set[str]:
        return {label.value for label in self.overlay_labels}

    def user_by_homelab_name(self, name: str) -> PlaneUserMapping | None:
        for user in self.users:
            if user.homelab_user == name:
                return user
        return None

    def validate_shape(self) -> list[str]:
        errors: list[str] = []
        if not self.workspace_slug:
            errors.append("workspace_slug is required")
        if not self.project_slug:
            errors.append("project_slug is required")
        if not self.project_id:
            errors.append("project_id is required")
        for role in REQUIRED_STATE_ROLES:
            binding = self.state_roles.get(role)
            if binding is None:
                errors.append(f"missing required state role: {role.value}")
            elif not binding.name:
                errors.append(f"state role {role.value} has empty name")
        for role in REQUIRED_LABEL_ROLES:
            binding = self.label_roles.get(role)
            if binding is None:
                errors.append(f"missing required label role: {role.value}")
            elif not binding.name:
                errors.append(f"label role {role.value} has empty name")
        if len(self.users) == 0:
            errors.append("at least one user mapping is required")
        for user in self.users:
            if not user.homelab_user:
                errors.append("user mapping has empty homelab_user")
            if not user.plane_uuid:
                errors.append(f"user '{user.homelab_user}' has empty plane_uuid")
            if not user.plane_display_name:
                errors.append(f"user '{user.homelab_user}' has empty plane_display_name")
        return errors


PlaneContract = TrackerContract


DEFAULT_CONTRACT = TrackerContract(
    project_id="cff68c17-bff6-452f-89b3-9b570613cfaa",
    state_roles={
        TrackerRole.STATE_TODO: RoleBinding("Todo", "ecdab56c-3d58-4da4-bed0-90f0c665deeb"),
        TrackerRole.STATE_RUNNING: RoleBinding("Running", "6d96e0cb-90f5-4581-807c-a7c9a976b422"),
        TrackerRole.STATE_IN_REVIEW: RoleBinding("In Review", "ea1ccd3d-82d3-4dd4-8226-192941e8e4c0"),
        TrackerRole.STATE_BLOCKED: RoleBinding("Blocked", "4b226b00-1e1c-46aa-bbd3-b1e04ad6fc1f"),
        TrackerRole.STATE_DONE: RoleBinding("Done", "ef9d22b5-c69c-4707-8ba3-e3db244f2a84"),
    },
    label_roles={
        TrackerRole.APPROVAL_REQUIRED: RoleBinding("approval-required", "e7480a55-5ab6-417b-a74a-f436ffcf1db7"),
        TrackerRole.MODE_PLAN: RoleBinding("plan", "5a022793-c712-4565-ab70-0183fe04c557"),
        TrackerRole.MODE_BUILD: RoleBinding("build", "4ffc7ef9-9159-455c-b3f9-b3a447157aef"),
        TrackerRole.APPROVED: RoleBinding("approved", "67839626-ca7f-4c02-a5e0-12e56a35d909"),
        TrackerRole.SCHEDULED: RoleBinding("scheduled", "9ac7586e-8745-4c22-8a9d-aa83652bee3e"),
    },
    extra_label_ids={
        "patrol": "74f5ab2e-a567-4f8b-8dcf-0908c7ea9ceb",
        "security": "618c2146-78d0-4955-a651-bd0c7ad5712e",
        "infra": "95635e31-ed47-4a2e-96ab-555e43242fa1",
        "network": "cb36e80d-9cea-4935-b9a6-29d3c4d7d90f",
        "media": "a683fbd6-a83a-439f-9e01-123a7088c04d",
        "storage": "cf3e9144-3925-41f0-ac62-3cb7aa3ac480",
        "docker": "c1d39f14-19e0-434a-a183-90bd28ae2875",
    },
)


def coerce_state_role(state: PlaneState | TrackerRole) -> TrackerRole:
    if isinstance(state, TrackerRole):
        return state
    return STATE_TO_ROLE[state]


def coerce_label_role(label: PlaneLabel | TrackerRole) -> TrackerRole | None:
    if isinstance(label, TrackerRole):
        return label
    return LABEL_TO_ROLE.get(label)


def label_name(label: PlaneLabel | TrackerRole, contract: TrackerContract = DEFAULT_CONTRACT) -> str:
    role = coerce_label_role(label)
    if role is not None:
        return contract.label_name_for_role(role)
    return label.value


def state_name(state: PlaneState | TrackerRole, contract: TrackerContract = DEFAULT_CONTRACT) -> str:
    return contract.state_name_for_role(coerce_state_role(state))
