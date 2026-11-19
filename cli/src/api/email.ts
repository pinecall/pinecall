/** The org's email layout as the gateway keeps it: read, written, forgotten, and tried on words. */

import type { GatewayClient } from "./client.js";

/** The HTML an agent's email is set in, whether it is the org's own (else the plain one), and whether its emails go as text alone, with no HTML. */
export interface EmailLayout {
  html: string;
  own: boolean;
  text_only?: boolean;
}

/** A reply as the contact would read it: its subject, its HTML in the layout (none when it goes as text alone), its plain part. */
export interface EmailPreview {
  subject: string;
  html: string | null;
  text: string;
}

/** What a preview is asked with: the words, the subject they answer, a layout to try, or the email as text alone. */
export interface PreviewBody {
  text: string;
  subject?: string;
  html?: string;
  text_only?: boolean;
  /** Try it in the plain layout, whatever the org keeps. */
  plain?: boolean;
}

const DOOR = "/v1/org/email/layout";

/** `GET /v1/org/email/layout`. */
export function getEmailLayout(gw: GatewayClient): Promise<EmailLayout> {
  return gw.get<EmailLayout>(DOOR);
}

/** `PUT /v1/org/email/layout`: its agents' next emails are set in the HTML, or go as text alone. */
export function putEmailLayout(gw: GatewayClient, kept: { html: string } | { text_only: true }): Promise<EmailLayout> {
  return gw.put<EmailLayout>(DOOR, kept);
}

/** `DELETE /v1/org/email/layout`: back to the plain one. */
export async function deleteEmailLayout(gw: GatewayClient): Promise<void> {
  await gw.delete(DOOR);
}

/** `POST /v1/org/email/layout/preview`: nothing is sent. */
export function previewEmail(gw: GatewayClient, body: PreviewBody): Promise<EmailPreview> {
  return gw.post<EmailPreview>(`${DOOR}/preview`, body);
}
