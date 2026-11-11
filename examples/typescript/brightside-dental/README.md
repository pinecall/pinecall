# Brightside Dental: a voice app

A dental clinic's phone line, written as a voice app: one `app.ts` that says who answers the number,
two agents the call passes between, a flow that calls the patient back the day before, and the clinic they share. It is the example to read for an app
of more than one agent. [Clínica Norte](../clinica-norte/README.md) is the example for one agent in depth.

```text
brightside-dental/
  app.ts                          the line, who answers it, the team, the timezone, the silence, the reminder's flow
  agents/
    brightside-front-desk/
      agent.ts                    answers the line: reads the agenda, books, passes a charge on
      harness.ts                  its own judge and its own test caller
      test/agent.test.ts          the class as a class
      test/goldens/               three written calls a model must get right
    brightside-billing/
      agent.ts                    takes the call the front desk passes: invoices, refund requests
    brightside-reminder/
      agent.ts                    calls a patient the day before a visit, for the flow
  lib/clinic.ts                   the agenda, the patients and the ledger (a stand-in, in memory)
  test/team.test.ts               the pass between the two agents, on the wire
```

## The app

```ts
const app = voiceApp("brightside-dental", { timezone: "America/Los_Angeles" });

app.line("+1 415 555 0134", {
  greeting: "Brightside Dental. How can I help?",
  answers: FrontDesk,
  team: [Billing],
});

app.rule("Never say an amount of money that a tool did not give you.");
app.silence({ after: "8s", say: "Are you still there?", times: 2 });

const remindVisit = flow("remind-visit", async (booked, step) => {
  const visit = booked as unknown as Visit & { phone: string };
  if (!visit.phone.startsWith("+")) return;
  await step.sleepUntil(startsAt(visit), { before: "24h" });
  const reminder = { state: { visit: visit.id }, instruction: `Remind ${visit.patient} of the visit …` };
  let called = await step.call(visit.phone, Reminder, reminder);
  if (!called.answered && called.refused === undefined) {
    await step.sleep("2h");
    called = await step.call(visit.phone, Reminder, reminder);
  }
  await step.run(() => void clinic.reminded.push({ visit: visit.id, answered: called.answered }));
}).cancelOn("visit.cancelled", (gone, visit) => gone["id"] === visit["id"]);

app.on("visit.booked", remindVisit);
```

| line | what it does |
|---|---|
| `timezone` | every agent of the app is told the date, the weekday and the hour in Los Angeles, and `this.call.today` is that day |
| `greeting` | said as written the moment the call comes in, before any model runs |
| `answers` | the agent on the call when it starts |
| `team` | the agents the call may pass to; each says what it takes with `static takes` |
| `rule` | read into the prompt of both agents, and a judge asks of every call whether it was kept |
| `on` | what an agent logs by name (`visit.booked`) and what happens to a call (`call.ended`) reach the app: a function hears it, a flow is started by it |
| `flow` | what outlives the call: the gateway keeps where the run stands and wakes it, so the reminder is made a day later whatever was deployed meanwhile |
| `silence` | what any agent of the app says to a caller who went quiet |

## How a call goes

1. The call comes in and the caller hears the greeting.
2. `FrontDesk.onCall` looks the calling number up and puts the patient in `this.call.shared`.
3. The caller asks for a time: the model calls `freeSlots`, offers two, reads one back, and calls `book`
   after a yes. `book` refuses a time the agenda did not give, so the model cannot invent one.
4. The caller asks about a charge instead: the model calls `transfer_to_billing`, a tool nobody wrote.
   It exists because `Billing` says `static takes = "a question about a charge, …"`.
5. From there the call is `Billing`'s: its instructions, its tools, and its `onCall`, which reads the
   patient from `this.call.shared` and loads her invoices. It can take a refund request and never
   promises one.

A caller who only says "Hello?" is passed to nobody: the front desk answers.

6. `book` logs `visit.booked`, which starts a run of `remind-visit`. It sleeps until a day before the
   visit, then `Reminder` calls the patient with what the call is for and the visit as its state. Nobody
   answers: it tries once more two hours later. The patient cancels on that call: `Reminder` logs
   `visit.cancelled`, and a reminder still waiting for that visit is cancelled.

## Run it

```bash
pinecall link                     # once: the org, and its key into .env
pinecall start                    # serves both agents with app.ts, in the sandbox
pinecall chat --agent brightside-front-desk  # talk to the line in writing
pinecall test                     # the goldens, played on the agents you are holding
pnpm test                         # the unit tests: no network, no key, no model
```

Point a number of your org at `brightside-front-desk` with `pinecall numbers` to answer it by phone; until then
`pinecall start` says once that the line's number is not pointed at the agent, and the web and the
chat work all the same.

## What to know

- An agent's slug is its folder's name, and a slug is one org's in the whole gateway: these two carry
  the clinic's name for that. Rename the folders to hold them in an org where the names are taken.

- The agents of one team give each tool a name of its own: the app is refused when it loads otherwise.
- A call keeps the voice and the models of the agent that answered it, and it is listed and judged
  under that agent.
- A call is passed three times at most.
