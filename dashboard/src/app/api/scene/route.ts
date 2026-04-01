import { NextRequest, NextResponse } from "next/server";
import { getHAClient } from "@/lib/ha-client";

// POST /api/scene
// Body: { webhook_id: string; data?: Record<string, unknown> }
// Fires a Home Assistant webhook that triggers the corresponding scene automation.
// The HA token is never exposed to the browser — it lives only in this server route.
export async function POST(req: NextRequest) {
  let body: { webhook_id?: string; data?: Record<string, unknown> };

  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { webhook_id, data = {} } = body;

  if (!webhook_id || typeof webhook_id !== "string") {
    return NextResponse.json(
      { error: "webhook_id is required" },
      { status: 400 }
    );
  }

  let client;
  try {
    client = getHAClient();
  } catch (err) {
    // HA not configured — return 503 so the UI can handle scaffold mode gracefully
    const message = err instanceof Error ? err.message : "HA not configured";
    return NextResponse.json({ error: message }, { status: 503 });
  }

  try {
    await client.fireWebhook(webhook_id, data);
    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Webhook failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
