# `pinecall-runtime`

The operator's terminal: the two processes, the database, the tenants and the fleet. One verb per
group; `pinecall-runtime --help` prints them all, `<group> --help` that group's verbs, and
`--json` before any verb answers as one JSON document, for a script. The tenant's
terminal is `pinecall`, whose page is `cli/docs/the-cli.md`, and they never overlap: nothing here
writes an agent, nothing there issues a key.

## What each group speaks to

| group | speaks to |
|---|---|
| `gateway` · `worker` · `runner` · `doctor` · `reach` · `providers` · `local` | this machine: its settings, its database, its LiveKit; `reach` asks its gateway from outside, at its name; `local` brings all three up in Docker |
| `migrate` · `sessions` · `memory` · `retention` · `traceback` · `facts` · `drift` · `usage` · `vault` · `init` · `orgs` · `keys` · `box` · `routes` · `fence` · `sip` | the services themselves, over `DATABASE_URL` (with `PINECALL_VAULT_KEY` for what is sealed, LiveKit for what a route admits, Redis to tell every gateway a key was revoked) |
| `fleet` · `orgs move` · `kill` | a running gateway, over `/v1/ops/*` with `PINECALL_OPS_KEY` ([protocol/operator-api.md](protocol/operator-api.md)): the roster, its cordons and which app holds which agent live in the gateways' memory |
| `load` | a running gateway's sandbox, over the worker's own call endpoints with the sandbox fleet's key (`PINECALL_WORKER_KEY`) |

## `gateway` · `worker start` · `worker overflow` · `callers start` · `runner start`

`gateway` serves both environments: in a pod on the address `PINECALL_GATEWAY_LISTEN` names, behind the
cluster's load balancer; elsewhere on the loopback address `PINECALL_GATEWAY_URL` names, and a URL
that is not loopback is refused in one sentence (on a Linux laptop, `setup` sets `PINECALL_GATEWAY_LISTEN` to
every interface, so the LiveKit container's webhooks reach it, and the console and API answer on port
8080 to the whole network: the machine's firewall is the fence; `setup --domain` takes it out again,
and a server's gateway stays on loopback behind Caddy). `worker start` is a worker of the fleet
`PINECALL_FLEET` names, until told to stop or cordoned; `worker overflow` the one that answers when
the fleet is full. `callers start` is the service that plays the callers of spoken simulations
(`scaling.md`, "The simulated callers are a plane of their own"): it starts
`PINECALL_CALLER_PROCESSES` processes (unset, half the cores it is given), each of which is
`callers play`, claims callers off their rows and plays three at once; one that ends on its own is
started again, and told to stop the service waits for every process to end the calls it plays,
eleven minutes at most. It reads the database, Redis, the vault and LiveKit as a gateway does and
answers nothing; the gateways beside it are told it exists with `PINECALL_CALLERS_SERVICE`, and
play no caller themselves. `runner start` keeps the hosted apps of the environment its `PINECALL_RUNNER_KEY`
opens running. On the hosting cluster it runs one gVisor pod each and is itself a pod there
(`charts/hosting`), outside the runtime's own cluster ([../infra/README.md](../../infra/README.md),
"Hosting"); with `PINECALL_RUNNER_ENGINE=containers`, on a server that runs other people's code,
each release is a container of the machine's Docker under gVisor, with no root, no capability, a
root filesystem it cannot write and a network of the apps' own, and the apps go on running while
their runner is started again; with `PINECALL_RUNNER_ENGINE=processes`, as `local up` runs it, each
release is a process of this machine under `PINECALL_RUNNER_HOME`, installed with the machine's own
npm and uv and fenced by nothing, since the code there is the machine owner's, and its apps stop
with it. Every variable they read is
[the-environment.md](the-environment.md).

## `setup`

```
pinecall-runtime setup                                   a runtime on this machine
pinecall-runtime setup --domain <name>                   a runtime on a server, with https
                       [--livekit <wss-url>|here] [--phone]   your own LiveKit, or setup's; phone calls
pinecall-runtime setup --help-all                        every flag, for a script
```

A runtime from nothing to a class that answers, in one verb; run it again any time, and every step
already done is skipped. Typed with nothing after it, it does the right thing: it loads the keys it
finds, serves the open models that fit the machine, asks who signs in to the console, and signs this
machine in. A runtime on a server is the same verb with the server's name.
On a laptop it then runs the gateway, a worker and the runner, which runs what `pinecall deploy`
sends here as processes of this machine.

**On this machine.** Postgres, Redis and LiveKit in Docker on loopback, the gateway and a sandbox
worker in the terminal you ran it in (Ctrl-C stops them; `setup` or `local up` starts them again).
No production worker runs here: a production spoken call finds nobody to take it, and a written
call runs in the gateway in either environment:

```console
$ pinecall-runtime setup

  Pinecall runtime · on this machine

  keys      anthropic · deepgram — found in ~/.zshrc, lent to your orgs
  models    gemma4:12b · whisper · kokoro — open, served here

  Who signs in to the console?
  email     ana@example.com
  password  ••••••••
  again     ••••••••

  services  Postgres · Redis · LiveKit — this machine only

  ✓ ready   http://127.0.0.1:8080/sandbox/
  ✓ this machine is signed in — no `pinecall login` needed

  Next, in another terminal:
    npm i -g pinecall
    pinecall new acme --agent front-desk && cd acme && npm install
    pinecall start       # the agent, held here: leave it running
    pinecall chat        # in a third terminal: talk to it

Running. Ctrl-C stops it; `pinecall-runtime setup` starts it again.
```

**On a server (`--domain`).** Linux with Docker, and a name whose A record points at the machine.
`setup` checks the name resolves here, puts Caddy in front on :80 and :443 with a certificate from
Let's Encrypt it renews itself, starts LiveKit facing out (its media on :7881 tcp and :7882 udp, the
machine's public address found by STUN, a key pair drawn for this machine), and runs the gateway and
a worker for each environment in Docker (two gateways, so one answers while the other is started
again), from this release of the package, so all of it comes back after a reboot. Each worker holds four calls (`PINECALL_MAX_JOBS=4`, the env file's), and each
environment has an overflow beside it: the caller no worker has a seat for hears one sentence and
is offered a call back, never silence. The night's work (`retention nightly`) runs there too.
Open :80, :443, :7881/tcp and :7882/udp to the machine. The console's admin is the
runtime's operator; a server always asks for a password (`--password-stdin` with `--yes`).

```console
$ pinecall-runtime setup --domain voice.example.com

  Pinecall runtime · voice.example.com

  name      voice.example.com → 203.0.113.7 — this machine ✓
  https     certificate from Let's Encrypt, renews itself
  keys      anthropic · cartesia · deepgram — found in the environment, lent to every org
  models    none served here — calls run on the keys above

  Who signs in to the console?
  email     ana@example.com
  password  ••••••••
  again     ••••••••

  services  Postgres · Redis · LiveKit
  phone     off — `--phone` turns it on

  ✓ ready   https://voice.example.com
  ✓ ana@example.com runs this runtime and is admin of org default

  From your laptop:
    npm i -g pinecall
    pinecall login https://voice.example.com
    pinecall new acme --agent front-desk && cd acme && npm install
    pinecall start       # the agent, held here: leave it running
    pinecall chat        # in another terminal: talk to it

  More orgs: the console → Box → Organizations · logs: pinecall-runtime local logs
```

To update the server, upgrade the package and run the verb again: `uv tool upgrade pinecall-runtime
&& pinecall-runtime setup` (the name, the LiveKit, the phone and the image are kept; the schema
migrates; the gateways and the workers start again on the new release). The name answers all
through it: a server runs two gateways behind Caddy, as a cluster does, and they are started again
one after the other, the second once the first answers (one gateway alone was away the half minute
it takes to start: 58 s measured on four busy cores). A socket held by the gateway that restarts,
a written call's or a held agent's, is dropped and opened again on the other. A worker told to stop
takes no new call and ends when the last call it holds does, ten minutes at most, so a spoken call
in flight is not cut by an update. A machine that ran `setup` alone becomes a server the first time
`--domain` is given.

**A server that carries production.** What a server is sized and built by are lines of its env file
(`<dir>/env`), which `setup` writes once and never takes a line of yours out of (a file begun by hand
before the first run is completed with what it lacks, each line of it kept); `local up` applies a
change, and starts every process that reads the file again: the gateways one after the other, each
worker once the calls it holds have ended.

| what | how |
|---|---|
| the seats of each environment | `PINECALL_SANDBOX_MAX_JOBS` and `PINECALL_PRODUCTION_MAX_JOBS`, each its worker's; `PINECALL_MAX_JOBS` is what either reads when it has no line of its own. A spoken call was measured at about a third of a core, the platform's part included |
| the simulations at once | `PINECALL_CALLER_PROCESSES`, the processes of the `callers` service, each playing three simulated callers at once (`PINECALL_CALLERS_PER_PROCESS`); unset, half the machine's cores. A spoken simulation is a seat of the sandbox's worker and a third of one of these: sixteen at once are six processes and sixteen seats and more, about 6.4 cores between them (`scaling.md`, "The simulated callers are a plane of their own") |
| the image | `--image <ref>`: every process of the runtime runs that image of a registry, the one a cluster of the same commit runs, pulled and never built here (the machine signs in to the registry itself). `setup` alone keeps it; `--image here` builds on the machine again |
| a server made ready before its name moves | `--unpointed`: the name is not checked and https is not waited for. Once the name points here, `local up` has Caddy ask for the certificate at once and waits for it: left alone, a Caddy that was refused while the name was elsewhere waits longer after each refusal, ten minutes between tries after half an hour |
| a database from another machine | `local restore <dump>`, below |
| the database's backups | `PINECALL_BACKUP_URL=s3://<bucket>/<path>` (or `gs://…`): Postgres archives every finished WAL segment there, five minutes apart at most, and a service beside it takes a base backup when the place holds none and one a night (`PINECALL_BACKUP_AT`, 03:00 UTC), keeping `PINECALL_BACKUP_DAYS` (35) of them. The tool is Barman's, the one a cluster's Postgres backs up with. The machine's own identity signs for the bucket (an instance profile, a service account); where it has none, the store's variables go in `<dir>/backups.env` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`). "A server's backups", below |
| sites of your own on :443 | a file in `<dir>/sites/`, `<name>.caddy`, as Caddy writes a site: `setup` writes the Caddyfile whole on every run and never a file of that folder |
| the apps' pages | `PINECALL_PAGES_DOMAIN=<domain>` and a wildcard record `*.<domain>` to the machine: each page's certificate is asked for at its first visit, once the gateway says the name is a page of an app that runs (`GET /v1/pages/known`). Let's Encrypt gives a registered domain 50 new certificates a week |
| the hosted apps | a runner for each environment, on a machine of their own: `pinecall-runtime runner start` with `PINECALL_GATEWAY_URL` (the server's https name), `PINECALL_RUNNER_KEY` (`keys runner <env>`), `PINECALL_RUNNER_ENGINE=containers` and `PINECALL_RUNNER_IMAGE` (the image every app runs in). Each app is a gVisor container, fenced from the machine and from the other apps; `infra/server/runners` sets the machine up (gVisor, the apps' network and its fence). Where every app is the operator's own, `PINECALL_RUNNER_ENGINE=processes` and a `PINECALL_RUNNER_HOME` for each runner run them as plain processes, fenced by nothing |

**What each process of a server holds.** Every process runs as a user of its own that is not root, as
a cluster's pod does: the runtime's as 10001, Postgres and Redis as their images' users, LiveKit and
SIP as 10001. None keeps a capability, none may gain a privilege, and none can write its root
filesystem; Caddy alone keeps one capability, to take ports 80 and 443. What they write goes to
memory (`/tmp`), a volume, and the recordings' folder; a one-shot service, `own`, run before the
others with no network and no capability but to change an owner, makes that folder and Caddy's
certificates theirs. Each is handed what it reads: the gateways the env file whole, with the
database as `pinecall_app`, a role that reads and writes every table's rows and changes none; the
simulated callers that database as the same role, Redis, the vault's key, the token key and LiveKit's
pair, and no operator's key and no fleet's; a
worker and an overflow their LiveKit and its pair, their fleet's key and where recordings go, and no
database, no Redis, no vault key, no operator's key and no signing key; the retention the database as
its owner, the vault and the recordings. `setup` draws, once, the role's password
(`PINECALL_DB_APP_URL`), Redis's (`PINECALL_REDIS_PASSWORD`; LiveKit and SIP sign in with it too)
and a password for the owner in place of the image's, and grants the role every table's rows each
run. Each worker and overflow answers its health on a port of loopback, which compose waits for: a run of `setup` or `local up` fails on one that does not start, and Docker starts one again that stops answering. LiveKit's and SIP's configs are said in the compose file from the env file's values, so the
env file (owner-only) is the one file of the machine that holds a secret. On a cloud's machine,
`infra/server/fence` (run by `make server`, as root) keeps the metadata address, and with it the
machine's identity, from the runtime's processes: it answers root, the operator and Postgres's
network, whose WAL goes to the bucket as the machine.

**Your own LiveKit (`--livekit`).** LiveKit Cloud or a LiveKit you run, instead of one `setup`
starts: its URL, then its API key and secret, asked once (`--livekit-key`, `--livekit-secret-stdin`
for a script). The pair is tried before anything is kept. LiveKit must reach the runtime with its
events, so it is a server's: on a laptop `setup` refuses it in one sentence. The last lines are the one
step left in LiveKit — its webhook, `https://<name>/v1/livekit/webhook`, signed with that key. The
browser joins your LiveKit where it is; a phone call then goes through that LiveKit's own SIP, so
`--phone` is refused beside it. `--livekit here` puts the LiveKit `setup` starts back, with a pair
drawn for the machine again.

**A server's backups.** With no `PINECALL_BACKUP_URL` a server keeps no backup at all: its database
is one Docker volume. With one, what is in the bucket restores the database to any moment of the last
35 days, on this machine or a new one. The runtime is stopped, Postgres's volume emptied and a base
backup put in it, and Postgres told to replay its WAL from the bucket up to the moment; when it has,
`up` starts the rest:

```console
$ cd ~/.pinecall-runtime/local && pinecall-runtime local down && set -a && . ./env && set +a
$ docker compose -f compose.yaml run --rm --user postgres --entrypoint bash postgres -c '
    barman-cloud-backup-list $PINECALL_BACKUP_URL pinecall'               # the backups, newest last
$ docker compose -f compose.yaml run --rm --user postgres --entrypoint bash postgres -c '
    rm -rf "$PGDATA"/* && barman-cloud-restore $PINECALL_BACKUP_URL pinecall <backup id> "$PGDATA"
    cat >> "$PGDATA/postgresql.auto.conf" <<CONF
restore_command = '"'"'barman-cloud-wal-restore $PINECALL_BACKUP_URL pinecall %f %p'"'"'
recovery_target_time = '"'"'2026-11-23 14:05:00+00'"'"'
recovery_target_action = promote
CONF
    touch "$PGDATA/recovery.signal"'
$ docker compose -f compose.yaml up -d postgres
$ until [ "$(docker compose -f compose.yaml exec -T postgres psql -U pinecall -d pinecall -Atc "select pg_is_in_recovery()")" = f ]; do sleep 2; done
$ pinecall-runtime local up
```

Without the `recovery_target_time` line Postgres replays every segment the bucket holds. A bucket of
Google's takes `--cloud-provider google-cloud-storage` after each of the three `barman-cloud-`
commands. `up` run while Postgres still replays fails on its first statement (the database is
read-only until then), which is what the wait is for. A backup is proven by restoring it: do this
once on a machine that is not the server.

**Phone calls (`--phone`).** LiveKit's SIP beside the LiveKit `setup` starts, on :5060, its audio on
:10000-10019/udp, a port a call (`PINECALL_SIP_RTP_PORTS=10000-10199` in the env file for more):
open them to your carrier alone. Carriers are told the server's own name; a `PINECALL_SIP_DOMAIN`
already in the env file is kept, for a runtime whose carriers' trunks name another. One SIP takes
both environments' calls: a second name for the sandbox's (`PINECALL_SANDBOX_SIP_DOMAIN`) points at
the same machine. What needs a SIP an environment is
a cluster's: a simulated caller that rings by phone (`simulate --via sip`) is refused on a server in
one sentence. A number is then imported or bought as on any
runtime ([telephony.md](telephony.md)).

**The keys.** For each installed vendor `setup` looks for its variable (`DEEPGRAM_API_KEY`,
`<VENDOR>_API_KEY`) in the environment, then in the shell's files (`~/.zshrc`, `~/.zprofile`,
`~/.bashrc`, `~/.bash_profile`, `~/.profile`) not loaded into this terminal; a line that expands
(`$(…)`, `$OTHER`) is not read, and no value is ever shown. A key found is the org `default`'s own
and the runtime's, which lends it to every org made later until that org brings its own
([limits.md](limits.md)). A default's key found nowhere is asked for once, without echo. With
`--models none` no key is loaded and no providers row is written: both are the operator's.

**The models.** It reads the machine — its NVIDIA cards and their memory, Apple silicon, the RAM,
whether an Ollama already answers — and serves the best measured model that fits beside the ears
(Whisper), the voice (Kokoro) and the embedder (bge-m3), through the runtime's `openai` plugin with a
`base_url` per stage; on a card Docker can reach, all of it runs on the GPU. A machine with no GPU
serves none, and its defaults are deepgram, anthropic and cartesia. Where an Ollama already answers
(a Mac's, on Metal), it is the one that thinks: a model it holds is used as it is, one it lacks is
pulled by it, and an Ollama too old for that model refuses in its own words — update it and run
`setup` again. These are the runtime's
defaults, what an agent naming no stage runs on; an agent names its own (`pinecall agent set
--llm groq`).

**The prices.** The first time it writes the providers row, `setup` gives it the list prices the
package ships (`cli/local/prices.csv`, vendor by vendor, with the notice of the rows it took from
voice-prices), so every call on a vendor's key is priced from the first; the open models cost
nothing. After that the row is the console's: a run of `setup` never overwrites a rate, and
`providers prices <file> --apply` changes them.

**How each vendor is built.** The runtime names no vendor in code, so what a vendor's models need is the
row's to say, and `setup` writes that with the row too (`cli/setup/shipped/tuning.json`): the plugin's class
a family of models runs on where it is not its `STT` or `TTS` (Deepgram's Flux on `STTv2`, Gemini's voice
and ears on `beta.GeminiTTS` and `beta.GeminiSTT`), the ears that end the turn themselves or commit when
told, and what a model is asked beside the conversation. It is the same word Pinecall's own runtime keeps,
by `stage/vendor/model`, so a model the picker offers runs here as it runs there; only the vendors this
install carries are written. A vendor named bare keeps its plugin's own class and model, as before.

**This machine, signed in.** On this machine, the console admin's own key is written into the CLI's
`~/.pinecall/session.json` (`PINECALL_HOME` moves it) as `pinecall login` writes one: the `pinecall`
CLI here needs no login, and a project `pinecall new` makes runs on this runtime, in `default`. A
server signs nobody in: each person runs `pinecall login https://<name>` on their own machine.

**For a script** (`--help-all` lists them): `--email`, `--person`, `--password-stdin`, `--yes`
(ask nothing: a key missing refuses, and a laptop's admin gets no password until `orgs password`
sets one); `--livekit-key`, `--livekit-secret-stdin`; `--from <wheel>` (a server's processes
installed from that wheel rather than PyPI); `--models local|keys|none`, `--stt`, `--turn`, `--llm`,
`--tts`, `--judge`, `--caller` (the defaults, a stage at a time: `local`, `local/<model>`, or a
vendor); `--chat-only` (no LiveKit and no worker: written calls alone; the ears and the voice are
set to `local`, so Ollama, Whisper and Kokoro still start); 
`--services-only`; `--recommend` (the machine's reading and the stack that fits, as JSON, nothing set
up); `--dir` (`~/.pinecall-runtime/local` unless named).

## `local`

```
pinecall-runtime local [--dir <path>] up [--services-only]
pinecall-runtime local [--dir <path>] down [--volumes]
pinecall-runtime local [--dir <path>] restore <dump>
pinecall-runtime local [--dir <path>] logs [<service>]
pinecall-runtime local [--dir <path>] init --email <address> --person "<name>" [--org <slug>] [--name "…"]
pinecall-runtime local [--dir <path>] env
```

The runtime whole on one machine, for developing an agent against it: no cloud account, no key
from anywhere. `up` writes the Docker Compose files the package ships into `--dir`
(`~/.pinecall-runtime/local` unless named), brings up Postgres (17, with pgvector and
pg_textsearch, built once), Redis and LiveKit on loopback ports of their own, migrates the schema,
draws the machine's secrets once into `<dir>/env` (0600: the vault key, the ops key, the token
key, the sandbox fleet's and the sandbox runner's keys), then runs the gateway on
`http://127.0.0.1:8080` — the console included, the sandbox at `/sandbox/` — a worker of the
sandbox fleet, and the sandbox's runner, which runs what `pinecall deploy` sends here as processes
of this machine (`runner start` above); their lines are prefixed `gateway |`, `worker  |` and
`runner  |`. Ctrl-C stops the three, and the deployed apps with them; the services stay.
`--services-only` stops after the schema, for a checkout that runs the processes from its sources
(`make local-gateway`, `make local-worker`). Run `up` again any time: it keeps the secrets and the
database. On a server (`setup --domain` made it one) `up` brings every service back in Docker, waits
for the name to answer over https, and returns: nothing runs in the terminal.

`down` stops the services, a server's included, and keeps the database; `--volumes` deletes it, and
the next `up` draws the box's keys again, since the database that knew them is gone.
`restore <dump>` replaces this machine's database with a dump of another runtime's (`pg_dump -Fc`),
which is how a runtime moves between machines, or between a cluster and a server: every service that
writes is stopped, the schema emptied, the dump restored, and the runtime left stopped for `up` to
bring the schema to this release and start it. What the dump holds is sealed under the other
runtime's `PINECALL_VAULT_KEY` and signed with its `PINECALL_TOKEN_KEY`: both go into `<dir>/env`
first (and each environment's fleet key, for workers that knock with them), or nothing sealed there
opens here.
`logs` follows a server's: every service's, or one's (`gateway`, `worker-sandbox`,
`worker-production`, `livekit-server`, `caddy`); a laptop's are in the terminal `setup` runs in. `init` is `init` below,
run on the local settings, so the first org and person need no shell line. `env` prints that
line, `set -a; . <dir>/env; set +a`, for any other verb against the local runtime. It needs Docker
with the compose plugin: Docker Desktop on macOS and Windows, Docker Engine on Linux; without it
`up` says so in one sentence. A phone call needs the SIP bridge on the host's network, which Docker
on macOS does not have: `docker compose -f <dir>/compose.yaml --profile phone up -d sip`, on Linux.

## `init`

```
pinecall-runtime init [--org <slug>] --email <address> --person "<name>" [--name "…"] [--role admin]
```

The first org and the first person on a runtime nobody has used yet: the org made (or found, run
twice), its first admin invited, that person made an operator of this deployment, and the invitation link
printed once with the two lines to type next.

## `kill`

```
pinecall-runtime kill <agent> [--org <slug>]
```

The agent let go by every app of the org that holds it, in either env, wherever they are connected:
each app is told the agent was killed, keeps its other agents, and declares this one no more when it
reconnects; the agent's calls move as on a drain. Nothing is erased: its settings, calls and logs
stay, and an app that declares it again holds it again. `--org` is `default` unless named. It asks a
gateway (`POST /v1/ops/orgs/{org}/agents/{agent}/kill`), because which app holds which agent lives
in the gateways' memory; a tenant's admin does the same in one env with `pinecall kill`.

## `orgs`

```
orgs list · orgs add <slug> [--name] · orgs rm <org>
orgs invite <org> <email> --name "…" [--role] · orgs operator <org> <email> [--revoke] · orgs remove-member <org> <email>
orgs password <org> <email>                          # asked twice at a terminal, else read from stdin
orgs move <agent> <org>
orgs quota <org> --env production|sandbox [--minutes n] [--messages n] [--agents n] [--concurrent-calls n]
           [--memory-facts n] [--knowledge-chunks n] [--numbers n] [--seats n] [--llm-tokens n]
           [--hosted-apps n] [--evals n] [--simulations n] [--budget-usd n]
orgs lends <org> --env production|sandbox <vendor[/model],…|all|none>
orgs simulating <org> --env production|sandbox [--at-once n] [--comparison-calls n]   # one left out is the platform's own
orgs dialling <org> [--dial-anywhere | --no-dial-anywhere] [--per-minute n] [--per-day n] [--max-duration-s n]
orgs sso <org> [--off]
orgs provider-key set|rm|list <org> <vendor>        # set reads the key from stdin
```

`<org>` is an id or a slug. `quota` replaces the whole set of limits **for one environment** and keeps
what the runtime lends the org there; `lends` is that alone — `all` every key the runtime holds, `none` none,
or the vendors and `vendor/model` entries named — and keeps the limits. A call runs on the org's own
key for a vendor, else on the runtime's where it is lent, else it is refused ([limits.md](limits.md)); `dialling` the whole
set of guards; `sso --off` is the break-glass; `provider-key set` reads from stdin because argv is
what `ps` shows. `password` sets a person's password the same way, with no link: an invited person
becomes active by it, a disabled one is refused until enabled.

## `box`

```
box keys list · box keys set <vendor> · box keys rm <vendor>      # set reads the key from stdin
box numbers-account show · box numbers-account set --account-sid <AC…> [--user <SK…>] [--label "…"] · box numbers-account rm
box admission show
box admission set --env production|sandbox [--later] [--minutes n] [--messages n] [--evals n] [--simulations n] …
                  [--budget-usd n] [--lends <vendor[/model],…|all|none>]
box alerts list [--org <id>] [--limit n] · box alerts show · box alerts set <url> [--secret] · box alerts rm
box test-line show · box test-line set <+E.164> · box test-line rm
```

What the box itself holds. `keys` are its own vendor keys, the ones an org without its own runs on
where `orgs lends` lets it: `set` reads the key from stdin and nothing reads it back. An org whose own
key for the vendor is the same key (`setup` gives `default` each key it finds) holds a copy: `set`
replaces the copy with the new key and `rm` forgets it, so rotating a key is one `set`; a key an org
brought that is a different one is never touched. `numbers-account`
is the Twilio account the box buys numbers on for its orgs (`POST /v1/numbers/buy`, the console's *Buy a
number here*): `set` reads the secret from stdin and tries the pair with Twilio before keeping it;
without one the box sells no numbers. `admission` is what a newborn org is given — `set` writes one
environment's limits and lends for a person's first org (`--later`: any later one), the rest of the row
as it stands; `--lends` left out lends every key. `alerts` is where the operator hears every org's
alerts: each one — a monitor fired, unusual spend, a quota run out, a hosted app that went down — is
kept 90 days (`list`, every org's newest first, or one's with `--org`), mailed to the org's admins and
the box's operators (once an hour per monitor, app or quota; the newborn orgs an hourly sweep finds quiet, as one mail), and posted to the URL `set` names as
well as to the org's own, the same JSON body (`org` and `env` name whose it is, `x-pinecall-event`
the kind, signed with the secret when one is given; `--secret` reads it from stdin). A webhook is
never needed: an org that named no URL of its own is still kept, mailed and seen by the operator. `test-line` is
the one sandbox number of the box's own that a person calls, from the phone they said was theirs, to reach their
own sandbox agent ([telephony.md](telephony.md), "The box's test line"): `set` wants a number the box routes in the
sandbox, and `rm` leaves the number ringing its own agent. The doors are [protocol/operator-api.md](protocol/operator-api.md).

```
$ printf '%s\n' "$CARTESIA_API_KEY" | pinecall-runtime box keys set cartesia
$ pinecall-runtime box admission set --env sandbox --minutes 30 --evals 100 --simulations 10 --lends google,cartesia,deepgram
$ pinecall-runtime box admission set --env production --minutes 0 --lends none
$ printf '%s\n' "$TWILIO_SECRET" | pinecall-runtime box numbers-account set --account-sid AC… --user SK… --label Pinecall
$ printf '%s\n' "$ALERTS_SECRET" | pinecall-runtime box alerts set https://hooks.example.com/pinecall-ops --secret
$ pinecall-runtime box test-line set +13617334133
```

## `keys`

```
keys issue [--org <org>] --env production|sandbox [--label "…"] [--scope <scope>]… [--subject <member>] [--name "…"]
keys list [--org <org>] · keys revoke <fingerprint>
keys runner production|sandbox
```

`issue` prints the key once; the table keeps the fingerprint. A fleet's key is no row of the database:
it is a setting of the gateway (`PINECALL_PRODUCTION_FLEET_KEY`, `PINECALL_SANDBOX_FLEET_KEY`,
[the-environment.md](the-environment.md)), drawn by Terraform in a cluster and by `setup` on a machine.
`runner` mints the key of the environment's runner on the database and prints it once, put once
in Secret Manager for the hosting cluster ([protocol/hosting.md](protocol/hosting.md),
[../infra/README.md](../../infra/README.md), "Hosting").

## `routes`

```
routes list [--org] [--env] · routes add <number> <agent> [--channel phone|whatsapp] [--org] [--env]
routes rm <number> [--org] · routes seed <file>
```

`seed` reads a JSON list of routes, each the body `routes add` sends (`number`, `agent`,
`channel`, `org`, `env`), and adds them one by one: how a box comes up from a checkout. The file
is yours; the repository ships none.

## `fence`

```
fence export
```

The networks 5060 opens to, Twilio's first, then the carriers the operator admits and the
addresses he approved ([telephony.md](telephony.md), "The fence, twice"), as Terraform reads them:
`{"sip_sources": [...]}`. `make tf-fence CLUSTER=<cluster>` runs it on the gateway and writes
`terraform/<cluster>.fence.tfvars.json` in the operator's own directory (the orgs' addresses: versioned
there, never in this repository); `make tf-plan` reads that file and refuses to plan without it,
and `make tf-apply` brings the cloud's firewall level with the platform.

## `sip`

```
sip repoint [--from <world>=<name>]…
```

Every trunk of the platform's Twilio account and of each org's that still sends an environment's calls to the
platform's name, or to a name `--from` says the environment was reached at before
(`--from production=sip.old.example.com`), sent on to its SIP name (`PINECALL_SIP_DOMAIN`,
[the-environment.md](the-environment.md)), a line each: the account, the trunk, the environment, where it
pointed and where it points now. Once, when the platform's SIP moves off its names or a name is retired;
run again, it sends nothing on.

## `fleet`

```
fleet list [--fleet <name>] · fleet cordon <worker> · fleet uncordon <worker>
```

`list` is the roster the gateway hears: each worker, what it holds, its seats, load, standing
(`accepting`, `failing`, `full`, `draining`, `cordoned`, `gone`) and when it was heard, then each
fleet summed, with its rooms waiting for a worker when there are any (a call LiveKit or a worker
dropped, offered again by the gateway: [scaling.md](scaling.md), "Who takes a call"). `cordon`
tells a worker, on its next heartbeat, to take no new call, finish what it holds and leave;
`uncordon` takes that back while it has not left. How many workers a fleet runs is the cluster's:
[scaling.md](scaling.md), "The burst"

## `load`

```
pinecall-runtime load --org <id> --agent <slug> --script <call-log.json> --calls <n> --ramp <seconds> --minutes <m>
```

Synthetic calls held against the gateway at `PINECALL_GATEWAY_URL` exactly as workers hold them,
so the control plane is measured without LiveKit, audio or a vendor. Each call knocks the endpoints a
worker knocks, through the worker's own client: it opens a call in the **sandbox** environment (there is
no other), queues the script's entries a worker writes at the script's own gaps on the worker's
own writer, which sends what is queued as one batch while the last is out, then its `call.ended`,
and seals it once all were answered; the entries the gateway writes itself
(`call.ringing`, `call.attached`, `tool.call`, `tool.result`, `call.summary`, `call.score`, memory
and sources) are left out, and so are tool round-trips, which need an app socket. A call that
ends before the run does is followed by a fresh one, so the number held stays at the top; a
refusal ends that call only, and its slot opens another a second later. `--script` is a call's
log as JSON, the shape of `tests/wire/golden/call-log.json` (125 entries over 53.5 s); `--calls`
is how many at once at the top, reached linearly over `--ramp` seconds and held `--minutes`.

```
PINECALL_GATEWAY_URL=https://<staging's sandbox name> PINECALL_WORKER_KEY=<its sandbox fleet key> \
  pinecall-runtime load --org org_load --agent load --script tests/wire/golden/call-log.json \
  --calls 500 --ramp 60 --minutes 5
```

It runs against **a cluster made for it** (staging, `make deploy CLUSTER=staging`), never
production's: the calls are real calls of the org, logged, counted against its quotas and
sealed. The org is one made for the run, with its sandbox quotas (`orgs quota --env sandbox`)
above the run and its hang-up judging off (`PUT /v1/org/judging`), or every seal asks the platform's
judge model. Each call at once has a client and a connection of its own, as a worker's job has, so
`ulimit -n` must be above `--calls`. At the end it prints, a line each:

| line | what it is |
|---|---|
| `calls opened` · `calls sealed` | calls the gateway opened, and those sealed after their `call.ended` |
| `calls open at the end` | calls still writing past the run's end and a grace of 60 s, cut |
| `most held at once` | the most calls open together |
| `entries sent` | appends the gateway answered, and how many of them it keeps (durable) |
| `entries a second at the top` | appends answered between the end of the ramp and the end of the run, per second |
| `append ms` · `seal ms` | from an entry queued to the log holding it, what the call waits, p50/p95/p99; and the time one seal took, p50/p99 |
| `entries per batch` | how many entries each batch carried, p50/p99: 1 while calls are idle, more as the gateway slows |
| `refusals` | the calls a refusal ended, by the status the gateway answered (`unreachable` for none) |
| `logs verified` · `logs found wrong` · `logs unread` | each sealed call's log read back: every durable entry sent, once each, in order, and seqs that rose; `unread` counts the reads refused, by status |
| `loop lag ms` | the p99 lag of the generator's own event loop; over 50 ms a `warning:` line follows, since a saturated generator measures itself |

## `sessions` · `memory` · `retention` · `traceback` · `facts` · `usage` · `drift` · `migrate` · `providers` · `doctor` · `reach`

`sessions list [--agent] [--limit]`, `sessions show <call> [--folded]`, `sessions tail [<call>]`,
`sessions recording <call>`: the log read back off Postgres, every tenant's; each read of a call is a row of its org's access log (`reader: operator`), and so is each org a `traceback` showed. `memory reembed`
embeds every fact another model wrote under the platform's embedder. `retention due` lists the sealed
calls past their org's `retention_days` (`PUT /v1/org/policy`), oldest first; `retention run`
erases them, each through the erasure path with `retention` as who asked, 5 000 a run at most,
then forgets the detail records of erased phone calls, and the dials, older than 24 months, and
the WhatsApp message ids claimed more than 7 days ago ([whatsapp.md](protocol/whatsapp.md)) and the alerts
raised more than 90 days ago;
then makes the log's days a week ahead (`call_log` is partitioned by UTC day; a row no day holds lands in `call_log_default`, and a day the default already holds rows of is named and not made) and drops each past day nothing is left in; the CronJob `pinecall-retention` runs it at 04:00 UTC every night, and on a server `retention nightly [--at HH:MM]` does, a service that waits for that hour of UTC and runs the same night, day after day. `doctor`'s `days` line names rows in the default and fewer than two days made ahead. `traceback <number> [--since
YYYY-MM-DD]` answers a carrier's traceback: every phone call with the number, still kept or erased
with its record, and every dial to it placed or refused, with the org, the environment, the number shown
and who asked — 24 months back unless `--since` says a day. `migrate up` applies what the
database lacks, `migrate status` says what it lacks (exit 1 while behind), `migrate plan` names
every migration on the disk. `providers list [--does llm|stt|tts]` lists every vendor this build
(`providers installed` the same with no database, and whether each vendor's ears end the turn)
runs and whether the platform holds its key; `providers seed <file>` writes the providers row a deployment
starts from, once: after it, the console edits it at `/v1/ops/providers`. `providers prices
<file.csv> [--apply]` says what a prices file changes in the row's rates (new, changed, the same,
and the models only the platform holds, which it keeps) and writes nothing until `--apply`; the
package ships `cli/local/prices.csv`. `providers models <file.csv> [--apply]` the same for what a
picker offers of each vendor by stage (`vendor,stage,model,name,as_of,source`, written by `voicedex
models`, and a `recommended` column after them or not, `yes` on the models a picker leads with); the
package ships `cli/local/models.csv`, which `setup` writes into the row. `facts rebuild [--call <call>] [--org <org id>] [--since
YYYY-MM-DD]` folds each call's facts row (what the lists, the inbox and the insights read) again
from its log — for a sealed call, the line a list shows of it too, which the seal writes and a list
reads instead of folding the log — every call's when no flag is given, and writes the row where it
differs: one call at
a time, each in a transaction of its own under the lock its appends take, so a live call waits
milliseconds and nothing holds a long transaction; it prints how many calls it read, how many
rows it rewrote, and how many it left as they were: a log holding an entry this release's wire
refuses is never refolded, because the fold would pass the entry by and lose what the release that
wrote it folded from it (doctor's sample passes those by too). `usage rebuild` folds every org's
usage totals (what admission counts, a row per org, environment and month) again from the summaries in
the log, as the usage feed folds each one, and rewrites the table in one transaction that holds
it: a summary written meanwhile waits and is counted after; it prints how many summaries and rows.
`doctor` asks each thing the platform needs one question, a line each, and exits 1
when one is missing. Its `facts` line examines the 20 newest
calls and 20 heads from a random point of the call ids (never every head: on a deployment that is a probe
per call), names each whose head gave out fewer seqs than its rows hold and how many it examined,
and refolds 20 sealed calls from a random point of the call ids, naming each whose stored facts
differ and the columns that do: `facts rebuild
--call` mends one. Its `offers` line names the rooms a caller joined over a minute ago that are
still kept: three offers 12 s apart let every room go before then, so one still kept is a room no
gateway is sweeping. `reach [<url>]` is what `doctor` cannot see from inside: it asks a gateway
at its address (the box's own name, unset) what a browser and a server ask it first, a line each,
`ok` or `NO` and why, and exits 1 when one is wrong: the console's page at any path and that it
is served `no-store`, the widget with `access-control-allow-origin: *`, `401` and the `Bearer`
challenge with no key, `401` for a key nobody issued, the API's own JSON `404` under `/v1`, and
the OpenAPI document naming the calls' endpoints. It opens no database and reads no key, and
`make deploy` ends in it, run in the new release's pod. `drift rebuild [--org <org id>] [--since YYYY-MM-DD]` forgets the drift of
the days the flags name (every org's and every day's when none), each stage's histogram, each
judge's count, each tool's day and each call's slowest turns that `/v1/insights`, `/v1/insights/drift`,
`/v1/insights/tools` and `/v1/insights/slow` read, and counts every sealed call of
them again from its log, each in a transaction of its own; it prints how many sealed calls it read
and how many it counted. A seal whose count broke says so in the gateway's journal, and this is what
mends it.

## `vault rotate`

Every secret the platform keeps is sealed under the first key of `PINECALL_VAULT_KEY`, and any key the
list holds opens it. To turn the vault: put a new key in front of the list (in a cluster, a new
version of the secret `pinecall-<world>-vault-key` in Secret Manager holding `<new>,<old>`, which
External Secrets brings to the pods within the hour) and restart the gateways, so
every secret written from then on is sealed under the new one; then `vault rotate` re-seals every
sealed value of the schema under the first key, one line per column:

```
box_settings.ciphertext: 3 re-sealed, 0 under the first key already, 0 opened by no key listed
```

The columns are the vendors' keys (the org's and the platform's), the carriers, the mailboxes, the
identity providers, the hosted apps' tokens, the org's secrets, the private values of calls' logs,
the recordings' keys and the one-use words of sign-in (a terminal's key while it waits). Each row is its own write,
guarded by the value it still holds, so a secret the gateway rewrites meanwhile is left to it; a
run cut short is run again, and finds what it did under the first key. It exits 1 while a value
opens under no key listed: that value was sealed under a key the list no longer holds, and the
old key comes out of the list only once every line says 0 there.
