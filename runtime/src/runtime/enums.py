"""The enumerations the tables and the API share, each as the database spells it."""

from enum import StrEnum


class Env(StrEnum):
    """One of an org's two environments. A key, a number and a call belong to one."""

    production = "production"
    sandbox = "sandbox"

    @property
    def other(self) -> "Env":
        """The env that is not this one."""
        return Env.sandbox if self is Env.production else Env.production


class Channel(StrEnum):
    """Where a conversation comes in: SIP into a room, the widget over WebRTC, or text."""

    phone = "phone"
    web = "web"
    whatsapp = "whatsapp"

    @property
    def has_a_number(self) -> bool:
        """Whether a route on this channel answers at a phone number."""
        return self in (Channel.phone, Channel.whatsapp)


class Medium(StrEnum):
    """How a call is had: spoken in a room, or written."""

    voice = "voice"
    text = "text"


class Direction(StrEnum):
    """Who called whom."""

    inbound = "inbound"
    outbound = "outbound"


class Role(StrEnum):
    """A member's role: a preset of key scopes, read when their key is minted."""

    qa = "qa"
    supervisor = "supervisor"
    manager = "manager"
    admin = "admin"
    developer = "developer"


class KeyScope(StrEnum):
    """What a key opens. Endpoints check scopes, never roles."""

    app = "app"
    calls = "calls"
    talk = "talk"
    supervise = "supervise"
    pipeline = "pipeline"
    knowledge = "knowledge"
    memory = "memory"
    evals = "evals"
    numbers = "numbers"
    keys = "keys"
    providers = "providers"
    team = "team"
    usage = "usage"
    words = "words"
    fleet = "fleet"
    runner = "runner"


class RouteOrigin(StrEnum):
    """How a number's row was written."""

    bought = "bought"
    imported = "imported"
    hooked = "hooked"
    typed = "typed"


class ConsentKind(StrEnum):
    """A fact about a number: consent given, or an opt-out."""

    express = "express"
    written = "written"
    opt_out = "opt_out"


class ReadKind(StrEnum):
    """What was read: the access log's subject kinds."""

    log = "log"
    recording = "recording"
    traceback = "traceback"
    listen = "listen"
    supervise = "supervise"
    export = "export"
    memory = "memory"


class CaseStatus(StrEnum):
    """A case or a case group waiting for a person."""

    pending = "pending"
    approved = "approved"
    dismissed = "dismissed"


class JudgeAnswer(StrEnum):
    """How an org's judge answers."""

    verdict = "verdict"
    choice = "choice"
    score = "score"


class JudgeRunsWhen(StrEnum):
    """When an org's judge runs."""

    always = "always"
    simulations = "simulations"
    trigger = "trigger"


class Stage(StrEnum):
    """The three stages of a spoken call."""

    stt = "stt"
    llm = "llm"
    tts = "tts"


class HoldPlayed(StrEnum):
    """What an agent plays while a tool runs: the runtime's melody, nothing, or the org's clip."""

    default = "default"
    off = "off"
    custom = "custom"


class MonitorMetric(StrEnum):
    """The numbers of the series a monitor may watch."""

    e2e_median_s = "e2e_median_s"
    llm_median_s = "llm_median_s"
    held_rate = "held_rate"
    escalated_rate = "escalated_rate"
    tool_failure_rate = "tool_failure_rate"
    spend_usd = "spend_usd"
    calls = "calls"
