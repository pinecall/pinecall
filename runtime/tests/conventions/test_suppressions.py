"""The checkers are not argued with: a suppression lives on the allow-list below, with its reason, or not at all."""

import re

from tests.conventions.canon import SRC, Module

A_SUPPRESSION = re.compile(r"#\s*(type:\s*ignore|pyright:\s*ignore|noqa)(\[[^\]]*\])?(:\s*[A-Z0-9, ]+)?")

# Rules that may be silenced anywhere, each for one reason.
ALLOWED_RULES = frozenset(
    {
        # An untyped third-party surface: livekit's `room.on(...)` and `session.on(...)` take an untyped
        # listener, and redis-py types its commands with `**kwargs` it leaves unknown.
        "reportUnknownMemberType",
        # What an untyped third-party surface returns (livekit's, redis-py's), where the value is passed
        # straight on.
        "reportUnknownVariableType",
    }
)
# One file, one rule, one reason.
ALLOWED_IN_A_FILE: dict[tuple[str, str], str] = {
    ("session/voice.py", "reportMissingTypeStubs"): "smart_turn_livekit ships no stubs",
    ("session/prompt.py", "reportIncompatibleMethodOverride"): "livekit's ChatContext override takes its own arguments",
    ("session/prompt.py", "override"): "the same, as mypy names it",
}


def test_every_suppression_is_allowed(modules: dict[str, Module]) -> None:
    """No `type: ignore`, `pyright: ignore` or `noqa` outside the allow-list."""
    wrong: list[str] = []
    for module in modules.values():
        where = str(module.path.relative_to(SRC))
        for number, line in enumerate(module.path.read_text(encoding="utf-8").splitlines(), start=1):
            for found in A_SUPPRESSION.finditer(line):
                rules = {rule.strip() for rule in (found.group(2) or "").strip("[]").split(",") if rule.strip()}
                if found.group(1).startswith("noqa"):
                    wrong.append(f"{module.shown}:{number}: {found.group(0).strip()}: ruff is not silenced")
                    continue
                for rule in rules or {"(bare)"}:
                    if rule not in ALLOWED_RULES and (where, rule) not in ALLOWED_IN_A_FILE:
                        wrong.append(f"{module.shown}:{number}: {rule} is not on the allow-list")
    assert not wrong, "\n".join(wrong)
