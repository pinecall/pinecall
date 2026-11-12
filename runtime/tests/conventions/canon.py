"""The canon's names as the tests read them: the tree under src/, the domains in order, a module parsed."""

import ast
from dataclasses import dataclass
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[2]
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
ENTRYPOINTS = frozenset({"app", "lifespan", "builders", "api", "worker", "runner", "cli"})
# A domain's value objects, read by any domain as its models are. Each is named in CONTRIBUTING.md.
VALUE_OBJECTS: frozenset[str] = frozenset(
    {
        # A stage as values: what an agent asks for (`Model`, `Voice`) and the stage resolved (`Running`, `Pipeline`).
        "providers.stage",
        # The providers row: the shape of a document the box keeps, and the one reader of its keys.
        "providers.catalog",
        # What an agent's class declares: its tools, its turns, its words, and the declaration whole.
        "agents.declaration",
        # What the org sets on an agent over its class: its settings, its lexicon, the versions a call ran on.
        "agents.settings",
        # What a call is: its id, who calls, the route it came in by, its day, and the name its log goes by.
        "calls.context",
        # What each audience reads of an entry and of the state: the tenant's, masked, and the public's.
        "calls.projection",
        # Where a call's audio is kept, the disk or a bucket, and a range of it as a player asks.
        "calls.recordings",
    }
)
# A package inside a domain that other domains reach: by its `__init__`, which names exactly what they import.
SUBPACKAGES: frozenset[str] = frozenset({"calls.log", "calls.folds"})
# The files a domain folder holds, each a module or a package of the same name.
CANON_FILES = frozenset({"models", "schemas", "repository", "service", "auth", "endpoints", "tasks"})
# The modules a domain holds beside the canon's files: its long-lived objects and its value objects, each
# named in CONTRIBUTING.md. A domain enters here in the commit that builds it.
ENGINE_MODULES: dict[str, frozenset[str]] = {
    # Its two value objects (`VALUE_OBJECTS`).
    "providers": frozenset({"stage", "catalog"}),
    # Its two value objects (`VALUE_OBJECTS`).
    "agents": frozenset({"declaration", "settings"}),
    # No module: the pages Pinecall's own judges and personas are written in, one `.md` each, shipped in
    # the wheel and read once a process by `service/library.py`.
    "judging": frozenset({"library"}),
    # Its three value modules (`VALUE_OBJECTS`) and its engine, in two packages that cannot exist without it
    # and share its tables (calls-engine-1): `log/` writes, keeps, tells and reads a log (the writer, the store,
    # a log, the logs, the feeds, the relay, the fanout, the private values); `folds/` is what is folded from
    # one, pure functions of its entries (the state, the facts, the usage, the latencies, the phone legs).
    "calls": frozenset({"context", "projection", "recordings", "log", "folds"}),
    # An engine: the calls a gateway serves while they last, each module an object that lives for hours and
    # holds what is open now, or the one value those objects share. `service/` beside them is the use cases.
    "live": frozenset(
        {
            # Served, a call this gateway serves, and Calls: each one's socket, pump and commands, every org's count.
            "served",
            # Sockets: the app sockets open here and on the other gateways, their inboxes, the dev asks.
            "sockets",
            # Holders: who holds each agent on every gateway, the line of each, the developers' phones.
            "holders",
            # Every channel of the signal the gateways tell each other of a live call on, as a value; who runs what.
            "peers",
            # A bound call's pump: what any gateway writes to it, sent down its app socket in seq order.
            "pump",
            # ToolCalls: a call's tool calls to its app, through its log, each asked once and answered once.
            "tool_calls",
            # LiveParts: one of each thing a call served here reaches, the one value that carries them together (G-1).
            "parts",
        }
    ),
    # Harness: one of each thing a test call reaches, the one value of evals that carries them together, as
    # `LiveParts` is the live side's (G-1).
    "evals": frozenset({"parts"}),
    # An engine: one call running for as long as it lasts, each module an object that holds its state, or
    # the one noun those objects share. `service.py` beside them is what a host calls.
    "session": frozenset(
        {
            # Call: the state that outlives a turn, and the Protocols of what it reaches (the context, the platform).
            "call",
            # Writing: the call's entries in order, sent to its log in batches by one task.
            "writing",
            # Session: the call on livekit's AgentSession, built on its place: opened, heard, re-staged, ended.
            "session",
            # The one table of what each command does to a call, the envelope a stream is read with, the refusal.
            "commands",
            # Line: who has the line, and the agent's ears and voice with it.
            "line",
            # HoldMusic: the melody, its grace, when it sounded.
            "hold",
            # CallAgent: livekit's Agent with the hooks of a turn.
            "agent",
            # The prompt's blocks, the request of each turn, the greeting, a supervisor's notes.
            "prompt",
            # The history: how it opens, how it is rebuilt from a log, a note added to it.
            "history",
            # Toolbox: the app's tools, the lookups, a voicemail reached, end_call.
            "tools",
            # Lookups: recall and search before each turn, within a budget.
            "lookups",
            # What the ears are told: the turn policy, agreement, the agent heard back, the keyterms.
            "hearing",
            # What the agent said since the caller last spoke.
            "repeats",
            # The agent's words as they play: the entry, the lexicon read back.
            "transcript",
            # Listener: what livekit says, written as entries; the turn's times.
            "listener",
            # livekit's metrics and usage as the wire's.
            "metrics",
            # The stages a call runs: what was built, whether it is spoken, a vendor lost or back.
            "stages",
            # A session built for a spoken call, and one for a written call.
            "voice",
            "text",
            # CallRoom: who is in the room, the caller's codes, transfers, the room verbs.
            "room",
            # Widget: the DataChannel to a browser widget.
            "widget",
            # Recorder: the call's file and the other voices.
            "recording",
            # The caller's audio cleared of the agent's own voice.
            "echo",
            # A call's time: its ceiling, a chat's quiet, the idle lines.
            "clock",
            # The call.started entry.
            "started",
        }
    ),
}
# A `service/` package may hold this many modules; past it the domain is cut, or CONTRIBUTING.md says in a
# sentence why it is one context and the domain is named here with that sentence.
MOST_SERVICE_MODULES = 16
ONE_CONTEXT: dict[str, str] = {
    "providers": (
        "which vendor runs each stage of a call, on whose key, told what, at what price: one row, one table of keys "
        "and one registry of plugins, read by twenty of its modules; where an org's traces go and what this machine "
        "can run stand apart and were decided into it (compliance-1, providers-6)"
    ),
    "telephony": (
        "how a number reaches an agent and an agent a number: the account it lives in, by its kind, its fence, its "
        "trunk and rule on the SFU and its row are one thing read and written together; the routes and the legs in a "
        "call's room were decided into it (channels-1, telephony-3), and a kind of account is a module each"
    ),
    "live": (
        "a call while it is served: opened, bound to the app that holds its agent, commanded, ended once. Its "
        "twenty-one nouns read and move the same calls and sockets (`Calls`, `Sockets`, `Holders`); the WhatsApp "
        "threads, the dial, a visitor's way in with its tokens and codes, the supervisor's desk, the console's "
        "asks of a running app, the apps and the line were decided into it (calls-service-1 B, calls-service-4 A)"
    ),
    "evals": (
        "a test call placed against an agent and read after it: a golden run, a caller simulated, setups compared, "
        "a finished call checked again. Its twenty-four nouns stand on one seam (`Line`: written or spoken) and one "
        "skeleton of a played call; what a person asks of a judge that reads calls (a judge tried, a group "
        "diagnosed, callers written, the calibration) was decided into it (judging-1 A, judging-3 A, evals-1 A)"
    ),
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
