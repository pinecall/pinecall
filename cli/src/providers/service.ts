/** Providers: the vendor catalog this build runs, and the org's own provider keys, added from stdin, taken back, named but never read. */

import { z } from "zod";

import * as api from "../api/providers.js";
import type { Context } from "../context.js";
import { UsageError } from "../errors.js";

export { MODALITIES, type Catalog, type Modality, type Provider } from "../api/providers.js";

export const NO_KEY_GIVEN = "no key was given: nothing was brought";

/** What `providers` takes: one job to keep, or every vendor. */
export const ListProvidersInput = z.object({
  does: z.enum(api.MODALITIES).optional(),
});
export type ListProvidersInput = z.infer<typeof ListProvidersInput>;

/** What `providers add` takes: the vendor, and the key read off stdin, never a flag. */
export const AddProviderKeyInput = z.object({
  vendor: z.string().min(1),
  key: z.string(),
});
export type AddProviderKeyInput = z.infer<typeof AddProviderKeyInput>;

/** The vendors the org brought a key for, by name and nothing else. */
export interface ProviderKeys {
  vendors: string[];
}

/** Every vendor this build runs, or the ones that do one job; the platform's defaults ride along. */
export async function listProviders(ctx: Context, input: ListProvidersInput = {}): Promise<api.Catalog> {
  const catalog = await api.listProviders(ctx.gateway());
  const does = input.does;
  if (does === undefined) return catalog;
  return { ...catalog, providers: catalog.providers.filter((one) => one.does.includes(does)) };
}

export async function listProviderKeys(ctx: Context): Promise<ProviderKeys> {
  return { vendors: await api.listProviderKeys(ctx.gateway()) };
}

/** The org's own account with a vendor: every call of the org runs on it from the next one. The key is never echoed. */
export async function addProviderKey(ctx: Context, input: AddProviderKeyInput): Promise<{ vendor: string }> {
  const key = input.key.trim();
  if (key === "") throw new UsageError(NO_KEY_GIVEN);
  await api.putProviderKey(ctx.gateway(), input.vendor, key);
  return { vendor: input.vendor };
}

/** The vendor given back to the deployment's key, where it lends one. */
export async function removeProviderKey(ctx: Context, vendor: string): Promise<{ vendor: string }> {
  await api.deleteProviderKey(ctx.gateway(), vendor);
  return { vendor };
}

// Short names for Anthropic tiers; the provider 404s on a bare "haiku". Other names pass through,
// and a name without a vendor defaults to Anthropic.
export const SHORT_NAMES: Record<string, string> = {
  haiku: "claude-haiku-5-5",
  sonnet: "claude-sonnet-5",
  opus: "claude-opus-5",
};

/** A model as the wire names it: provider and model id, the short names expanded. */
export interface NamedModel {
  provider: string;
  model: string;
}

/**
 * `vendor/model`, or a short name, as provider and model id; undefined when it names none. The
 * model keeps every slash after the vendor's (`hf/Qwen/Qwen2.5-3B-Instruct`, `livekit/openai/gpt-5-mini`).
 */
export function parseModel(value: string): NamedModel | undefined {
  if (value === "") return undefined;
  const slash = value.indexOf("/");
  const [provider, name] = slash >= 0 ? [value.slice(0, slash), value.slice(slash + 1)] : ["anthropic", value];
  if (provider === "" || name === "") return undefined;
  return { provider, model: SHORT_NAMES[name] ?? name };
}

/** `vendor/model` with every slash after the vendor's kept (`livekit/openai/gpt-5-mini`); a short name is Anthropic's. */
export function parseModelPath(value: string): NamedModel | undefined {
  const tier = SHORT_NAMES[value];
  if (tier !== undefined) return { provider: "anthropic", model: tier };
  const slash = value.indexOf("/");
  if (slash <= 0 || slash === value.length - 1) return undefined;
  return { provider: value.slice(0, slash), model: value.slice(slash + 1) };
}

/**
 * The name as a settings field stores it. Short names expand to `anthropic/<id>`; anything else is
 * kept as typed, since the gateway accepts a bare vendor or a bare model.
 */
export function modelFieldOf(value: string): string | undefined {
  const model = parseModel(value);
  if (model === undefined) return undefined;
  return value.includes("/") || SHORT_NAMES[value] !== undefined ? `${model.provider}/${model.model}` : value;
}

/** The refusal of every flag that takes a model, named by its flag. */
export const NOT_A_MODEL = (said: string, flag = "--llm"): string =>
  `${flag} ${said} names no model: vendor/model, a vendor alone, a model alone, or one of ${Object.keys(SHORT_NAMES).join(" · ")}`;
