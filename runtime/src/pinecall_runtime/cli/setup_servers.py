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
    serving = [*([] if host_ollama else ["ollama"]), *voice]
    # Started (a service this release no longer names is taken down), the models pulled into them, then
    # waited for: Ollama is healthy once its model answers.
    if serving:
        _compose(compose, profiles, ["up", "-d", "--remove-orphans", *serving], environment, MODELS_FAILED)
    # The puller takes one model a run: each model the thinking, the judge or the caller names.
    pulls = [*([] if host_ollama else [("ollama-models", model) for model in choices.local_models])]
    if "whisper" in voice:
        pulls.append(("whisper-model", ""))
    for puller, model in pulls:
        pulled = {**environment, **({"LOCAL_LLM": model} if model else {})}
        _compose(compose, profiles, ["run", "--rm", puller], pulled, PULL_FAILED)
    if serving:
        _compose(compose, profiles, ["up", "-d", "--wait", *serving], environment, MODELS_FAILED)
    if host_ollama:
        pull_on_host([LOCAL_EMBEDDER, *choices.local_models])
        warm_on_host(choices.local_models)
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


# A Mac's own Ollama is warmed by setup alone: the container's healthcheck does it for the one setup runs.
def warm_on_host(models: tuple[str, ...]) -> None:
    """One short answer asked of each open model that thinks on this machine's own Ollama."""
    for model in models:
        warmed = subprocess.run(
            ["ollama", "run", "--think=false", model, "hi"], capture_output=True, text=True, check=False
        )
        if warmed.returncode != 0:
            raise UpstreamError(PULL_FAILED.format(output=(warmed.stderr or warmed.stdout).strip()[-2000:]))


def _compose(
    compose: list[str], profiles: list[str], verb: list[str], environment: dict[str, str], failed: str
) -> None:
    done = subprocess.run([*compose, *profiles, *verb], capture_output=True, text=True, check=False, env=environment)
    if done.returncode != 0:
        raise UpstreamError(failed.format(output=(done.stderr or done.stdout).strip()[-2000:]))


async def models(runtime: Context, where: Path, choices: Choices, keys: dict[str, str], *, card: bool) -> None:
    """The servers the choices need up, on the card when there is one, the keys kept, the row written."""
    # An Ollama answering is this machine's own only when it is not the one an earlier setup started.
    host_ollama = providers.answers(MODEL_PORTS["Ollama"]) and not ours_running(where, "ollama")
    models_up(where, choices, host_ollama=host_ollama, card=card)
    await seed(runtime, row_of(choices), keys)
    warm_embedder()


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
