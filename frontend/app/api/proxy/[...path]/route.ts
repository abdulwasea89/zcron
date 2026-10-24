import { NextRequest, NextResponse } from "next/server";
import { backend, BackendError } from "@/lib/backend";

// Generic authenticated proxy. The browser calls /api/proxy/<backend-path>;
// this handler attaches the httpOnly access token + org header server-side and
// forwards to FastAPI. Tokens are never exposed to client JavaScript.

async function handle(req: NextRequest, path: string[]) {
  const backendPath = "/" + path.join("/");
  const search = req.nextUrl.search; // preserve query string
  const method = req.method;

  let body: unknown = undefined;
  if (method !== "GET" && method !== "DELETE") {
    if (req.headers.get("content-type")?.includes("multipart/form-data")) {
      body = await req.formData();
    } else {
      const text = await req.text();
      body = text ? JSON.parse(text) : undefined;
    }
  }

  const idempotencyKey = req.headers.get("Idempotency-Key") || undefined;

  try {
    const data = await backend(`${backendPath}${search}`, {
      method,
      body,
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    });
    return NextResponse.json(data ?? {});
  } catch (e) {
    const err = e as BackendError;
    return NextResponse.json(
      { detail: err.detail ?? "Request failed" },
      { status: err.status ?? 500 },
    );
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return handle(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return handle(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return handle(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return handle(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return handle(req, (await ctx.params).path);
}
