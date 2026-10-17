"""What `setup` runs a call on, stage by stage: an open model on this machine or a vendor of yours; the row for it."""

import json
import os
import socket
import subprocess
import urllib.request
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from shutil import which
from typing import Literal

import typer

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.cli.command import Context
from pinecall_runtime.cli.output import Printer
from pinecall_runtime.exceptions import Conflict, UpstreamError, ValidationError
from pinecall_runtime.providers import service as providers

# The word for an open model on this machine, in any stage's answer.
LOCAL = "local"
type Turn = Literal["stt", "smart-turn", "livekit"]
# How the end of the caller's turn is read: the ears' own endpointing, or a model on the worker's CPU.
TURNS: tuple[Turn, ...] = ("stt", "smart-turn", "livekit")
TURN_MODELS: dict[Turn, str | None] = {"stt": None, "smart-turn": "smart-turn-v3", "livekit": "v1-mini"}

# Open models on this machine, through the `openai` plugin and a `base_url` per stage (DEV-FIRST.md).
LOCAL_LLM = "qwen3:4b"
LOCAL_STT = "deepdml/faster-whisper-large-v3-turbo-ct2"
LOCAL_TTS = "kokoro"
# The embedder is always local: changing it would blind every base and every memory.
LOCAL_EMBEDDER = "bge-m3"
# The three servers, on loopback, as `providers.local.json` reaches them.
MODEL_PORTS = {"Ollama": 11434, "Whisper": 8000, "Kokoro": 8880}
# What the local servers ask for a key: nothing; the plugin wants one, so the org holds this word.
NO_KEY_NEEDED = "local"
# The vendors `--models keys` means when no stage is named.
KEYS_DEFAULTS = {"stt": "deepgram", "llm": "anthropic", "tts": "cartesia"}
MODELS_FAILED = "docker compose could not bring the models up:\n{output}"
PULL_FAILED = "pulling the models did not finish:\n{output}"
ROW_THERE = "row        the providers row is there already: left as it is (the console edits it)"
NO_KEY_FOR = "{vendor} needs a key: set {variable}, or answer when asked at a terminal"
WHISPER_ENDS_NO_TURN = "the local ears (Whisper) end no turn themselves: --turn smart-turn or livekit"


@dataclass(frozen=True)
class Choices:
    """One vendor or `local` per stage, and who reads the end of the caller's turn."""

    stt: str = LOCAL
    turn: Turn = "smart-turn"
    llm: str = LOCAL
    tts: str = LOCAL

    @property
    def vendors(self) -> frozenset[str]:
        """The vendors of yours among the choices."""
        return frozenset(vendor_of(choice) for choice in (self.stt, self.llm, self.tts) if choice != LOCAL)


# A choice names a vendor, or a vendor and the model it runs: `hf/Qwen/Qwen2.5-3B-Instruct`.
def vendor_of(choice: str) -> str:
    """The vendor a choice names."""
    return choice.partition("/")[0]


def model_of(choice: str) -> str | None:
    """The model a choice names after its vendor, if any."""
    _, _, model = choice.partition("/")
    return model or None


ALL_LOCAL = Choices()
ALL_KEYS = Choices(stt=KEYS_DEFAULTS["stt"], turn="stt", llm=KEYS_DEFAULTS["llm"], tts=KEYS_DEFAULTS["tts"])


def turn_of(text: str) -> Turn:
    """The turn a flag or an answer names, one of three."""
    named = text.strip().lower()
    if named not in TURNS:
        raise ValidationError(f"--turn is one of {', '.join(TURNS)}, not {text!r}")
    return named


def check_choices(choices: Choices) -> Choices:
    """Each vendor installed and doing its stage; the turn one the ears can read."""
    stages: tuple[tuple[Modality, str], ...] = (("stt", choices.stt), ("llm", choices.llm), ("tts", choices.tts))
    for stage, choice in stages:
        if choice != LOCAL:
            providers.vendor_doing(vendor_of(choice), stage)
    if choices.turn not in TURNS:
        raise ValidationError(f"--turn is one of {', '.join(TURNS)}, not {choices.turn!r}")
    if choices.turn == "stt" and (choices.stt == LOCAL or not providers.ends_turns(vendor_of(choices.stt))):
        who = "the local ears (Whisper)" if choices.stt == LOCAL else choices.stt
        raise ValidationError(f"{who} end no turn themselves: --turn smart-turn or livekit")
    return choices


def ask_choices() -> Choices:
    """The four questions, at a terminal: each stage's list is what this build runs."""
    stt = _ask("ears: who hears the caller?", "stt")
    turns = [turn for turn in TURNS if turn != "stt" or (stt != LOCAL and providers.ends_turns(stt))]
    turn = typer.prompt(f"end of turn: {' · '.join(turns)}", default="stt" if "stt" in turns else "smart-turn")
    llm = _ask("thinking: which model?", "llm")
    tts = _ask("voice: who speaks?", "tts")
    return check_choices(Choices(stt=stt, turn=turn.strip(), llm=llm, tts=tts))


def _ask(question: str, stage: str) -> str:
    listed = sorted(
        name for name, vendor in providers.installed().items() if vendor.broken is None and stage in vendor.does
    )
    answer: str = typer.prompt(f"{question}  {LOCAL} · {' · '.join(listed)}", default=LOCAL)
    return answer.strip().lower()


# ── the row ──


def row_of(choices: Choices) -> providers.Catalog:
    """The providers row for the choices: local stages on the openai plugin and a base_url each, vendors bare."""
    text = files("pinecall_runtime.cli").joinpath("local", "providers.local.json").read_text(encoding="utf-8")
    shipped = json.loads(text.replace("LOCAL_LLM", LOCAL_LLM).replace("LOCAL_STT", LOCAL_STT))
    row: dict[str, object] = {"rates": shipped["rates"], "embedding": shipped["embedding"]}
    defaults: dict[str, dict[str, str]] = {}
    tuning: dict[str, dict[str, object]] = {}
    for stage, choice in (("stt", choices.stt), ("llm", choices.llm), ("tts", choices.tts)):
        if choice == LOCAL:
            defaults[stage] = shipped["defaults"][stage]
            tuning[f"{stage}/openai"] = dict(shipped["tuning"][f"{stage}/openai"])
        else:
            defaults[stage] = {"vendor": vendor_of(choice), **({"model": model} if (model := model_of(choice)) else {})}
    model = TURN_MODELS[choices.turn]
    stt_key = f"stt/{'openai' if choices.stt == LOCAL else vendor_of(choices.stt)}"
    turned = {k: v for k, v in tuning.get(stt_key, {}).items() if k != "turn_model"}
    if model is not None:
        turned["turn_model"] = model
    if turned:
        tuning[stt_key] = turned
    elif stt_key in tuning:
        del tuning[stt_key]
    thinking = defaults["llm"]
    row.update(
        defaults=defaults,
        tuning=tuning,
        voices=shipped["voices"] if choices.tts == LOCAL else {},
        judge={"llm": thinking, "ceiling_usd": shipped["judge"]["ceiling_usd"]},
        caller={"llm": thinking, "ceiling_usd": shipped["caller"]["ceiling_usd"]},
    )
    return providers.Catalog.model_validate(row)


# ── the keys ──


def key_variable(vendor: str) -> str:
    """The environment variable a vendor's key is read from: `DEEPGRAM_API_KEY`."""
    return f"{vendor.upper().replace('-', '_')}_API_KEY"


def keys_for(choices: Choices, *, asking: bool) -> tuple[dict[str, str], list[str]]:
    """Each chosen vendor's key, from its variable or asked once; and which came from the environment."""
    given: dict[str, str] = {}
    read: list[str] = []
    for vendor in sorted(choices.vendors):
        if not providers.takes_a_key(vendor):
            continue
        variable = key_variable(vendor)
        found = os.environ.get(variable, "").strip()
        if found:
            given[vendor] = found
            read.append(variable)
        elif asking:
            typed = typer.prompt(variable, hide_input=True, show_default=False).strip()
            if not typed:
                raise ValidationError(NO_KEY_FOR.format(vendor=vendor, variable=variable))
            given[vendor] = typed
        else:
            raise ValidationError(NO_KEY_FOR.format(vendor=vendor, variable=variable))
    # The embedder is local, on the openai plugin, whatever the stages: the plugin wants a key.
    given.setdefault("openai", NO_KEY_NEEDED)
    return given, read


# ── the servers ──


def models_up(where: Path, choices: Choices, *, host_ollama: bool) -> list[str]:
    """The local servers up and their models pulled once; the lines that say what runs where."""
    voice = [name for name, choice in (("whisper", choices.stt), ("kokoro", choices.tts)) if choice == LOCAL]
    on_ollama = LOCAL_EMBEDDER + (f", {LOCAL_LLM}" if choices.llm == LOCAL else "")
    served = [f"Ollama :{MODEL_PORTS['Ollama']} ({on_ollama}){' on this machine' if host_ollama else ''}"]
    compose = ["docker", "compose", "-f", str(where / "models.yaml")]
    profiles = [*([] if host_ollama else ["--profile", "ollama"]), *(["--profile", "voice"] if voice else [])]
    environment = {**os.environ, "LOCAL_LLM": LOCAL_LLM, "LOCAL_STT": LOCAL_STT}
    serving = [*([] if host_ollama else ["ollama"]), *voice]
    if serving:
        up = subprocess.run(
            [*compose, *profiles, "up", "-d", "--wait", *serving],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        if up.returncode != 0:
            raise UpstreamError(MODELS_FAILED.format(output=(up.stderr or up.stdout).strip()[-2000:]))
    pulls = [*([] if host_ollama else ["ollama-models"]), *(["whisper-model"] if "whisper" in voice else [])]
    for puller in pulls:
        pulled = subprocess.run(
            [*compose, *profiles, "run", "--rm", puller], capture_output=True, text=True, check=False, env=environment
        )
        if pulled.returncode != 0:
            raise UpstreamError(PULL_FAILED.format(output=(pulled.stderr or pulled.stdout).strip()[-2000:]))
    if host_ollama:
        pull_on_host([LOCAL_EMBEDDER, *([LOCAL_LLM] if choices.llm == LOCAL else [])])
    if "whisper" in voice:
        served.append(f"Whisper :{MODEL_PORTS['Whisper']}")
    if "kokoro" in voice:
        served.append(f"Kokoro :{MODEL_PORTS['Kokoro']}")
    return served


def pull_on_host(models: list[str]) -> None:
    """The models pulled by the Ollama this machine already runs."""
    if which("ollama") is None:
        raise UpstreamError(
            f"something answers on :{MODEL_PORTS['Ollama']} but `ollama` is not on PATH: pull {', '.join(models)} there"
        )
    for model in models:
        pulled = subprocess.run(["ollama", "pull", model], capture_output=True, text=True, check=False)
        if pulled.returncode != 0:
            raise UpstreamError(PULL_FAILED.format(output=(pulled.stderr or pulled.stdout).strip()[-2000:]))


def answers(port: int) -> bool:
    """Whether something accepts a connection on that loopback port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


# A turn's lookup waits 3 s for its search; the embedder's first request after a start loads the
# model (3.4 s for bge-m3 on an L4, longer on a CPU), so the first caller's search would miss.
def warm_embedder() -> None:
    """One embedding asked of Ollama, so bge-m3 is loaded before the first call searches."""
    body = json.dumps({"model": LOCAL_EMBEDDER, "input": ["warm"], "encoding_format": "float", "dimensions": 1024})
    asked = urllib.request.Request(
        f"http://127.0.0.1:{MODEL_PORTS['Ollama']}/v1/embeddings",
        data=body.encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(asked, timeout=120):
            pass
    except OSError as failed:
        raise UpstreamError(f"Ollama did not embed with {LOCAL_EMBEDDER}: {failed}") from failed


# ── all of it ──


async def models(runtime: Context, where: Path, choices: Choices, *, asking: bool, out: Printer) -> None:
    """The servers the choices need up, the keys they need kept, the row written: what `setup` does for the models."""
    keys, read = keys_for(choices, asking=asking)
    served = models_up(where, choices, host_ollama=answers(MODEL_PORTS["Ollama"]))
    out.line("models     " + " · ".join(served) + " — open models, no account")
    chosen = " · ".join(
        f"{vendor} {stage}"
        for stage, vendor in (("hears", choices.stt), ("thinks", choices.llm), ("speaks", choices.tts))
        if vendor != LOCAL
    )
    if chosen:
        out.line(f"vendors    {chosen}" + (f" — read from the environment: {', '.join(read)}" if read else ""))
    out.line(f"turn       {choices.turn}")
    await seed(runtime, row_of(choices), keys, out)
    warm_embedder()


async def seed(runtime: Context, row: providers.Catalog, credentials: dict[str, str], out: Printer) -> None:
    """The row written unless one is there; each vendor's key given to the org `default` and held by the box."""
    async with runtime.sessions.begin() as session:
        try:
            await providers.seed_catalog(session, row)
            out.line("row        the providers row written: the console edits it from now on")
        except Conflict:
            out.line(ROW_THERE)
    # The box holds the same keys: the judges at hang-up and the embedder run on the box's, never
    # on an org's, and this machine is both the box and the org.
    async with runtime.sessions.begin() as session:
        found = await orgs.get_org(session, DEFAULT_ORG)
        for vendor, secret in credentials.items():
            named = providers.installed_vendor(vendor)
            await providers.put_own_credentials(session, runtime.vault, found.id, named, secret)
            await providers.put_box_credentials(session, runtime.vault, named, secret)
