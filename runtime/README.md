# pinecall-runtime

The Pinecall runtime: one package, two processes. The **gateway** answers the API the SDKs, the
console and the carriers reach, and keeps every call's log. The **worker** runs the calls on
LiveKit. Both read one Postgres and tell each other what just happened over Redis.

```
pinecall-runtime gateway        serve the API
pinecall-runtime worker         run calls for a fleet
pinecall-runtime migrate up     bring the database to this release
```

How the code is organised, and the rules it is held to: `CONTRIBUTING.md`. How to run it on a
cluster or a laptop: the repository's `infra/README.md`.
