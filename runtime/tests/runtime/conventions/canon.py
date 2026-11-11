"""The canon's names as the tests read them: the tree under src/, the domains in order, a module parsed."""

import ast
from dataclasses import dataclass
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[3]
SRC = RUNTIME / "src" / "runtime"
PACKAGE = "runtime"

# True from the cutover on: every domain of the order exists. Until then a folder outside the canon fails
# and a domain not yet built does not.
WHOLE = False

# The domains, bottom up: a domain imports the service of one below it and never one above.
DOMAINS = (
    "platform",
    "billing",
    "mail",
    "accounts",
    "signin",
    "compliance",
    "providers",
    "agents",
    "knowledge",
    "whatsapp",
    "fleet",
    "telephony",
    "session",
    "judging",
    "alerts",
    "calls",
    "insights",
    "live",
    "flows",
    "evals",
    "hosting",
    "studio",
    "retention",
    "jobs",
    "hosts",
)
# Below every domain, read by any of them.
FOUNDATIONS = frozenset(
    {
        "kit",
        "wire",
        "enums",
        "config",
        "exceptions",
        "actor",
        "auth",
        "scoping",
        "postgres",
        "signal",
        "redis",
        "livekit",
        "shared_state",
        "handles",
        "migrations",
    }
)
# Above every domain: wiring only.
ENTRYPOINTS = frozenset({"app", "api", "worker", "runner", "cli"})
# A domain's value objects, read by any domain as its models are. Each is named in CONTRIBUTING.md.
VALUE_OBJECTS: frozenset[str] = frozenset()
# The files a domain folder holds, each a module or a package of the same name.
CANON_FILES = frozenset({"models", "schemas", "repository", "service", "auth", "endpoints", "tasks"})
# The modules a domain holds beside the canon's files: its long-lived objects and its value objects, each
# named in CONTRIBUTING.md. A domain enters here in the commit that builds it.
ENGINE_MODULES: dict[str, frozenset[str]] = {}
# A `service/` package may hold this many modules; past it the domain is cut, or CONTRIBUTING.md says in a
# sentence why it is one context and the domain is named here with that sentence.
MOST_SERVICE_MODULES = 16
ONE_CONTEXT: dict[str, str] = {}


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
    """The dotted name of a file under src/runtime, a package's `__init__` as the package."""
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
