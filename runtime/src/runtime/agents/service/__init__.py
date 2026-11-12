"""The agents' rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.agents.service.declaration import NoSuchAgent, agent_of, apply_declaration, list_changes, read_model
from runtime.agents.service.resolution import name_model
from runtime.agents.service.setting_names import refuse_what_the_class_sets
from runtime.agents.service.settings import list_noted_versions, list_settings, resolve_for_call

__all__ = [
    "NoSuchAgent",
    "agent_of",
    "apply_declaration",
    "list_changes",
    "list_noted_versions",
    "list_settings",
    "name_model",
    "read_model",
    "refuse_what_the_class_sets",
    "resolve_for_call",
]
