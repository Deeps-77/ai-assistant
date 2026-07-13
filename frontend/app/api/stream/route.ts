import { NextRequest } from "next/server";

const FASTAPI = process.env.FASTAPI_URL || "http://127.0.0.1:8000";

export async function GET(req: NextRequest) {
  const threadId = req.nextUrl.searchParams.get("thread_id");
  if (!threadId) {
    return new Response("thread_id required", { status: 400 });
  }

  const upstream = await fetch(`${FASTAPI}/stream?thread_id=${encodeURIComponent(threadId)}`, {
    headers: { Accept: "text/event-stream" },
  });

  // Proxy the SSE stream directly
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
