import { NextResponse } from "next/server";
import { BackendError, backend } from "@/lib/backend";

// Exchange the httpOnly session cookie for a 30-second, WebSocket-only ticket.
export async function GET() {
  try {
    const data = await backend<{ token: string }>("/auth/ws-ticket", { method: "POST" });
    return NextResponse.json({ token: data.token });
  } catch (error) {
    const status = error instanceof BackendError ? error.status : 502;
    const detail = error instanceof Error ? error.message : "Could not create a realtime ticket.";
    return NextResponse.json({ detail }, { status });
  }
}
