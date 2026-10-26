import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  if (!path || path[0] !== "api" || path[1] !== "v1") {
    return NextResponse.json({ detail: "Unsupported backend path." }, { status: 404 });
  }

  const configuredBase = process.env.ARLETION_API_BASE_URL;
  const base = configuredBase || (process.env.NODE_ENV !== "production" ? "http://127.0.0.1:8000" : "");
  if (!base) {
    return NextResponse.json({ detail: "Arletion API base URL is not configured." }, { status: 503 });
  }

  const apiKey = process.env.ARLETION_API_KEY;
  if (process.env.NODE_ENV === "production" && !apiKey) {
    return NextResponse.json({ detail: "Arletion server-side API credential is not configured." }, { status: 503 });
  }

  const withScheme = /^https?:\/\//i.test(base) ? base : `http://${base}`;
  const baseWithSlash = withScheme.endsWith("/") ? withScheme : `${withScheme}/`;
  const target = new URL(`${path.join("/")}${request.nextUrl.search}`, baseWithSlash);
  const headers = new Headers({ Accept: "application/json" });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  if (apiKey) headers.set("Authorization", `Bearer ${apiKey}`);

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
      signal: AbortSignal.timeout(90_000),
    });
    const responseHeaders = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    const responseType = response.headers.get("content-type");
    if (responseType) responseHeaders.set("Content-Type", responseType);
    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const timedOut = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
    return NextResponse.json(
      { detail: timedOut ? "Arletion API request timed out." : "Arletion API is unavailable." },
      { status: timedOut ? 504 : 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
