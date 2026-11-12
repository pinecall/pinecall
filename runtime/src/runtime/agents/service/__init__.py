"""The agents' rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.agents.service.declaration import (
    NoSuchAgent,
    agent_of,
    apply_declaration,
    declaration_of,
    declare,
    list_changes,
    put_declaration,
    read_model,
)
from runtime.agents.service.kinds import BUILT_IN_STUDIO, is_studio_key, kind_of
from runtime.agents.service.lexicon import put_lexicon
from runtime.agents.service.resolution import name_model
from runtime.agents.service.setting_names import NAME_IN_DECLARATION, refuse_what_the_class_sets
from runtime.agents.service.setting_writes import SettingsPlan, keep_settings, plan_settings, put_settings, try_settings
from runtime.agents.service.settings import (
    Picked,
    Resolved,
    Shown,
    check_test_values,
    current_settings,
    declaration_for_call,
    find_settings_version,
    list_noted_versions,
    list_settings,
    parse_settings,
    resolve_for_call,
    show_settings,
)
from runtime.agents.service.versions import Written

__all__ = [
    "BUILT_IN_STUDIO",
    "NAME_IN_DECLARATION",
    "NoSuchAgent",
    "Picked",
    "Resolved",
    "SettingsPlan",
    "Shown",
    "Written",
    "agent_of",
    "apply_declaration",
    "check_test_values",
    "current_settings",
    "declaration_for_call",
    "declaration_of",
    "declare",
    "find_settings_version",
    "is_studio_key",
    "keep_settings",
    "kind_of",
    "list_changes",
    "list_noted_versions",
    "list_settings",
    "name_model",
    "parse_settings",
    "plan_settings",
    "put_declaration",
    "put_lexicon",
    "put_settings",
    "read_model",
    "refuse_what_the_class_sets",
    "resolve_for_call",
    "show_settings",
    "try_settings",
]
