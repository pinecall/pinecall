# The voice app, tasks and the caller's screen

What a project adds around its agents: the numbers it answers and who answers each (the voice app),
what a tool asks the caller for in the middle of it (tasks), and what the caller sees on a page of
yours (the screen). Each is optional. The TypeScript and Python packages have the same three.

## A tool that asks: tasks

```ruby
class FrontDesk < Pinecall::Agent
  tasks Pinecall::GetEmail

  # Book a time, once the caller said yes to it.
  tool
  def book(slot:)
    email = ask(Pinecall::GetEmail)
    Clinic.book(slot, email)
  end
end
```

A task is one thing a tool needs from the caller before it can finish. `ask(Pinecall::GetEmail)`
stops the tool there, on its own thread: the model is told what is missing and how to ask, asks the
caller, and gives the answer with a tool of the task's own (`give_email`), the only tool open
meanwhile. The task checks what it was given, and one that does not pass is asked for again. Then
`ask` returns the value, and what the tool returns is what the model reads, as
`{ finished: "book", result: … }`. One question at a time.

Three come with the gem: `Pinecall::GetEmail`, `Pinecall::GetPhone` and `Pinecall::GetName`. One of
your own:

```ruby
GetPlate = Pinecall.task("plate", asks: "the plate of the car", how: "Read it back letter by letter.",
                                  fields: { plate: "The plate, letters and digits, no spaces." }) do |given|
  plate = given["plate"]
  raise ArgumentError, "\"#{plate}\" is not a plate. Ask for it again." unless plate.match?(/\A[A-Z0-9]{5,8}\z/i)

  plate.upcase
end
```

`fields` is what the model gives, each a string with what it is; the block returns what your tool
is handed, and what it raises is told to the model. A class names the tasks its tools ask for with
`tasks`; a call that ends with a question open makes `ask` raise, so the tool does not go on.

## The voice app: the project's lines

```ruby
# app.rb
APP = Pinecall.voice_app("brightside", timezone: "America/Los_Angeles")
APP.line("+1 415 555 0134", FrontDesk, greeting: "Brightside Dental. How can I help?")
APP.silence(after: "8s", say: "Are you still there?", times: 2)
```

A project may have an `app.rb` beside `agents/`. `pinecall start` loads the agents first and then
the app, so it names their classes as they are; the file makes one `Pinecall.voice_app(…)`. The
greeting is that agent's `greeting`, declared by the app, and `silence` is its `idle`; a class that
declares either itself and gets one from the app too is refused when the app loads. `timezone` is the
zone every agent of the app reads its day and clock in, the same setting as a class's `timezone`.

`APP.page("ui/dist")` gives the app a page, sent with `pinecall deploy` and served at
`https://<app>--<org>.app.pinecall.io`; `pinecall start` serves the same folder on
`http://localhost:4747` (`PINECALL_PAGE_PORT` names another port) with your key and no captcha, its
ticket, its code and its dictation asked at `/pinecall/token`, `/pinecall/code` and `/pinecall/dictation`.

### What the app hears

```ruby
APP.on("visit.booked") { |call, visit| Reminders.schedule(visit) }
APP.on("call.ended") { |call, ended| DB.calls.insert(call: call.id, reason: ended[:reason]) }
```

The name is an entry of the call's log by its type (`call.ended`, `call.score`, `handoff`, `routed`),
or a line an agent logs by its own name (`log("visit.booked", visit)`). A block that raises is said in
the terminal, and the others run.

### A flow: what outlives a call

```ruby
RemindVisit = Pinecall.flow("remind-visit") do |visit, step|
  step.sleep_until(visit[:at], before: "24h")
  called = step.call(visit[:phone], Reminder, instruction: "Remind #{visit[:patient]} of the visit.")
  step.run { DB.visits.update(visit[:id], reminded: called.answered) }
end
RemindVisit.cancel_on("visit.cancelled") { |gone, visit| gone[:id] == visit[:id] }
APP.on("visit.booked", RemindVisit)
```

A flow is a name and a block of what started it and its steps. The gateway keeps each run's journal,
so a run outlives a deploy; each time it is woken the block runs again from the top and every step
already in the journal answers what it came to. What must happen once goes inside `step.run`.

| step | what it does |
|---|---|
| `step.sleep("2h")` | the run sleeps: a number and `s`, `m`, `h` or `d` |
| `step.sleep_until(at, before: "24h")` | until a `Time` or an ISO string, or that long before it |
| `step.call(to, Agent, state:, metadata:, greeting:, instruction:, from:)` | the agent calls the number; a `Flow::Called` says how it ended, or why nothing rang |
| `step.wait_for(event, match:, within:)` | an event sent to the app whose data has what `match` names; nil once `within` passed |
| `step.run { … }` | your own code, once; what it returned is kept |
| `step.emit(name, data)` | sends an event to the app |

### Rules, a team, and a line that chooses

```ruby
APP.rule("Never quote a price that is not in the price list.")

class Billing < Pinecall::Agent
  takes "a question about a charge, an invoice or a refund"
end

APP.line("+1 415 555 0135", ->(call) { Clinic.closed?(call.today) ? AfterHours : nil },
         fallback: FrontDesk, team: [AfterHours, Billing])
```

A rule is read into every agent's prompt and judged (`app-rule-1`, …). A teammate that `takes`
something is offered as a tool named by its class (`transfer_to_billing`); a tool can pass the call
itself with `call.handoff(Billing, invoice:)`, and the teammate reads `call.handed`; `call.shared` is
what the agents of one call share. A line's lambda chooses who answers; the `fallback` answers when it
returns nil, raises, takes more than a second or names an agent outside the team.

## The caller's page: `screen`

```ruby
Agenda = Pinecall.part("agenda")

class FrontDesk < Pinecall::Agent
  scenes agenda: "the open times you last read"

  # Reads the open times of a day.
  tool shows: :agenda
  def free_slots(day:) = Clinic.free(day)

  def screen
    return Form.(**call.asking.to_h) unless call.asking.nil?

    Agenda.(day: "lunes") if call.scene == "agenda"
  end
end
```

`screen` is what the caller's page shows now: parts (`Agenda.(slots:)`, which nest), words, arrays of
them. It travels in the call's state as the public field `screen`. A tool with `shows:` puts its scene
up once it ran; a turn of the caller that showed nothing takes it away. The model is given
`show_screen` to keep a scene, put another up or take it away with `none`. `call.show(part)` puts a
part over the screen from a tool or a hook. A page that shows a task's form gives the answer with the
event `task.give`, in the model's place.
