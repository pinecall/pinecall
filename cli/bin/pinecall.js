#!/usr/bin/env node
// The bin of a checkout: the CLI straight from its source, through tsx — the loader it already
// reads a tenant's agent.ts with. What npm installs is not this file: `publishConfig.bin` points
// the published package at the compiled dist/main.js, which needs no loader at all.
import { register } from "tsx/esm/api";

register();
const { main } = await import("../src/main.ts");
process.exitCode = await main(process.argv.slice(2));
