import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// ---------------------------------------------------------------------------
// Rate limiting
// ---------------------------------------------------------------------------
// In-memory store: tracks request counts per IP address.
// This resets on each serverless cold start — for persistent rate limiting
// across multiple Vercel instances, use Vercel KV or Upstash Redis.
// For a single-household dashboard, in-memory is sufficient.
const requestCounts = new Map<string, { count: number; resetTime: number }>();

// Maximum number of API requests per IP per window.
const RATE_LIMIT_MAX = 60;
// Window duration in milliseconds (1 minute).
const RATE_LIMIT_WINDOW_MS = 60 * 1000;

// ---------------------------------------------------------------------------
// Auth configuration
// ---------------------------------------------------------------------------
// When DASHBOARD_AUTH_TOKEN is set in the environment, all routes except
// /login and /api/auth require a valid auth cookie. If the variable is not
// set, authentication is disabled and all requests pass through. This allows
// the dashboard to run in scaffold/dev mode without configuration.
const AUTH_TOKEN = process.env.DASHBOARD_AUTH_TOKEN;

// Cookie name used to carry the session after successful login.
const AUTH_COOKIE_NAME = "aura-auth";

// Routes that are always accessible regardless of auth state.
const PUBLIC_PATHS = new Set(["/login", "/api/auth"]);

// ---------------------------------------------------------------------------
// Security headers
// ---------------------------------------------------------------------------
// Applied to every response regardless of auth state.
const SECURITY_HEADERS: Record<string, string> = {
  // Prevent browsers from MIME-sniffing a response away from the declared content-type.
  "X-Content-Type-Options": "nosniff",
  // Prevent this page from being embedded in an iframe on another origin (clickjacking).
  "X-Frame-Options": "DENY",
  // Enable the browser's built-in XSS filter (legacy — belt-and-suspenders alongside CSP).
  "X-XSS-Protection": "1; mode=block",
  // Limit the Referer header to the origin only when navigating cross-origin.
  "Referrer-Policy": "strict-origin-when-cross-origin",
  // Content Security Policy: tightly controls what this page is allowed to load.
  // unsafe-inline and unsafe-eval are required by Next.js for hydration and Tailwind.
  // connect-src allows ws/wss for HA WebSocket subscriptions and https for API calls.
  "Content-Security-Policy": [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' https://fonts.gstatic.com",
    "connect-src 'self' ws: wss: https:",
    "frame-ancestors 'none'",
  ].join("; "),
};

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;
  const isPublicPath = PUBLIC_PATHS.has(pathname);

  // -- Rate limiting (API routes only) -----------------------------------
  if (pathname.startsWith("/api/")) {
    // Prefer x-forwarded-for (set by Vercel/CDN) over x-real-ip.
    // Fall back to "unknown" — all unknown-IP traffic shares the same bucket
    // which is deliberately conservative.
    const ip =
      request.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
      request.headers.get("x-real-ip") ??
      "unknown";

    const now = Date.now();
    const record = requestCounts.get(ip);

    if (record && now < record.resetTime) {
      if (record.count >= RATE_LIMIT_MAX) {
        const retryAfterSecs = Math.ceil((record.resetTime - now) / 1000);
        return new NextResponse(
          JSON.stringify({ error: "Rate limit exceeded. Try again later." }),
          {
            status: 429,
            headers: {
              "Content-Type": "application/json",
              "Retry-After": String(retryAfterSecs),
              ...SECURITY_HEADERS,
            },
          }
        );
      }
      record.count += 1;
    } else {
      // First request in this window, or window has expired — start a new bucket.
      requestCounts.set(ip, { count: 1, resetTime: now + RATE_LIMIT_WINDOW_MS });
    }

    // Sweep expired entries to prevent unbounded memory growth.
    // Triggered periodically rather than on every request to keep overhead low.
    if (requestCounts.size > 1000) {
      for (const [entryIp, entryRecord] of requestCounts) {
        if (now > entryRecord.resetTime) {
          requestCounts.delete(entryIp);
        }
      }
    }
  }

  // -- Authentication gate -----------------------------------------------
  // Only active when DASHBOARD_AUTH_TOKEN is configured.
  if (AUTH_TOKEN && !isPublicPath) {
    const cookieValue = request.cookies.get(AUTH_COOKIE_NAME)?.value;

    if (cookieValue !== AUTH_TOKEN) {
      // API requests that lack auth get a 401 JSON response, not a redirect.
      // This prevents infinite redirect loops for programmatic clients and
      // gives the UI a clear signal to redirect the user to /login.
      if (pathname.startsWith("/api/")) {
        return new NextResponse(
          JSON.stringify({ error: "Unauthorized" }),
          {
            status: 401,
            headers: {
              "Content-Type": "application/json",
              ...SECURITY_HEADERS,
            },
          }
        );
      }

      // Browser navigation: redirect to the login page, preserving the
      // originally requested URL so the user is sent there after login.
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("next", pathname);
      return NextResponse.redirect(loginUrl);
    }
  }

  // -- Pass through + inject security headers ----------------------------
  const response = NextResponse.next();
  for (const [header, value] of Object.entries(SECURITY_HEADERS)) {
    response.headers.set(header, value);
  }
  return response;
}

// Run on all routes except Next.js internals and static assets.
// sw.js, offline.html, manifest.json, and icon files must be publicly
// reachable so the browser can install the PWA and register the service
// worker without hitting the auth gate.
export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon\\.ico|favicon\\.svg|manifest\\.json|sw\\.js|offline\\.html|icon-|apple-touch-icon\\.png).+)",
  ],
};
