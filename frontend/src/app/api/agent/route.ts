/**
 * src/app/api/agent/route.ts
 *
 * Proxies agent chat requests to FastAPI backend.
 * Token comes from Authorization header (sent by ChatWidget via useAuth).
 *
 * POST /api/agent?stream=true  → FastAPI /api/v1/agent/chat/stream  (SSE)
 * POST /api/agent?stream=false → FastAPI /api/v1/agent/chat          (JSON)
 */

import { NextRequest, NextResponse } from "next/server";

const FASTAPI_URL =
  process.env.FASTAPI_INTERNAL_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const stream = searchParams.get("stream") !== "false";

  const authHeader = req.headers.get("authorization");
  if (!authHeader) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.text();

  const backendPath = stream
    ? "/api/v1/agent/chat/stream"
    : "/api/v1/agent/chat";

  let backendRes: Response;
  try {
    backendRes = await fetch(`${FASTAPI_URL}${backendPath}`, {
      method:  "POST",
      headers: {
        "Content-Type":  "application/json",
        "Authorization": authHeader,
      },
      body,
      // @ts-ignore — required for streaming in Node 18+
      duplex: "half",
    });
  } catch {
    return NextResponse.json(
      { error: "Could not reach backend" },
      { status: 502 }
    );
  }

  if (!backendRes.ok) {
    const error = await backendRes.text();
    return NextResponse.json(
      { error: `Backend error: ${error}` },
      { status: backendRes.status }
    );
  }

  if (!stream) {
    const data = await backendRes.json();
    return NextResponse.json(data);
  }

  return new NextResponse(backendRes.body, {
    status:  200,
    headers: {
      "Content-Type":      "text/event-stream",
      "Cache-Control":     "no-cache",
      "X-Accel-Buffering": "no",
      "Connection":        "keep-alive",
    },
  });
}