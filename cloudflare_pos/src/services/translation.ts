/**
 * Japanese → English translation with persistent D1 cache.
 * Falls back to identity if no API key is set.
 */
import type { Env } from "../lib/env.js";

export async function translateJaToEn(env: Env, text: string): Promise<string> {
  const trimmed = text.trim();
  if (!trimmed) return "";

  const cached = await env.DB.prepare(
    "SELECT translated_text FROM translations WHERE source_text = ? AND target_lang = 'en'",
  )
    .bind(trimmed)
    .first<{ translated_text: string }>();
  if (cached) return cached.translated_text;

  if (!env.GOOGLE_TRANSLATE_API_KEY) return trimmed;

  try {
    const res = await fetch(
      `https://translation.googleapis.com/language/translate/v2?key=${env.GOOGLE_TRANSLATE_API_KEY}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q: trimmed, source: "ja", target: "en", format: "text" }),
      },
    );
    if (!res.ok) return trimmed;
    const data = (await res.json()) as {
      data?: { translations?: { translatedText: string }[] };
    };
    const translated = data.data?.translations?.[0]?.translatedText ?? trimmed;
    await env.DB.prepare(
      `INSERT OR REPLACE INTO translations (source_text, translated_text, source_lang, target_lang)
       VALUES (?, ?, 'ja', 'en')`,
    )
      .bind(trimmed, translated)
      .run();
    return translated;
  } catch {
    return trimmed;
  }
}
