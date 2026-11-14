# Brightside Dental: a voice app, in Python

The app on [pinecall.io](https://pinecall.io)'s editor, in Python: a dental clinic's phone line written
as a voice app. One `app.py` says who answers the number; two agents the call passes between; a flow
that calls the patient back the day before the visit; and the clinic they share. The same app, file
for file, as the [TypeScript](../../typescript/brightside-dental/README.md) one, whose README walks a
call through it, and the [Ruby](../../ruby/brightside_dental/README.md) one.

```text
brightside_dental/
  app.py                                   the line, who answers it, the team, the rule, the silence, the reminder
  agents/
    clinic-front-desk/
      agent.py                             answers the line: reads the agenda, books, passes a charge on
      harness.py                           its own judge, and two test callers `pinecall simulate` plays
      views/clinic-front-desk.jinja        what the model reads each turn: the times on the table
      test/goldens/                        three written calls a model must get right
    clinic-billing/
      agent.py                             takes the call the front desk passes: invoices, refund requests
      views/clinic-billing.jinja           the invoices of the patient on the call
  flows/remind_visit.py                    the day before a visit, the front desk calls the patient
  lib/clinic.py                            the agenda, the patients and the invoices (a stand-in, in memory)
```

## What is Python's own

- **An agent is named by its slug.** A folder with a dash cannot be imported, so `app.py` and the flow
  name the agents by their folders' names: `app.line("+1 415 555 0134", "clinic-front-desk",
  team=["clinic-billing"])` and `step.call(phone, "clinic-front-desk", …)`. Nothing imports an agent's
  folder, and a type checker reads every line.
- **The project's own modules import by name.** `pinecall start` runs from the project's folder, so
  `from lib.clinic import clinic` reads the same from an agent, from the flow and from `app.py`.
- **The view is a template beside the class**, `views/<slug>.jinja`, where the TypeScript class has a
  `render()`.
- **The model, the ears and the voice are decorators** (`@stt`, `@llm`, `@voice`); what the agent
  takes, its judges and its test callers are fields of the class.
- **What the agents of a call share is JSON**: billing reads the patient the front desk found with a
  `match` on its shape.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install pinecall   # the CLI starts the project's own interpreter
pinecall login                               # once per machine: signs it in
pinecall start                               # serves both agents with app.py, in the sandbox
pinecall chat --agent clinic-front-desk      # talk to the line in writing
pinecall test                                # the goldens, played on the agents you are holding
pinecall simulate --agent clinic-front-desk --persona hurried --judge   # a test caller phones it, and the judges read the call
```

In this checkout the interpreter is the SDK's: `ln -sfn ../../../sdk/python/.venv .venv`, as
`make ring1` does. `make check` in `sdk/python` lints this folder and type-checks it,
strictly, from its own root.

An agent's slug is its folder's name, and a slug is one org's in the whole gateway: rename the folders,
and the names in `app.py` and the flow, to hold them in an org where they are taken.
