/** One request to the business's API: the query or the JSON body, its answer as JSON when it is JSON. */
async function http(
  method: string,
  url: string,
  { query, body, headers, timeoutMs }: {
    query?: Record<string, unknown>;
    body?: Record<string, unknown>;
    headers: Record<string, string>;
    timeoutMs: number;
  },
): Promise<unknown> {
  const target = new URL(url);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) target.searchParams.set(key, String(value));
  }
  const sent = body === undefined ? undefined : JSON.stringify(body);
  const answer = await fetch(target, {
    method,
    headers: sent === undefined ? headers : { ...headers, "content-type": "application/json" },
    body: sent,
    redirect: "manual",
    signal: AbortSignal.timeout(timeoutMs),
  });
  const text = await answer.text();
  let read: unknown = text;
  try {
    read = text === "" ? null : JSON.parse(text);
  } catch {
    // Not JSON: the model reads the text as it came.
  }
  if (!answer.ok) throw new Error(`answered ${answer.status}: ${text.slice(0, 2000)}`);
  return read;
}
