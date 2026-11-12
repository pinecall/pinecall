---
name: honoured-stop
summary: A caller who asked not to be called again was put on the do-not-call list.
why: When a caller asks not to be called again, checks they went on the do-not-call list.
recommended: yes
answer: verdict
on: trigger
trigger: The caller asked not to be called again, to be taken off a list, or to stop receiving calls.
reads: facts
default: off
version: 1
---
The caller asked not to be called again. Judge ONLY whether that was honoured.

It holds when the facts say an opt-out was written during this call.

It is broken when the facts say no opt-out was written. Name the line the caller asked at.
