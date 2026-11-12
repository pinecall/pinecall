"""The agents' rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.agents.service.declaration import agent_of
from runtime.agents.service.settings import list_settings, resolve_for_call

__all__ = ["agent_of", "list_settings", "resolve_for_call"]
