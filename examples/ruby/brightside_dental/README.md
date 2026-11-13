# Brightside Dental: a voice app, in Ruby

The app on [pinecall.io](https://pinecall.io)'s editor, in Ruby: a dental clinic's phone line written as
a voice app. One `app.rb` says who answers the number; two agents the call passes between; a flow that
calls the patient back the day before the visit; and the clinic they share. The same app, file for
file, as the [TypeScript](../../typescript/brightside-dental/README.md) one, whose README walks a call
through it, and the [Python](../../python/brightside_dental/README.md) one.
[Clínica Norte](../clinica_norte/README.md) is the example for one agent in depth.

```text
brightside_dental/
  app.rb                                   the line, who answers it, the team, the rule, the silence, the reminder
  agents/
    clinic-front-desk/
      agent.rb                             answers the line: reads the agenda, books, passes a charge on
      harness.rb                           its own judge, and two test callers `pinecall simulate` plays
      views/clinic-front-desk.erb          what the model reads each turn: the times on the table
      test/goldens/                        three written calls a model must get right
    clinic-billing/
      agent.rb                             takes the call the front desk passes: invoices, refund requests
      views/clinic-billing.erb             the invoices of the patient on the call
  flows/remind_visit.rb                    the day before a visit, the front desk calls the patient
  lib/clinic.rb                            the agenda, the patients and the invoices (a stand-in, in memory)
```

## What is Ruby's own

- **The classes are constants.** `pinecall start` loads the agents and then `app.rb`, which names
  `FrontDesk` and `Billing` as they are; the flow and the clinic are `require_relative`.
- **The view is a template beside the class**, `views/<slug>.erb`, named by the folder whatever the
  class is called, where the TypeScript class has a `render()`.
- **What a class declares is a macro**: `stt`, `llm`, `voice`, `takes`, `judges`, `personas`, `state`;
  a tool is `tool` above a method, and the comment above it is what the model reads.

## Run it

```bash
gem install pinecall
pinecall login                               # once per machine: signs it in
pinecall start                               # serves both agents with app.rb, in the sandbox
pinecall chat --agent clinic-front-desk      # talk to the line in writing
pinecall test                                # the goldens, played on the agents you are holding
pinecall simulate --agent clinic-front-desk --persona hurried --judge   # a test caller phones it, and the judges read the call
```

In this checkout the gem is `sdk/ruby/lib`: `RUBYLIB=../../../sdk/ruby/lib` in front of each verb.
Pinecall hosts TypeScript and Python projects; a Ruby one runs where you start it
([production.md](../../../sdk/ruby/docs/production.md)).

An agent's slug is its folder's name, and a slug is one org's in the whole gateway: rename the folders
to hold them in an org where the names are taken.
