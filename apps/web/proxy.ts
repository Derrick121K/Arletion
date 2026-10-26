import { NextRequest, NextResponse } from "next/server";

/**
 * Private-preview gate. The hosted workspace is intentionally protected with
 * HTTP Basic authentication until proper user accounts and tenant authorization
 * are implemented. Credentials are server-only environment variables.
 */
export function proxy(request: NextRequest) {
  const user = process.env.ARLETION_BASIC_AUTH_USER;
  const password = process.env.ARLETION_BASIC_AUTH_PASSWORD;

  if (process.env.NODE_ENV !== "production" && !user && !password) {
    return NextResponse.next();
  }

  if (!user || !password) {
    return new NextResponse(
      "Arletion private preview is not configured. Set ARLETION_BASIC_AUTH_USER and ARLETION_BASIC_AUTH_PASSWORD.",
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  const authorization = request.headers.get("authorization") ?? "";
  if (authorization.startsWith("Basic ")) {
    try {
      const decoded = atob(authorization.slice(6));
      if (decoded === `${user}:${password}`) {
        return NextResponse.next();
      }
    } catch {
      // Malformed base64 is treated as missing credentials.
    }
  }

  return new NextResponse("Authentication required.", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Arletion private workspace", charset="UTF-8"',
      "Cache-Control": "no-store",
    },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|healthz).*)"],
};
