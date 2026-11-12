---
name: interrupts
summary: A caller who talks over the agent.
style: Starts speaking before the agent finishes, changes the subject mid-sentence.
tags: realism
default: off
interrupts: 0.6
version: 1
---
I want what this business offers, and I keep cutting the agent off to add details.

Expects:
- The agent should pick up the caller's latest words, not restart its own sentence.
- The agent should not lose a detail the caller gave while interrupting.
