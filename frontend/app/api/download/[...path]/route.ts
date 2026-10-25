import { NextRequest, NextResponse } from "next/server";
import { backendRaw, BackendError } from "@/lib/backend";

// Binary download proxy. The browser calls /api/download/<backend-path>; this
// handler forwards the request with auth to FastAPI and returns the raw body
// with the original Content-Type. Used for PDF invoices, receipt exports, etc.

async function handle(req: NextRequest, path: string[]) {
  const backendPath = "/" + path.join("/");
  const search = req.nextUrl.search;
  const method = req.method;

  try {
    const res = await backendRaw(`${backendPath}${search}`, { method });

    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Type": res.headers.get("Content-Type") ?? "application/octet-stream",
        "Content-Disposition": res.headers.get("Content-Disposition") ?? "attachment",
        ...(res.headers.get("Content-Length") ? { "Content-Length": res.headers.get("Content-Length")! } : {}),
      },
    });
  } catch (e) {
    const err = e as BackendError;
    return NextResponse.json(
      { detail: err.detail ?? "Download failed" },
      { status: err.status ?? 500 },
    );
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return handle(req, (await ctx.params).path);
}
