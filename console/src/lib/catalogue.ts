/** Vendor catalogue shared by the Providers screen and the Pipeline knobs. */

import { z } from "zod";

import { read, type Credentials } from "@pinecall/core/api";

// Same shape as GET /v1/providers and the pipeline report (runtime api/providers.py).

// Standing is computed by the runtime (providers/standing.py); never derive it from the booleans.
// `its own`: credentials that are not a single key (AWS chain, RTZR client pair).
export const READY = "ready";
export const NO_PLUGIN = "no plugin";
export const NO_KEY = "no key";
export const ITS_OWN = "its own";

/** One vendor: its modalities, names and readiness on this box. */
export const ProviderSchema = z.object({
  name: z.string(),
  does: z.array(z.enum(["llm", "stt", "tts"])),
  aliases: z.array(z.string()),
  note: z.string(),
  standing: z.enum([READY, NO_PLUGIN, NO_KEY, ITS_OWN]),
  ready: z.boolean(),
  env: z.string().nullable(),
  extra: z.string(),
  /** Whether GET /v1/voices lists this vendor's voices. */
  voices_listed: z.boolean(),
});
export type Provider = z.infer<typeof ProviderSchema>;

/** Find a vendor by name or alias (`11labs`). */
export function named(providers: readonly Provider[], word: string): Provider | undefined {
  return providers.find((provider) => provider.name === word || provider.aliases.includes(word));
}

export type Modality = Provider["does"][number];

export const MODALITIES = ["llm", "stt", "tts"] as const satisfies readonly Modality[];

/** GET /v1/providers: vendors, defaults and curated models. */
export const CatalogueSchema = z.object({
  providers: z.array(ProviderSchema),
  defaults: z.record(z.string(), z.string()),
  /** Unused here: the voice picker reads GET /v1/voices. */
  voices: z.array(z.string()),
  /** Curated models by "<modality>/<vendor>", default first. */
  models: z.record(z.string(), z.array(z.string())),
});
export type Catalogue = z.infer<typeof CatalogueSchema>;

export async function readCatalogue(credentials: Credentials): Promise<Catalogue> {
  return CatalogueSchema.parse(await read(credentials, "/v1/providers"));
}

/** Vendors for one modality, ready ones first. */
export function doing(providers: readonly Provider[], modality: Modality): Provider[] {
  return providers
    .filter((provider) => provider.does.includes(modality))
    .sort((one, other) => Number(other.ready) - Number(one.ready) || one.name.localeCompare(other.name));
}

/** Subtitle for a vendor row: its note, or what it is missing. */
export function said(provider: Provider): string {
  if (provider.standing === NO_PLUGIN) return `the box needs livekit-agents[${provider.extra}]`;
  if (provider.standing === NO_KEY) return `the box needs ${provider.env ?? "a credential"}`;
  if (provider.standing === ITS_OWN) return "its credentials are its own: a profile, a pair, not one key";
  return provider.note || "ready on this box";
}
