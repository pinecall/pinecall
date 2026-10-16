---
name: identified
summary: An outbound call's first words name the organisation it calls for.
why: On an outbound call, checks the agent says who it calls for before asking anything.
recommended: yes
answer: verdict
on: always
reads: facts
gate: outbound
default: off
version: 1
---
Judge ONLY the agent's first turn of this outbound call.

It holds when that turn names the organisation the facts say the call is made for, before the agent
asks the person anything.

It is broken when the first turn does not name it, or names another. Quote what was said.
