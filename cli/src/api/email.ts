/** The org's email layout as the gateway keeps it: read, written, forgotten, and tried on words. */

import type { GatewayClient } from "./client.js";

/** The HTML an agent's email is set in, and whether it is the org's own (else the plain one). */
export interface EmailLayout {
  html: string;
  own: boolean;
}

/** A reply as the contact would read it: its subject, its HTML in the layout, its plain part. */
export interface EmailPreview {
  subject: string;
  html: string;
  text: string;
}

const DOOR = "/v1/org/email/layout";

/** `GET /v1/org/email/layout`. */
export function getEmailLayout(gw: GatewayClient): Promise<EmailLayout> {
  return gw.get<EmailLayout>(DOOR);
}

/** `PUT /v1/org/email/layout`: its agents' next emails are set in it. */
export function putEmailLayout(gw: GatewayClient, html: string): Promise<EmailLayout> {
  return gw.put<EmailLayout>(DOOR, { html });
}

/** `DELETE /v1/org/email/layout`: back to the plain one. */
export async function deleteEmailLayout(gw: GatewayClient): Promise<void> {
  await gw.delete(DOOR);
}

/** `POST /v1/org/email/layout/preview`: nothing is sent. */
export function previewEmail(gw: GatewayClient, body: { text: string; subject?: string; html?: string }): Promise<EmailPreview> {
  return gw.post<EmailPreview>(`${DOOR}/preview`, body);
}
