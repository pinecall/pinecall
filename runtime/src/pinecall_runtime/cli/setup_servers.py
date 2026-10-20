"""The local model servers `setup` brings up for its choices, the models pulled into them, the row seeded."""

import contextlib
import json
import os
import subprocess
import urllib.request
from pathlib import Path
from shutil import which

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.cli.command import Context
from pinecall_runtime.cli.setup_models import LOCAL_EMBEDDER, LOCAL_STT, MODEL_PORTS, Choices, is_local, model_of
from pinecall_runtime.cli.setup_row import row_of
from pinecall_runtime.exceptions import Conflict, UpstreamError
from pinecall_runtime.providers import service as providers

MODELS_FAILED = "docker compose could not bring the models up:\n{output}"
PULL_FAILED = "pulling the models did not finish:\n{output}"


def models_up(where: Path, choices: Choices, *, host_ollama: bool, card: bool = False) -> list[str]:
    """The local servers up, on the card when there is one, and their models pulled once; what runs where."""
    voice = [name for name, choice in (("whisper", choices.stt), ("kokoro", choices.tts)) if is_local(choice)]
    on_ollama = ", ".join((LOCAL_EMBEDDER, *choices.local_models))
    served = [f"Ollama :{MODEL_PORTS['Ollama']} ({on_ollama}){' on this machine' if host_ollama else ''}"]
    compose = [
        "docker",
        "compose",
        "--progress",
        "quiet",
        "-f",
        str(where / "models.yaml"),
        *(["-f", str(where / "models.gpu.yaml")] if card else []),
    ]
    profiles = [*([] if host_ollama else ["--profile", "ollama"]), *(["--profile", "voice"] if voice else [])]
    ears = (model_of(choices.stt) if is_local(choices.stt) else None) or LOCAL_STT
    environment = {
        **os.environ,
        "LOCAL_LLM": choices.local_models[0] if choices.local_models else "",
        "LOCAL_STT": ears,
    }
    serving = [*([] if host_ollama else ["ollama", "ollama-warm"]), *voice]
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


def ours_running(where: Path, service: str) -> bool:
    """Whether the models' compose already runs that service: what answers on its port is setup's own."""
    listed = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(where / "models.yaml"),
            "--profile",
            "ollama",
            "--profile",
            "voice",
            "ps",
            "--status",
            "running",
            "--quiet",
            service,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return listed.returncode == 0 and bool(listed.stdout.strip())


def a_card_for_docker() -> bool:
    """Whether this machine has an NVIDIA card and Docker can hand it to a container."""
    if which("nvidia-smi") is None:
        return False
    runtimes = subprocess.run(
        ["docker", "info", "--format", "{{json .Runtimes}}"], capture_output=True, text=True, check=False
    )
    return runtimes.returncode == 0 and "nvidia" in runtimes.stdout


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


# The first answer of a model Ollama just loaded waits for the card's kernels to be built: ~30 s for
# gemma4:12b on an L4 (2026-10-20), and a call waits 10 s for a model. One word asked of each,
# before setup says ready, so the first caller is answered as fast as the hundredth.
def warm_thinking(models: tuple[str, ...]) -> None:
    """One short answer asked of each open model that thinks, so none is cold when the first call comes."""
    for model in models:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
            "reasoning_effort": "none",
        }
        asked = urllib.request.Request(
            f"http://127.0.0.1:{MODEL_PORTS['Ollama']}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(asked, timeout=300):
                pass
        except OSError as failed:
            raise UpstreamError(f"Ollama did not answer with {model}: {failed}") from failed


async def models(runtime: Context, where: Path, choices: Choices, keys: dict[str, str], *, card: bool) -> None:
    """The servers the choices need up, on the card when there is one, the keys kept, the row written."""
    # An Ollama answering is this machine's own only when it is not the one an earlier setup started.
    host_ollama = providers.answers(MODEL_PORTS["Ollama"]) and not ours_running(where, "ollama")
    models_up(where, choices, host_ollama=host_ollama, card=card)
    await seed(runtime, row_of(choices), keys)
    warm_embedder()
    warm_thinking(choices.local_models)


async def seed(runtime: Context, row: providers.Catalog, credentials: dict[str, str]) -> None:
    """The row written unless one is there (the console edits it after); each key given to `default` and the runtime."""
    async with runtime.sessions.begin() as session:
        with contextlib.suppress(Conflict):
            await providers.seed_catalog(session, row)
    # The runtime holds the same keys and lends them: the judges at hang-up and the embedder run on
    # the runtime's, never on an org's, and every org made later runs on them until it brings its own.
    async with runtime.sessions.begin() as session:
        found = await orgs.get_org(session, DEFAULT_ORG)
        for vendor, secret in credentials.items():
            named = providers.installed_vendor(vendor)
            await providers.put_own_credentials(session, runtime.vault, found.id, named, secret)
            await providers.put_box_credentials(session, runtime.vault, named, secret)
