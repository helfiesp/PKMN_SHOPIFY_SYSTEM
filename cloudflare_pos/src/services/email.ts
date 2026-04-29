/**
 * Resend email client.
 */
import type { Env } from "../lib/env.js";
import { getConfig } from "../lib/config.js";

export interface EmailPayload {
  to?: string | string[];
  subject: string;
  html: string;
  text?: string;
}

export async function sendEmail(env: Env, p: EmailPayload): Promise<{ id?: string; ok: boolean; error?: string }> {
  if (!env.RESEND_API_KEY) return { ok: false, error: "RESEND_API_KEY not configured" };
  const to = p.to ?? (await getConfig(env, "EMAIL_TO"));
  const from = (await getConfig(env, "EMAIL_FROM")) || "POS <onboarding@resend.dev>";
  if (!to) return { ok: false, error: "EMAIL_TO not configured" };
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from,
      to,
      subject: p.subject,
      html: p.html,
      text: p.text,
    }),
  });
  const json = (await res.json()) as { id?: string; message?: string };
  if (!res.ok) return { ok: false, error: json.message ?? `http ${res.status}` };
  return { ok: true, id: json.id };
}
