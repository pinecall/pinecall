"""The local model servers `setup` brings up for its choices, the models pulled into them, the row seeded."""

import json
import os
import subprocess
import urllib.request
from pathlib import Path
from shutil import which

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.cli.command import Context
from pinecall_runtime.cli.output import Printer
from pinecall_runtime.cli.setup_models import (
    LOCAL_EMBEDDER,
    LOCAL_STT,
    MODEL_PORTS,
    Choices,
    is_local,
    keys_for,
    model_of,
)
from pinecall_runtime.cli.setup_row import row_of
from pinecall_runtime.exceptions import Conflict, UpstreamError
from pinecall_runtime.providers import service as providers

MODELS_FAILED = "docker compose could not bring the models up:\n{output}"
PULL_FAILED = "pulling the models did not finish:\n{output}"
ROW_THERE = "row        the providers row is there already: left as it is (the console edits it)"


def models_up(where: Path, choices: Choices, *, host_ollama: bool) -> list[str]:
    """The local servers up and their models pulled once; the lines that say what runs where."""
    voice = [name for name, choice in (("whisper", choices.stt), ("kokoro", choices.tts)) if is_local(choice)]
    on_ollama = ", ".join((LOCAL_EMBEDDER, *choices.local_models))
    served = [f"Ollama :{MODEL_PORTS['Ollama']} ({on_ollama}){' on this machine' if host_ollama else ''}"]
    compose = ["docker", "compose", "-f", str(where / "models.yaml")]
    profiles = [*([] if host_ollama else ["--profile", "ollama"]), *(["--profile", "voice"] if voice else [])]
    ears = (model_of(choices.stt) if is_local(choices.stt) else None) or LOCAL_STT
    environment = {
        **os.environ,
        "LOCAL_LLM": choices.local_models[0] if choices.local_models else "",
        "LOCAL_STT": ears,
    }
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
    # The puller takes one model a run: each model the thinking, the judge or the caller names.
    pulls = [*([] if host_ollama else [("ollama-models", model) for model in choices.local_models])]
    if "whisper" in voice:
        pulls.append(("whisper-model", ""))
    for puller, model in pulls:
        pulled = subprocess.run(
            [*compose, *profiles, "run", "--rm", puller],
            capture_output=True,
            text=True,
            check=False,
            env={**environment, **({"LOCAL_LLM": model} if model else {})},
        )
        if pulled.returncode != 0:
            raise UpstreamError(PULL_FAILED.format(output=(pulled.stderr or pulled.stdout).strip()[-2000:]))
    if host_ollama:
        pull_on_host([LOCAL_EMBEDDER, *choices.local_models])
    if "whisper" in voice:
        served.append(f"Whisper :{MODEL_PORTS['Whisper']} ({ears})")
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
    served = models_up(where, choices, host_ollama=providers.answers(MODEL_PORTS["Ollama"]))
    out.line("models     " + " · ".join(served) + " — open models, no account")
    chosen = " · ".join(
        f"{choice} {stage}"
        for stage, choice in (
            ("hears", choices.stt),
            ("thinks", choices.llm),
            ("speaks", choices.tts),
            ("judges", choices.judging),
            ("calls", choices.calling),
        )
        if not is_local(choice)
    )
    if chosen:
        out.line(f"vendors    {chosen}" + (f" — read from the environment: {', '.join(read)}" if read else ""))
    out.line(f"turn       {choices.turn}")
    if choices.judge is not None or choices.caller is not None:
        out.line(f"judge      {choices.judging} · caller {choices.calling}")
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
