# The voice app, tasks and the caller's screen

What a project adds around its agents: the numbers it answers and who answers each (the voice app),
what a tool asks the caller for in the middle of it (tasks), and what the caller sees on a page of
yours (the screen). Each is optional. The TypeScript package has the same three, word for word.

## A tool that asks: tasks

```python
from pinecall import Agent, GetEmail, tool


class FrontDesk(Agent):
    """You answer the phone for Brightside Dental."""

    tasks = [GetEmail]

    @tool
    async def book(self, slot: str) -> dict:
        """Book a time, once the caller said yes to it."""
        email = await self.ask(GetEmail)
        return clinic.book(slot, email)
```

A task is one thing a tool needs from the caller before it can finish. `await self.ask(GetEmail)`
stops the tool there: the model is told what is missing and how to ask for it, asks the caller, and
gives the answer with a tool of the task's own (`give_email`), the only tool open meanwhile. The task
checks what it was given, and one that does not pass is asked for again. Then your tool goes on with
the value, and what it returns is what the model reads, as `{"finished": "book", "result": …}`. A
tool may ask more than once, one question at a time. In a `def` tool, which runs on a thread, the
same is `self.ask(GetEmail).result()`.

Three come with the package: `GetEmail` (an address, lowercased), `GetPhone` (the digits, with the
`+` of a country code) and `GetName` (`{"first": …, "last": …}`). One of your own is `task`:

```python
import re

from pinecall import task


def plate_of(given: dict[str, str]) -> str:
    if not re.fullmatch(r"[A-Z0-9]{5,8}", given["plate"], re.I):
        raise ValueError(f'"{given["plate"]}" is not a plate. Ask for it again.')
    return given["plate"].upper()


GetPlate = task(
    "plate",
    asks="the plate of the car",
    how="Read it back letter by letter.",
    fields={"plate": "The plate, letters and digits, no spaces."},
    check=plate_of,
)
```

`fields` is what the model gives, each a string with what it is; `check` returns what your tool is
handed, and what it raises is told to the model. A class names the tasks its tools ask for in
`tasks`: each one's tool is declared with the agent, and `self.ask` of one that is not named is
refused. A call that ends with a question open makes the `await` raise, so the tool does not go on.

## The voice app: the project's lines

A project may have an `app.py` beside `agents/`: its voice app. It says which agent answers each of
the project's numbers, the words a call on that line opens with, and what every agent of the app says
to a caller who went quiet.

```python
# app.py
from pinecall import voice_app
from pinecall_agents.front_desk.agent import FrontDesk

app = voice_app("brightside", timezone="America/Los_Angeles")

app.line("+1 415 555 0134", FrontDesk, greeting="Brightside Dental. How can I help?")
app.silence(after="8s", say="Are you still there?", times=2)
```

`pinecall start` serves the agents first, each as `pinecall_agents.<folder>.agent` (a dash in the
folder's name is an underscore), and then loads `app.py`, which imports them from there. The file
holds one `voice_app(…)` at its top level. `timezone` is the zone every agent of the app reads its day
and its clock in, the same setting as a class's `timezone`. The greeting is said as written, before
any model runs: it is that agent's `greeting`, declared by the app, and `silence` is its `idle`. A
class that declares `greeting` or `idle` itself and gets one from the app too is refused when the app
loads, naming both.

### The app's page

```python
app.page("ui/dist")
```

An app may have a page of its own: the folder its build writes, inside the project. `pinecall deploy`
sends the folder with the release, and Pinecall serves it at `https://<app>--<org>.app.pinecall.io`
(`--sandbox` after the org in the sandbox). A visitor of it reaches the agent of the app's first
line, or the one `app.page(dir, answers=Billing)` names. The page asks its own name for its ticket
(`POST /pinecall/token`) and for a visitor's code (`POST /pinecall/code`); while you write it,
`pinecall start` serves the same folder and routes on `http://localhost:4747`
(`PINECALL_PAGE_PORT` names another port), with your own key and no captcha.

### What the app hears

```python
async def booked(call, visit):
    await reminders.schedule(visit)


app.on("visit.booked", booked)
```

`app.on(name, handler)` runs the handler on every entry of that name on a call of the app's agents:
an entry of the call's log by its type (`call.started`, `call.ended`, `call.score`, `handoff` for a
pass and `routed` for a line's choice), or a line an agent logs by its own name
(`self.log("visit.booked", visit)` in a tool). The handler is told the call (`id`, `agent`) and what
the entry carries; a `def` or an `async def`. One that raises is said in the terminal, and the others
run. The handlers run in the process that serves the agents: what must outlive it is a flow.

### A flow: what outlives a call

```python
from pinecall import flow


@flow("remind-visit")
async def remind_visit(visit, step):
    await step.sleep_until(visit["at"], before="24h")
    called = await step.call(
        visit["phone"], Reminder, instruction=f"Remind {visit['patient']} of the visit."
    )
    if not called.answered:
        await step.sleep("2h")
        called = await step.call(visit["phone"], Reminder)
    await step.run(lambda: db.visits.update(visit["id"], reminded=called.answered))


remind_visit.cancel_on("visit.cancelled", lambda gone, visit: gone["id"] == visit["id"])
app.on("visit.booked", remind_visit)
```

A flow is a name and an `async def` of what started it and its steps. `app.on(name, flow)` starts a
run of it on every entry of that name, with what the entry carries as its input, once per entry
however many processes hear it. The function runs in the process that serves the agents; the gateway
keeps the run (a journal of its steps, and the time, the event or the call that wakes it), so a run
outlives a deploy, a crash and a night with nothing running.

| step | what it does |
|---|---|
| `await step.sleep("2h")` | the run sleeps: a number and `s`, `m`, `h` or `d` |
| `await step.sleep_until(at, before="24h")` | until a time (a `datetime` with its zone, or an ISO string), or that long before it |
| `await step.call(to, Agent, state=, metadata=, greeting=, instruction=, from_=)` | the agent calls the number, and the step answers how the call ended: `Called(answered, reason, call)`, or at once `Called(answered=False, refused=, message=)` when the org's guards refused it |
| `await step.wait_for(event, match=, within=)` | waits for an event sent to the app whose data has what `match` names; its data, or `None` once `within` passed |
| `await step.run(effect)` | runs your own code once and keeps what it returned |
| `await step.emit(name, data)` | sends an event to the app |

Each time a run is woken its function is called again from the top, and every step already in the
journal answers what it came to without doing it again. What must happen once goes inside
`step.run`, and the function reaches its steps in the same order every time: a run whose function
asks for another step than its journal holds fails, saying which. A run sleeps or waits 90 days at
most, an org has 10000 runs waiting at most, and an input or an event is 16 KB of JSON at most.

### A rule every agent keeps

```python
app.rule("Never quote a price that is not in the price list.")
```

A rule is read into the prompt of every agent of the app, and a judge asks of each call whether it
was kept, named `app-rule-1`, `app-rule-2`, in order. A class's own `judges` stay beside them.

### A team: the call passed from one agent to another

```python
class Billing(Agent):
    """You handle charges, invoices and refunds for Brightside Dental."""

    takes = "a question about a charge, an invoice or a refund"


app.line("+1 415 555 0134", FrontDesk, greeting="Brightside Dental.", team=[Billing])
```

The agent on the call is offered one tool per teammate, named by its class (`transfer_to_billing`),
and the model calls it when the caller asks for that. A tool can pass the call itself:
`return await self.call.handoff(Billing, {"invoice": invoice})`. From the pass on, the call is the
teammate's: its instructions, tools, state and `on_call`, where `self.call.handed` is what it was
handed and `self.call.shared` is a dict the agents of one call share. A call is passed three times at
most. The agents of a team give each tool a name of its own, or the app is refused when it loads. A
spoken call takes the teammate's model and voice from its next sentence; the ears stay the first's.

### A line that chooses who answers

```python
def who(call):
    return AfterHours if clinic.is_closed(call.today) else FrontDesk


app.line("+1 415 555 0134", who, fallback=FrontDesk, team=[AfterHours, Billing])
```

`answers` may be a function (a `def` or an `async def`) of the call as a hook sees it. `fallback` is
the agent the number is pointed at; it answers when the function returns `None`, raises, takes more
than a second or names an agent outside the team, and the call's log has a `routed` line saying why.

## The caller's page: `screen()`

```python
from pinecall import Agent, part, tool

Agenda = part("agenda")
Form = part("form")


class FrontDesk(Agent):
    """You answer the phone for Brightside Dental."""

    scenes = {"agenda": "the open times you last read"}
    slots: list[str] = []

    @tool(shows="agenda")
    def free_slots(self, day: str) -> list[str]:
        """Reads the open times of a day."""
        self.slots = clinic.free(day)
        return self.slots

    def screen(self):
        asked = self.call.asking
        if asked is not None:
            return Form(task=asked.task, asks=asked.asks, fields=dict(asked.fields))
        if self.call.scene == "agenda":
            return Agenda(slots=self.slots)
        return None
```

`screen()` is what the caller's page shows now: parts (`part("agenda")(slots=…)`, which nest as
`Agenda(Slot(at="9:00"), day="lunes")`), words, and lists of them. What a part is given crosses to a
browser as JSON. It is drawn again whenever the state moves, a tool ends or a task is asked for, and
sent only when it changed. `self.call.show(Part(...))` puts a part over the screen from a tool or a
hook, and `self.call.show(None)` takes it away.

A tool with `shows` puts its scene up once it ran, and `self.call.scene` is the one up now. A turn
the caller opened in which nothing showed or kept the scene takes it away. The model is told which
scene is up and is given `show_screen`, a quiet tool it calls in the same turn as its words to keep
the scene, put another up, or take it away with `none`.

The screen travels in the call's state as the field `screen`, public to that call's own page.
`@pinecall/room` draws it. A page that shows a task's form gives the answer with the event
`task.give` (`{"task": "phone", "given": {"number": "+14155550142"}}`), in the model's place; a
value the check refuses comes back on `self.call.asking.refused`.
