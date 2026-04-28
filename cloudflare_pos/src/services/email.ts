/**
 * Resend email client.
 */
import type { Env } from "../lib/env.js";

export interface EmailPayload {
  to?: string | string[];
  subject: string;
  html: string;
  text?: string;
}

export async function sendEmail(env: Env, p: EmailPayload): Promise<{ id?: string; ok: boolean; error?: string }> {
  if (!env.RESEND_API_KEY) return { ok: false, error: "RESEND_API_KEY not configured" };
  const to = p.to ?? env.EMAIL_TO;
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.EMAIL_FROM,
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
