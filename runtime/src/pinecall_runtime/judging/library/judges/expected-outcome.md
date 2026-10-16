---
name: expected-outcome
summary: The simulated caller's expectations were met.
why: Tells you whether a simulated caller got what it came for. Runs on simulations only.
recommended: yes
answer: verdict
on: simulations
reads: facts
gate: expectations
default: off
version: 1
---
The facts list what the simulated caller expected of the agent, one line each. Judge each line
against the conversation: yes when it happened, no when the conversation shows it did not, blocked
when the conversation never reached the point where it could happen.

It holds when every line is yes. It is broken when any line is no. Answer na when every line is
blocked. In the reason, give each line its yes, no or blocked, and the line of the conversation that
decided it.
