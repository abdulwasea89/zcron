import { NextRequest, NextResponse } from "next/server";
import { BackendError, backend } from "@/lib/backend";

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  if (!path.length || path.some((part) => part === ".." || part.includes("/"))) {
    return NextResponse.json({ detail: "Invalid chat route." }, { status: 404 });
  }
  const method = request.method;
  const body = method === "POST" ? await request.json().catch(() => null) : undefined;
  const authorization = request.headers.get("authorization");
  try {
    const data = await backend(`/inbox/public/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, {
      method,
      auth: false,
      body,
      headers: authorization ? { Authorization: authorization } : {},
    });
    return NextResponse.json(data, { status: method === "POST" && path.at(-1) === "conversations" ? 201 : 200 });
  } catch (error) {
    const status = error instanceof BackendError ? error.status : 502;
    const detail = error instanceof BackendError ? error.detail : "Chat service is temporarily unavailable.";
    return NextResponse.json({ detail }, { status });
  }
}

export const GET = forward;
export const POST = forward;
