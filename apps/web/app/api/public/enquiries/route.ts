import { createHash } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const attempts = new Map<string, { count: number; resetAt: number }>();
const WINDOW_MS = 15 * 60 * 1000;
const LIMIT = 5;

export async function POST(request: NextRequest) {
  if (request.headers.get("origin") !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Request origin is not allowed." }, { status: 403 });
  }

  const address = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
  const key = createHash("sha256").update(address).digest("hex");
  const now = Date.now();
  for (const [entry, value] of attempts) if (value.resetAt <= now) attempts.delete(entry);
  const current = attempts.get(key);
  if (current && current.resetAt > now && current.count >= LIMIT) {
    return NextResponse.json({ detail: "Too many submissions. Please try again later." }, { status: 429 });
  }
  attempts.set(key, current && current.resetAt > now
    ? { ...current, count: current.count + 1 }
    : { count: 1, resetAt: now + WINDOW_MS });

  const raw = await request.text();
  if (raw.length > 12_000) return NextResponse.json({ detail: "Submission is too large." }, { status: 413 });

  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ detail: "Invalid form submission." }, { status: 400 });
  }
  if (typeof payload.website === "string" && payload.website.trim()) {
    return NextResponse.json({ accepted: true }, { status: 202 });
  }
  delete payload.website;

  const base = process.env.ARLETION_API_BASE_URL;
  const apiKey = process.env.ARLETION_API_KEY;
  if (!base || !apiKey) {
    return NextResponse.json({ detail: "Public enquiries are not configured." }, { status: 503 });
  }

  try {
    const response = await fetch(new URL("/api/v1/public/consumer-enquiries", base), {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    const body = await response.json().catch(() => ({ detail: "The enquiry service returned an unreadable response." }));
    return NextResponse.json(body, { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "The enquiry service is temporarily unavailable. Please try again later." }, { status: 502 });
  }
}
