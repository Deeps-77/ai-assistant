import { NextRequest, NextResponse } from "next/server";

const FASTAPI = process.env.FASTAPI_URL || "http://127.0.0.1:8000";

export async function GET(_: NextRequest, { params }: { params: Promise<{ threadId: string }> }) {
  const { threadId } = await params;
  try {
    const res = await fetch(`${FASTAPI}/history/${threadId}`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 503 });
  }
}
