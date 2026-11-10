/** The way to where the org pays: the billing page's address with a one-use login code, and the plan picked when there is one. */

import type { Credentials } from "@pinecall/core/api";
import { aLoginCode } from "@pinecall/core/login";

/** The address that signs this person in on the billing page, in the org they are working in. */
export async function billingAddress(credentials: Credentials, billingUrl: string, plan: string | null): Promise<string> {
  const there = new URL(billingUrl);
  there.searchParams.set("login", await aLoginCode(credentials));
  if (plan !== null) there.searchParams.set("plan", plan);
  return there.toString();
}
