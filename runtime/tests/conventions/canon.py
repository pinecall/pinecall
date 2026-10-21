"""The canon's names as the tests read them: the tree under src/, the domains in order, a module parsed."""

import ast
from dataclasses import dataclass
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[2]
SRC = RUNTIME / "src" / "pinecall_runtime"
PACKAGE = "pinecall_runtime"

# The domains, bottom up: a domain imports the service of one below it and never one above.
DOMAINS = (
    "platform",
    "billing",
    "accounts",
    "compliance",
    "providers",
    "agents",
    "knowledge",
    "channels",
    "fleet",
    "telephony",
    "session",
    "judging",
    "alerts",
    "calls",
    "evals",
    "hosting",
    "studio",
    "retention",
    "jobs",
)
# Below every domain, read by any of them.
FOUNDATIONS = frozenset({"kit", "wire", "enums", "config", "exceptions", "postgres", "redis", "livekit", "migrations"})
# Above every domain: wiring only.
ENTRYPOINTS = frozenset({"app", "api", "worker", "runner", "cli"})
# A domain's value objects, read by any domain as its models are.
VALUE_OBJECTS = frozenset({"agents.declaration", "calls.context"})
# The files a domain folder holds, each a module or a package of the same name.
CANON_FILES = frozenset({"models", "schemas", "repository", "service", "auth", "endpoints", "tasks"})
# The engines' own modules, and the two value objects, named in CONTRIBUTING.md.
ENGINE_MODULES: dict[str, frozenset[str]] = {
    "agents": frozenset({"declaration"}),
    "calls": frozenset(
        {
            "store",
            "writer",
            "relay",
            "fanout",
            "logs",
            "facts",
            "reducer",
            "readers",
            "private",
            "histogram",
            "latencies",
            "metering",
            "recordings",
            "context",
        }
    ),
    "session": frozenset(
        {
            "call",
            "writing",
            "session",
            "agent",
            "prompt",
            "tools",
            "lookups",
            "hearing",
            "voice",
            "text",
            "room",
            "widget",
            "hold",
            "recording",
            "clock",
            "listener",
            "echo",
            "repeats",
        }
    ),
    # The judges' and the personas' texts the box ships, read by judging's service.
    "judging": frozenset({"library"}),
}


@dataclass(frozen=True, slots=True)
class Module:
    """One module of the package: its dotted name, its path, and its tree."""

    name: str
    path: Path
    tree: ast.Module

    @property
    def parts(self) -> tuple[str, ...]:
        """The name's parts after the package."""
        return tuple(self.name.split("."))

    @property
    def domain(self) -> str | None:
        """The domain the module is in, or None for a foundation or an entrypoint."""
        return self.parts[0] if self.parts[0] in DOMAINS else None

    # The canon's file inside the domain: schemas, repository, service, auth, endpoints, tasks, or
    # an engine's own module.
    @property
    def kind(self) -> str:
        """The second part of the name, or `__init__` for the domain's own package."""
        return self.parts[1] if len(self.parts) > 1 else "__init__"

    @property
    def shown(self) -> str:
        """The path as a failure names it."""
        return str(self.path.relative_to(RUNTIME))

    def imports(self) -> list[tuple[str, list[str], int]]:
        """Every `from X import a, b` and `import X`, anywhere in the module: the module, the names, the line."""
        found: list[tuple[str, list[str], int]] = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.append((node.module, [alias.name for alias in node.names], node.lineno))
            elif isinstance(node, ast.Import):
                found.extend((alias.name, [], node.lineno) for alias in node.names)
        return found


def module_name(path: Path) -> str:
    """The dotted name of a file under src/pinecall_runtime, a package's `__init__` as the package."""
    parts = path.relative_to(SRC).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or PACKAGE


def of_ours(target: str) -> tuple[str | None, str]:
    """The top-level part and the dotted path after the package of an import of ours; (None, "") otherwise."""
    if not target.startswith(PACKAGE + "."):
        return None, ""
    dotted = target[len(PACKAGE) + 1 :]
    return dotted.split(".")[0], dotted


def read_modules() -> dict[str, Module]:
    """Every module of the package, parsed, by name."""
    found: dict[str, Module] = {}
    for path in sorted(SRC.rglob("*.py")):
        name = module_name(path)
        found[name] = Module(name, path, ast.parse(path.read_text(encoding="utf-8"), str(path)))
    return found
