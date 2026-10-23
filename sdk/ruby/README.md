# pinecall

Build voice agents as Ruby classes. Declared fields are the agent's state, `tool` methods are
what the model can call, the comment above each tool is its description, and an ERB view renders
the part of the prompt that changes during the call.

```ruby
require "pinecall"

# You are the front desk of Clínica Norte. Formal, short sentences.
class ClinicaNorte < Pinecall::Agent
  stage :identify, :book
  state :patient, visibility: :pii
  state :slots, []

  # Finds the patient by name and phone. Ask for both before calling it.
  tool stage: :identify, pii: %i[name phone]
  def find_patient(name:, phone:)
    self.patient = Agenda.find(name, phone)
    self.stage = :book if patient
    patient
  end

  # Free slots on one day.
  tool stage: :book, preview: 2
  def free_slots(day:)
    self.slots = Agenda.free(day)
  end
end
```

`views/clinica-norte.erb` renders the prompt from that state:

```erb
<% if stage == :identify -%>
Greet the caller and ask for their name and phone. Nothing else until the patient is identified.
<% end -%>

<% if remembers?("usual doctor") -%>
Offer their usual doctor's slots first.
<% end -%>

<% if slots.any? -%>
## Free slots, in order

<% slots.each do |slot| -%>
<%= slot.when %> with <%= slot.doctor %>
<% end -%>
<% end -%>
```

The prompt has four named blocks: `identity`, `knowledge` and `tools` are static and cached
before the history; `view` comes after it and is replaced every turn. A block is re-sent only when
its text changes.

Memory and knowledge-base results never enter the prompt. The platform runs `recall` and `search`
and returns their results to the model as tool results, so retrieved text is treated as data, not
instructions. A view can ask `remembers?("usual doctor")` and write its own sentence about the
answer.

## Five minutes

This gem is a library: the verbs are the one `pinecall` CLI's, the same for every language. In a
project laid out as `agents/<name>/agent.rb`, with this gem in its `Gemfile`:

```bash
bundle add pinecall
npm i -g pinecall                     # the CLI: Node, whatever the agent is written in
pinecall login                        # this machine signed in, once; pinecall.json names the org
pinecall prompt --state agents/<name>/test/goldens/a.json   # the exact prompt a state produces. No gateway.
pinecall start                        # registered and answering: the process you deploy; leave it running
pinecall chat                         # in another terminal: a caller against the agent start holds
pinecall test                         # ring 1: the goldens, played on the agent start holds, scored by the gateway
```

The CLI never loads your class: for `prompt` and `start` it runs this gem's serve entry,
`bundle exec ruby -r pinecall -e 'exit Pinecall::Serve.main(ARGV)'`, and talks to it through the
gateway. `start` is the one verb that runs the agent; `chat`, `test` and `simulate` start nothing,
and reach whoever holds it. The console, the knowledge bases, memory and every other verb are the
CLI's.
How a server runs the agent, with the CLI or inside your own Ruby process, is
[docs/production.md](docs/production.md).

## Architecture

This gem is the application side. It never talks to a model vendor or handles audio: it sends
commands and reads log entries over one WebSocket, in the runtime's own wire (`lib/pinecall/wire/`),
held to the runtime's golden call log. Tools are the only code that may change state.

| you want | you use |
|---|---|
| the class and the view | `Pinecall::Agent`, `Pinecall.mount` |
| the agent held inside your own process | `Pinecall.serve` |
| the socket alone, your own way of deciding what to answer | `Pinecall::Client` |
| a suite with no network, no key and no model | `pinecall/testing` |

```ruby
pc = Pinecall::Client.new(url: "https://cloud.pinecall.io", api_key: ENV.fetch("PINECALL_KEY"))
agent = pc.agent("clinica-norte", tools: [])
agent.on("turn.user") { |data, call| call.say("I heard: #{data[:text]}") }
pc.connect
```

`PINECALL_KEY` here is a server's token, made in the console's API keys screen for the org and the
environment the process runs in — not your own sign-in, which stays on your machine. On a runtime
of your own the URL is its gateway's (`http://127.0.0.1:8080` on your machine).

## Testing it

Agent tests run with no network, key, model or gateway:

```ruby
require "pinecall/testing"

gateway = Pinecall::Testing::Gateway.new
Pinecall.mount(ClinicaNorte, client: gateway)

call = gateway.call_started(from: "+34600123456")
call.tool("find_patient", name: "Marta Ruiz", phone: "600123456")

refute_includes call.prompt, "ask for their name"
assert_equal %w[free_slots], call.tools
```

## Where the rest is

| what | where |
|---|---|
| tutorial: an agent with knowledge and memory, from an empty directory | [docs/tutorial.md](docs/tutorial.md) |
| every file, entity and rule | [ARCHITECTURE.md](ARCHITECTURE.md) |
| how to write an agent, step by step | [docs/writing-an-agent.md](docs/writing-an-agent.md) |
| the view, and the blocks of a prompt | [docs/the-view.md](docs/the-view.md) |
| how to test one | [docs/testing-an-agent.md](docs/testing-an-agent.md) |
| running it in production | [docs/production.md](docs/production.md) |
| the CLI, verb by verb | the one CLI's reference, at docs.pinecall.io |
| a complete example agent | [examples/ruby/clinica_norte](../../examples/ruby/clinica_norte) |
| the wire itself | `lib/pinecall/wire/`, the runtime's shapes this gem speaks |

## Requirements

Ruby 3.2+. The only runtime dependency is `websocket-driver` (the driver ActionCable uses). The
`pinecall` CLI is a Node program (Node 24+): the verbs need it, the library does not.

## License

[Apache-2.0](LICENSE), including its patent grant. No CLA.
