# Brightside Dental: a voice app

The app on [pinecall.io](https://pinecall.io)'s editor, file for file: a dental clinic's phone line
written as a voice app. One `app.ts` says who answers the number; two agents the call passes
between; a flow that calls the patient back the day before the visit; and the clinic they share. It
is the one example of the repository. The same app is written in
[Python](../../python/brightside_dental/README.md) and [Ruby](../../ruby/brightside_dental/README.md).

```text
brightside-dental/
  app.ts                          the line, who answers it, the team, the rule, the silence, the reminder
  agents/
    clinic-front-desk/
      agent.tsx                   answers the line: reads the agenda, books, passes a charge on
      judges.ts                   its own judge, beside two of Pinecall's
      personas.ts                 two test callers `pinecall simulate` plays
      test/goldens/               three written calls a model must get right
    clinic-billing/
      agent.tsx                   takes the call the front desk passes: invoices, refund requests
  flows/remind-visit.ts           the day before a visit, the front desk calls the patient
  lib/clinic.ts                   the agenda, the patients and the invoices (a stand-in, in memory)
```

## The app

```ts
const app = voiceApp("brightside", { timezone: "America/Los_Angeles" });

app.line("+1 415 555 0134", {
  greeting: "Brightside Dental. How can I help?",
  answers: FrontDesk,
  team: [Billing],
});

app.rule("Never say an amount of money that a tool did not give you.");
app.silence({ after: "8s", say: "Are you still there?", times: 2 });

app.on("visit.booked", remindVisit);
```

| line | what it does |
|---|---|
| `timezone` | every agent of the app is told the date, the weekday and the hour in Los Angeles |
| `greeting` | said as written the moment the call comes in, before any model runs |
| `answers` | the agent on the call when it starts |
| `team` | the agents the call may pass to; each says what it takes, `@agent({ takes })` |
| `rule` | read into the prompt of both agents, and a judge asks of every call whether it was kept |
| `silence` | what any agent of the app says to a caller who went quiet |
| `on` | a line an agent logs by name (`visit.booked`) starts a run of the flow |

## How a call goes

1. The call comes in and the caller hears the greeting.
2. `FrontDesk.onCall` looks the calling number up and puts the patient in `this.call.shared`.
3. The caller asks for a time: the model calls `freeSlots`, offers what the agenda gave, asks the
   caller's name and calls `book`. `book` refuses a time `freeSlots` did not return, so the model
   cannot invent one, and `render()` tells the model each turn which times are on the table.
4. The caller asks about a charge instead: the model calls `transfer_to_billing`, a tool nobody wrote.
   It exists because `Billing` says `@agent({ takes: "a question about a charge, …" })`.
5. From there the call is `Billing`'s: its instructions, its tools, its voice, and its `onCall`, which
   reads the patient from `this.call.shared` and loads her invoices. It takes a refund request and
   never promises one.
6. `book` logs `visit.booked`, which starts a run of `remind-visit`. It sleeps until a day before the
   visit, then the front desk calls the patient; nobody answers, and it tries once more two hours
   later. A visit booked from a web page has no number to ring, and the run ends there.

At hang-up the call is judged: `consent` and `grounded` are Pinecall's, `offers-a-real-time` is the
clinic's own (`judges.ts`), and `app-rule-1` is the app's rule.

## Run it

```bash
npm pkg set dependencies.@pinecall/agents=latest && npm install   # outside this repository's workspace
pinecall login                               # once per machine: signs it in
pinecall start                               # serves both agents with app.ts, in the sandbox
pinecall chat --agent clinic-front-desk      # talk to the line in writing
pinecall test                                # the goldens, played on the agents you are holding
pinecall simulate --agent clinic-front-desk --persona hurried --judge   # a test caller phones it, and the judges read the call
pinecall deploy up                           # the app on Pinecall
```

Point a number of your org at `clinic-front-desk` with `pinecall numbers` to answer it by phone; until
then the web and the chat work all the same.

## What to know

- An agent's slug is its folder's name, and a slug is one org's in the whole gateway. Rename the
  folders to hold them in an org where the names are taken.
- The agents of one team give each tool a name of its own: the app is refused when it loads otherwise.
- A spoken call passed to billing takes billing's model and voice from its next sentence. It stays
  listed and judged under the agent that answered.
