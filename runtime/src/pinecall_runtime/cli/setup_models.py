"""What `setup` runs a call on: open models on this machine, or the vendors' own keys; the row seeded for either."""

import json
import os
import socket
import subprocess
import urllib.request
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from shutil import which

import typer

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.cli.command import Context
from pinecall_runtime.cli.output import Printer
from pinecall_runtime.exceptions import Conflict, UpstreamError, ValidationError
from pinecall_runtime.providers import service as providers


class Models(StrEnum):
    """Where a call's ears, model and voice come from."""

    local = "local"
    keys = "keys"
    none = "none"


# Open models on this machine, through the `openai` plugin and a `base_url` per stage. Provisional
# until the P0 measurements name them (DEV-FIRST.md): the LLM must call tools, in Spanish, on a CPU.
LOCAL_LLM = "qwen3:4b"
LOCAL_STT = "deepdml/faster-whisper-large-v3-turbo-ct2"
# The three servers, on loopback, as `providers.local.json` reaches them.
MODEL_PORTS = {"Ollama": 11434, "Whisper": 8000, "Kokoro": 8880}
# What the servers ask for a key: nothing; the plugin wants one, so the org holds this word.
NO_KEY_NEEDED = "local"
# The vendors `--models keys` runs on, and the variable each key is read from.
KEY_VARIABLES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepgram": "DEEPGRAM_API_KEY",
    "cartesia": "CARTESIA_API_KEY",
}

MODELS_FAILED = "docker compose could not bring the models up:\n{output}"
PULL_FAILED = "pulling the models did not finish:\n{output}"
ROW_THERE = "row        the providers row is there already: left as it is (the console edits it)"
ASK_MODELS = (
    "models: local (open models on this machine, no account, ~4 GB pulled once) · "
    "keys (your vendors' keys) · none (the row is yours)"
)
NO_KEY_GIVEN = (
    "no key given: set OPENAI_API_KEY or ANTHROPIC_API_KEY (and DEEPGRAM_API_KEY, CARTESIA_API_KEY "
    "for voice), or answer the questions"
)


def ask_models() -> Models:
    """The one question `setup` asks, at a terminal."""
    answer = typer.prompt(ASK_MODELS, default=Models.local.value)
    try:
        return Models(answer.strip().lower())
    except ValueError:
        raise ValidationError(f"models is local, keys or none, not {answer!r}") from None


# ── open models on this machine ──


async def local_models(runtime: Context, where: Path, llm: str, chat_only: bool, out: Printer) -> None:
    """The servers up, the models pulled once, the row written for them, the org given the one word they take."""
    host_ollama = answers(MODEL_PORTS["Ollama"])
    models_up(where, llm, chat_only=chat_only, host_ollama=host_ollama)
    if host_ollama:
        pull_on_host(llm)
    served = [f"Ollama :{MODEL_PORTS['Ollama']} ({llm}, bge-m3){' on this machine' if host_ollama else ''}"]
    if not chat_only:
        served += [f"Whisper :{MODEL_PORTS['Whisper']}", f"Kokoro :{MODEL_PORTS['Kokoro']}"]
    out.line("models     " + " · ".join(served) + " — open models, no account")
    await seed(runtime, local_row(llm, LOCAL_STT, chat_only=chat_only), {"openai": NO_KEY_NEEDED}, out)
    warm_embedder()


# A turn's lookup waits 3 s for its search; the embedder's first request after a start loads the
# model (3.4 s for bge-m3 on an L4, longer on a CPU), so the first caller's search would miss.
# Measured on the GPU test machine, 2026-10-17.
def warm_embedder() -> None:
    """One embedding asked of Ollama, so bge-m3 is loaded before the first call searches."""
    body = json.dumps({"model": "bge-m3", "input": ["warm"], "encoding_format": "float", "dimensions": 1024})
    asked = urllib.request.Request(
        f"http://127.0.0.1:{MODEL_PORTS['Ollama']}/v1/embeddings",
        data=body.encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(asked, timeout=120):
            pass
    except OSError as failed:
        raise UpstreamError(f"Ollama did not embed with bge-m3: {failed}") from failed


def local_row(llm: str, stt: str, *, chat_only: bool) -> providers.Catalog:
    """The row the package ships for the local models, these two named; chat alone keeps no ears and no voice."""
    text = files("pinecall_runtime.cli").joinpath("local", "providers.local.json").read_text(encoding="utf-8")
    row = json.loads(text.replace("LOCAL_LLM", llm).replace("LOCAL_STT", stt))
    if chat_only:
        row["defaults"] = {"llm": row["defaults"]["llm"]}
        row["tuning"] = {"llm/openai": row["tuning"]["llm/openai"]}
        row.pop("voices", None)
    return providers.Catalog.model_validate(row)


def models_up(where: Path, llm: str, *, chat_only: bool, host_ollama: bool) -> None:
    """The servers up and their models pulled once: no Ollama where the machine has its own, no voice for chat alone."""
    profiles = [*([] if host_ollama else ["--profile", "ollama"]), *([] if chat_only else ["--profile", "voice"])]
    if not profiles:
        return
    compose = ["docker", "compose", "-f", str(where / "models.yaml"), *profiles]
    environment = {**os.environ, "LOCAL_LLM": llm, "LOCAL_STT": LOCAL_STT}
    serving = [*([] if host_ollama else ["ollama"]), *([] if chat_only else ["whisper", "kokoro"])]
    up = subprocess.run(
        [*compose, "up", "-d", "--wait", *serving], capture_output=True, text=True, check=False, env=environment
    )
    if up.returncode != 0:
        raise UpstreamError(MODELS_FAILED.format(output=(up.stderr or up.stdout).strip()[-2000:]))
    pulls = [*([] if host_ollama else ["ollama-models"]), *([] if chat_only else ["whisper-model"])]
    for puller in pulls:
        pulled = subprocess.run(
            [*compose, "run", "--rm", puller], capture_output=True, text=True, check=False, env=environment
        )
        if pulled.returncode != 0:
            raise UpstreamError(PULL_FAILED.format(output=(pulled.stderr or pulled.stdout).strip()[-2000:]))


def pull_on_host(llm: str) -> None:
    """The two models pulled by the Ollama this machine already runs."""
    if which("ollama") is None:
        raise UpstreamError(
            f"something answers on :{MODEL_PORTS['Ollama']} but `ollama` is not on PATH: pull {llm} and bge-m3 there"
        )
    for model in (llm, "bge-m3"):
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


# ── the vendors' own keys ──


async def vendor_keys(runtime: Context, asking: bool, out: Printer) -> None:
    """The keys read from the environment, the missing ones asked at a terminal, the row written for those keyed."""
    given = {vendor: os.environ[variable] for vendor, variable in KEY_VARIABLES.items() if os.environ.get(variable)}
    if asking:
        for vendor, variable in KEY_VARIABLES.items():
            if vendor not in given:
                typed = typer.prompt(f"{variable} (blank to skip)", default="", hide_input=True, show_default=False)
                if typed.strip():
                    given[vendor] = typed.strip()
    if not given:
        raise ValidationError(NO_KEY_GIVEN)
    row = keys_row(frozenset(given))
    out.line("keys       " + " · ".join(sorted(given)) + (f" — {missing}" if (missing := missing_stages(row)) else ""))
    await seed(runtime, row, given, out)


def keys_row(vendors: frozenset[str]) -> providers.Catalog:
    """The row for the vendors keyed: Anthropic thinks when keyed, else OpenAI; Deepgram hears; Cartesia speaks."""
    defaults: dict[str, dict[str, str]] = {}
    if "anthropic" in vendors:
        defaults["llm"] = {"vendor": "anthropic"}
    elif "openai" in vendors:
        defaults["llm"] = {"vendor": "openai"}
    if "deepgram" in vendors:
        defaults["stt"] = {"vendor": "deepgram"}
    if "cartesia" in vendors:
        defaults["tts"] = {"vendor": "cartesia"}
    return providers.Catalog.model_validate({"defaults": defaults})


def missing_stages(row: providers.Catalog) -> str:
    """What the row cannot do yet, in one clause; empty when it can hear, think and speak."""
    missing = [stage for stage in ("llm", "stt", "tts") if stage not in row.defaults]
    if not missing:
        return ""
    words = {"llm": "no model to think with: chat needs one", "stt": "no ears", "tts": "no voice"}
    return "; ".join(words[stage] for stage in missing)


# ── the row ──


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
