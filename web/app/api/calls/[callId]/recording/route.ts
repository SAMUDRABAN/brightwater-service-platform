import { staffToken } from "../../../../../lib/staff";
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ callId: string }> },
) {
  const { callId } = await params;
  if (!/^[a-f0-9-]{36}$/.test(callId)) return new Response("Recording not found", { status: 404 });
  const token = await staffToken();
  if (!token) return new Response("Office connection is not configured", { status: 503 });
  try {
    const upstream = await fetch(
      `${process.env.BW_API_URL || "http://127.0.0.1:8787"}/v1/calls/${callId}/recording`,
      {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(30000),
      },
    );
    if (!upstream.ok) return new Response("Recording is unavailable", { status: upstream.status });
    return new Response(upstream.body, {
      headers: {
        "Content-Type": "audio/ogg",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return new Response("Recording connection is unavailable", { status: 503 });
  }
}
