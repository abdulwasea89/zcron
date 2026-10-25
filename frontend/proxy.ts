import { NextRequest, NextResponse } from "next/server";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/cookies";

// Route guard (Next 16 renamed `middleware` -> `proxy`). Protected app pages live under /app/*. If there's no session
// cookie, bounce to /login with a `next` back to the page they wanted.
const PROTECTED_PREFIX = "/app";

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const hasSession =
    Boolean(req.cookies.get(ACCESS_COOKIE)?.value) ||
    Boolean(req.cookies.get(REFRESH_COOKIE)?.value);

  const isAppPage = pathname.startsWith(PROTECTED_PREFIX);
  const dev = process.env.NODE_ENV === "development";
  const nonce = isAppPage && !dev ? Buffer.from(crypto.randomUUID()).toString("base64") : null;
  const csp = nonce && [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    "connect-src 'self' ws: wss: https://api.stripe.com https://*.stripe.com",
    "frame-src 'self' https://*.stripe.com",
    "form-action 'self' https://*.stripe.com",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "require-trusted-types-for 'script'",
    "trusted-types nextjs nextjs#bundler",
  ].join("; ");
  const requestHeaders = new Headers(req.headers);
  if (csp && nonce) {
    requestHeaders.set("x-nonce", nonce);
    requestHeaders.set("Content-Security-Policy", csp);
  }

  let response: NextResponse;
  if (pathname.startsWith(PROTECTED_PREFIX) && !hasSession) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    response = NextResponse.redirect(url);
  } else {
    response = csp
      ? NextResponse.next({ request: { headers: requestHeaders } })
      : NextResponse.next();
  }
  if (csp) response.headers.set("Content-Security-Policy", csp);
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("Cross-Origin-Opener-Policy", "same-origin-allow-popups");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("X-Content-Type-Options", "nosniff");
  if (!dev) {
    response.headers.set(
      "Strict-Transport-Security",
      "max-age=31536000; includeSubDomains",
    );
  }
  return response;
}

export const config = {
  matcher: ["/app/:path*", "/login", "/register"],
};
