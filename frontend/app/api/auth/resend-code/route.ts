import { NextRequest, NextResponse } from "next/server";
import { backend, BackendError } from "@/lib/backend";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const data = await backend("/auth/resend-code", {
      method: "POST",
      auth: false,
      body: { email: body.email },
    });
    return NextResponse.json(data);
  } catch (e) {
    const err = e as BackendError;
    return NextResponse.json(
      { detail: err.detail ?? "Could not resend the verification code." },
      { status: err.status ?? 500 },
    );
  }
}
