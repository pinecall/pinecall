# Production

How a Python agent runs where its callers reach it. There are three ways: inside your own app, as
a process of its own on your server, or on Pinecall's servers.

## The server's token

A server runs on a **server's token**, minted for production in the console's API keys screen
(under the org's Settings). It was made for one world and opens that one alone: put it in the server's
secrets as `PINECALL_KEY`, never in the repository. A person's key works too while their
production switch is on, but a server should not run on a person.

## (a) Inside your own Python app

When the app is already a Python process that stays up — a FastAPI service, a worker — the agent
can live in it. `pinecall.hold` mounts the class on a client of its own, connects, and hands back
what it holds; `stop` drains the calls to the next holder and closes:

```python
import os

import pinecall

from clinica.agent import ClinicaNorte  # a module of your app, like any other


async def lifespan(app):
    held = await pinecall.hold(
        ClinicaNorte, url="https://cloud.pinecall.io", api_key=os.environ["PINECALL_KEY"]
    )
    yield
    await held.stop()  # the live calls are handed over, not cut
```

`pinecall.Client` reads nothing from the environment: the app hands it the gateway and the key it
keeps. A person's key would need `env="production"`; a server's token needs nothing. The class
registers under its own `slug`, or its name in kebab-case, and its view is `views/<slug>.jinja` beside
the module's file.

## (b) `pinecall start --prod`, from the one CLI

The `pinecall` command is the Node CLI (`npm i -g pinecall`), for every language. In the project's
folder it finds `agents/<name>/agent.py`, and `pinecall start --prod` starts this package's serve
entry with the project's own interpreter — `.venv/bin/python -m pinecall.serve start …` when the
project has a `.venv`, else `python3` — and watches it; beside it, it holds the socket that answers
the console. Run that line under whatever keeps the app's processes up:

```
agent: pinecall start --prod
```

Node on the server is that verb's price; (a) is the way without it.

**A deploy never cuts a call.** On SIGTERM the serve entry drains: the gateway hands its live
calls to another process holding the agent, or keeps them for the next one, and the tools running
are let finish, up to 30 seconds; one line on stderr says where the calls went. Give the process
45 seconds between the signal and the kill — systemd's `TimeoutStopSec=45`, pm2's
`--kill-timeout 45000`. A second signal leaves at once. The end of its stdin — the CLI that started
it is gone — drains the same way a signal does, and after a signal it is not a second one.

A refusal at start — the file cannot be served, the class is refused, the gateway will not take
the slug or the key — is one sentence on stderr and exit status 2, so a supervisor that restarts
on failure does not loop on it silently. `PINECALL_LOG=debug` writes the package's own log to
stderr, each line timed: when a call opened, and every entry read with how late it arrived.

What the agent searches is pushed before the deploy, not with it: `pinecall docs push --prod`.

## (c) Pinecall runs it

`pinecall deploy`, from the project's root, uploads it as a release and Pinecall runs (b) for you:
it installs the project with uv on CPython 3.13 — `uv sync --frozen --no-dev` from `uv.lock`, else
`uv sync --no-dev` from `pyproject.toml`, which must list `pinecall` — and starts `pinecall start`
over it, with the org's secrets (`pinecall secrets`) and a token of the app's own in its
environment. `.venv` and `__pycache__` never travel. Packages with native code need a wheel for
linux-x64: nothing is compiled. The whole guide is [Deploy to Pinecall](https://docs.pinecall.io/guides/deploy/).
