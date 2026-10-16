# Production

How a Ruby agent runs where its callers reach it. There are two ways, and neither is the box's
yet.

## The server's token

A server runs on a **server's token**, minted for production in the console (Settings ▸ Keys) or
with the Node CLI's `pinecall keys`. It was made for one world and opens that one alone: put it in
the server's secrets as `PINECALL_KEY`, never in the repository. A person's key works too while
their production switch is on, but a server should not run on a person.

## (a) Inside your own Ruby app

When the app is already a Ruby process that stays up — a Rails app's worker, a Sinatra service —
the agent can live in it. `Pinecall.serve` mounts the class on a client of its own, connects, and
hands back what it holds; `stop` drains the calls to the next holder and closes:

```ruby
require "pinecall"
require_relative "agents/clinica_norte/agent"

held = Pinecall.serve(ClinicaNorte, url: "https://cloud.pinecall.io", api_key: ENV.fetch("PINECALL_KEY"),
                                    slug: "clinica-norte")
at_exit { held.stop }
```

`Pinecall::Client.new` reads nothing from the environment: the app hands it the gateway and the
key it keeps. A person's key would need `env: "production"`; a server's token needs nothing.

## (b) `pinecall start --prod`, from the one CLI

The `pinecall` command is the Node CLI (`npm i -g pinecall`), for every language. In the project's
folder it finds `agents/<name>/agent.rb`, and `pinecall start --prod` starts this gem's serve
entry — `bundle exec ruby -r pinecall -e 'exit Pinecall::Serve.main(ARGV)' -- start …`, through
bundler when the project has a `Gemfile` — and watches it; beside it, it holds the socket that
answers the console. Run that line under whatever keeps the app's processes up:

```
agent: pinecall start --prod
```

Node on the server is that verb's price; (a) is the way without it.

**A deploy never cuts a call.** On SIGTERM the serve entry drains: the gateway hands its live
calls to another process holding the agent, or keeps them for the next one, and the tools running
are let finish, up to 30 seconds; one line on stderr says where the calls went. Give the process
45 seconds between the signal and the kill — systemd's `TimeoutStopSec=45`, pm2's
`--kill-timeout 45000`. A second signal leaves at once.

What the agent searches is pushed before the deploy, not with it: `pinecall docs push --prod`.

## Not hosted by the box yet

`pinecall deploy` runs a project on Pinecall's own servers in a Node container, and a Ruby project
is not one of those yet: Ruby in the runner's image and a Gemfile install step are a plan of their
own. Until then a Ruby agent runs on the tenant's own server, (a) or (b).
