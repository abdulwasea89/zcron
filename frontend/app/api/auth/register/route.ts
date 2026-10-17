import { NextRequest, NextResponse } from "next/server";
import { backend, BackendError } from "@/lib/backend";

// Step 1 of registration: create owner account, backend emails a 6-digit code.
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const data = await backend("/auth/register", {
      method: "POST",
      auth: false,
      body: {
        email: body.email,
        password: body.password,
        confirm_password: body.confirm_password,
      },
    });
    return NextResponse.json(data);
  } catch (e) {
    const err = e as BackendError;
    return NextResponse.json({ detail: err.detail ?? "Registration failed" }, { status: err.status ?? 500 });
  }
}
