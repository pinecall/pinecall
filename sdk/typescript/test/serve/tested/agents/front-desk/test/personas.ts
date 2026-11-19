// Fixture callers of the front desk: one of its own, one of Pinecall's switched on, and an export that is no caller.

import { ownPersona } from "../../../../../../src/index.js";

export const on = ["in-a-hurry"];

export const rush = ownPersona({ name: "in-a-rush", goal: "I want the first time you have", style: "short, interrupts" });

export const NOTE = "a line the file exports that is no caller";
