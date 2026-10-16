/** Every test file's setup: the fake gateway listens, forgets each test's routes after it, and refuses a request nobody answered. */

import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./gateway.js";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
