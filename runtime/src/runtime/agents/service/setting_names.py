"""Each setting by its names: as a class declares it, as the declaration's field, as the org's fields under it."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from runtime.agents.declaration import Agent
from runtime.agents.settings import FIELDS
from runtime.enums import Stage
from runtime.exceptions import Conflict


# "The class wins" was seven lists of the same fields in six files until 2026-11: what a class fixes,
# what an org's field is called in the declaration, which stage a changed field has tried, what a
# `words` key may touch, what a test room may change. A setting added to one and forgotten in another
# failed nothing: the org's field was dropped in silence. Every list is read off this table now, and a
# setting is one row.
@dataclass(frozen=True, slots=True)
class SettingNames:
    """One setting an agent has: how its class declares it, and how the org sets it underneath."""

    # In the declaration, as the wire names it: what `Declaration.fixed` holds.
    declared: str
    # The `Declaration`'s field it becomes.
    field: str
    # The `AgentSettings` fields that feed it; none: the class's alone, or the lexicon's.
    set_by: tuple[str, ...] = ()
    # The stages tried on their vendor when one of its fields moves.
    tries: tuple[Stage, ...] = ()
    # A `words` key (a supervisor's) may set it; the rest is the pipeline's.
    words: bool = False
    # Of its fields, the ones a test room may change for its own call.
    in_a_test: tuple[str, ...] = ()


SETTINGS: tuple[SettingNames, ...] = (
    SettingNames(
        "voice",
        "voice",
        ("voice", "tts", "tts_model", "tts_builds", "tts_options"),
        (Stage.tts,),
        in_a_test=("voice", "tts", "tts_model"),
    ),
    SettingNames(
        "llm",
        "llm",
        ("llm", "temperature", "llm_builds", "llm_options"),
        (Stage.llm,),
        in_a_test=("llm", "temperature"),
    ),
    SettingNames(
        "stt",
        "stt",
        ("stt", "stt_builds", "stt_options", "end_of_turn"),
        (Stage.stt,),
        in_a_test=("stt", "end_of_turn"),
    ),
    SettingNames("realtime", "realtime", ("realtime", "realtime_options")),
    SettingNames("judge", "judge", ("judge", "judge_builds", "judge_options")),
    SettingNames("turn", "turn", ("turn",), (Stage.stt,)),
    SettingNames("stt_fallbacks", "stt_fallbacks", ("stt_fallbacks",), (Stage.stt,)),
    SettingNames("tts_fallbacks", "tts_fallbacks", ("tts_fallbacks",), (Stage.tts,)),
    SettingNames("language", "language", ("language",), (Stage.tts, Stage.stt), in_a_test=("language",)),
    SettingNames("timezone", "timezone", ("timezone",)),
    SettingNames("greeting", "greeting", ("greeting",), words=True),
    SettingNames("hangup", "hangup", ("hangup",)),
    SettingNames("memory", "memory", ("memory",), words=True),
    SettingNames("record", "record", ("record",)),
    SettingNames("max_duration_s", "max_duration_s", ("max_duration_s",)),
    SettingNames("llm_timeout_s", "llm_timeout_s", ("llm_timeout_s",)),
    SettingNames("silence_timeout_s", "silence_timeout_s", ("silence_timeout_s",)),
    SettingNames("idle", "idle", ("idle",)),
    SettingNames("voicemail", "voicemail", ("voicemail",)),
    SettingNames("knowledge", "knowledge", ("knowledge",), words=True),
    # `bases` is `docs` said for several: one setting, however the class says it.
    SettingNames("docs", "bases", ("bases",)),
    # The lexicon's, set in versions of their own.
    SettingNames("says", "says"),
    SettingNames("hears", "hears"),
    # The class's alone: declared, no endpoint writes them.
    SettingNames("judges", "judges"),
    SettingNames("personas", "personas"),
    SettingNames("hold", "hold"),
    SettingNames("widget", "widget"),
    SettingNames("monitors", "monitors"),
)

# The declaration's field of each setting a class may declare.
FIELD_OF: dict[str, str] = {one.declared: one.field for one in SETTINGS}
# Every field of the org's settings by its name in the declaration.
DECLARED_AS: dict[str, str] = {name: one.declared for one in SETTINGS for name in one.set_by}
# A write that changes one of a stage's fields has the stage tried before it is kept.
STAGE_FIELDS: dict[Stage, tuple[str, ...]] = {
    stage: tuple(name for one in SETTINGS if stage in one.tries for name in one.set_by)
    for stage in (Stage.tts, Stage.llm, Stage.stt)
}
REALTIME_FIELDS: tuple[str, ...] = next(one.set_by for one in SETTINGS if one.declared == "realtime")
JUDGE_FIELDS: tuple[str, ...] = next(one.set_by for one in SETTINGS if one.declared == "judge")
# A `words` key sets the opening's words, what is remembered and the knowledge; the rest is the pipeline's.
WORDS_FIELDS: frozenset[str] = frozenset(name for one in SETTINGS if one.words for name in one.set_by)
PIPELINE_ONLY: tuple[str, ...] = tuple(name for name in FIELDS if name not in WORDS_FIELDS)
# What a test room may change for its own call: the voice, the models and the language they run in.
TEST_FIELDS: frozenset[str] = frozenset(name for one in SETTINGS for name in one.in_a_test)


class SetByTheClass(Conflict):
    """The class's declaration wins over a setting it declares."""

    def __init__(self, fields: Collection[str], slug: str) -> None:
        super().__init__(
            f"{', '.join(sorted(fields))} set by the class of {slug}: the class's declaration wins over these "
            "settings, so change it there, or take it out of the class to set it here"
        )


# A field of the org's settings is named as the org sets it (`tts_model`); a setting that is the class's
# alone or the lexicon's by its own name (`hold`, `widget`, `says`).
def refuse_what_the_class_sets(agent: Agent, fields: Sequence[str]) -> None:
    """Refuse a write that changes what the class of the agent declares."""
    taken = {DECLARED_AS.get(name, name) for name in fields} & agent.fixed
    if taken:
        raise SetByTheClass(taken, agent.slug)
