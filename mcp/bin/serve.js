#!/usr/bin/env node
// The server straight from its source, through tsx: the loader the CLI's own checkout runs on. The
// image runs this file; nothing is compiled.
import { register } from "tsx/esm/api";

register();
const { main } = await import("../src/main.ts");
process.exitCode = await main(process.argv.slice(2), process.env);
