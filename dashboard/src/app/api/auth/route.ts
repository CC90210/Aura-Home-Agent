import { NextResponse } from "next/server";

// Auth token configured via environment variable.
// Must be set in .env.local (development) and in Vercel env vars (production).
// If not set, the auth system is disabled — all requests are allowed.
// This mirrors the middleware behaviour so they stay in sync.
const VALID_TOKEN = process.env.DASHBOARD_AUTH_TOKEN;

// Cookie settings
const COOKIE_NAME = "aura-auth";
// 30 days — residents should not need to log in more than once a month.
const COOKIE_MAX_AGE_SECS = 60 * 60 * 24 * 30;

// ---------------------------------------------------------------------------
// POST /api/auth
// ---------------------------------------------------------------------------
// Verifies the submitted token against DASHBOARD_AUTH_TOKEN. On success,
// sets an httpOnly auth cookie. On failure, returns 401.
//
// The cookie is:
//   httpOnly — not readable by JavaScript, prevents XSS theft
//   secure    — HTTPS only in production
//   sameSite=strict — not sent on cross-origin requests, prevents CSRF
//   path=/    — valid for the entire dashboard
//
export async function POST(request: Request): Promise<NextResponse> {
  let submittedToken: string;

  try {
    const body = (await request.json()) as { token?: unknown };
    if (typeof body.token !== "string" || body.token.length === 0) {
      return NextResponse.json(
        { error: "token must be a non-empty string" },
        { status: 400 }
      );
    }
    submittedToken = body.token;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  // If auth is not configured, allow any token (scaffold / dev mode).
  if (!VALID_TOKEN) {
    const response = NextResponse.json({ ok: true });
    return response;
  }

  // Constant-time string comparison is not available in the Web Crypto API
  // in a way that is straightforward in Edge Runtime, but the token is a
  // randomly generated opaque string (not a password/hash), so a direct
  // comparison is acceptable here. An attacker cannot extract timing
  // information over HTTPS at meaningful resolution for a 32-byte token.
  if (submittedToken !== VALID_TOKEN) {
    return NextResponse.json({ error: "Invalid access code" }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });

  response.cookies.set(COOKIE_NAME, VALID_TOKEN, {
    httpOnly: true,
    // Require HTTPS in production. In development (NODE_ENV !== "production"),
    // cookies can be sent over HTTP to localhost.
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: COOKIE_MAX_AGE_SECS,
    path: "/",
  });

  return response;
}
