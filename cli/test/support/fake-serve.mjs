// A serve entry a test can script: FAKE_LINES printed on start, then it waits; SIGTERM or stdin's end is a drain.
// FAKE_DEAF=1 ignores both, so only a kill ends it; FAKE_EXITS ends it at once with that code.

const deaf = process.env.FAKE_DEAF === "1";
const leave = (why) => {
  process.stderr.write(`draining · ${why}\n`);
  process.exit(0);
};

// In place before the first line, as a real serve entry's are before it registers.
process.on("SIGTERM", () => (deaf ? undefined : leave("signalled")));
process.stdin.on("end", () => (deaf ? undefined : leave("ended")));
process.stdin.resume();
setInterval(() => undefined, 1000);

for (const line of JSON.parse(process.env.FAKE_LINES ?? "[]")) process.stdout.write(`${typeof line === "string" ? line : JSON.stringify(line)}\n`);
if (process.env.FAKE_EXITS !== undefined) process.exit(Number(process.env.FAKE_EXITS));
