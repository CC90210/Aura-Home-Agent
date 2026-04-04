import { NextRequest, NextResponse } from "next/server";
import { getHAClient } from "@/lib/ha-client";

export const dynamic = "force-dynamic";

// GET /api/drops — list saved AURA Drops
// Calls the HA webhook dispatcher which routes to AuraDrops.list_drops()
export async function GET() {
  let client;
  try {
    client = getHAClient();
  } catch {
    return NextResponse.json({ drops: [] });
  }

  try {
    // Call the voice agent's drops listing endpoint via HA REST API
    // The voice agent exposes drop management through webhook handlers
    const states = await client.getStates();

    // Check if AURA voice agent is running
    const voiceActive = states.find(
      (s) => s.entity_id === "input_boolean.aura_voice_active"
    );

    if (!voiceActive || voiceActive.state !== "on") {
      return NextResponse.json({
        drops: [],
        message: "Voice agent offline — drops unavailable",
      });
    }

    // For now, return empty until the Pi is connected.
    // When live, this will query the drops database through the webhook dispatcher.
    return NextResponse.json({ drops: [] });
  } catch {
    return NextResponse.json({ drops: [] });
  }
}

// POST /api/drops — activate a saved drop
// Body: { name: string }
export async function POST(req: NextRequest) {
  let body: { name?: string };

  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { name } = body;
  if (!name || typeof name !== "string") {
    return NextResponse.json({ error: "name is required" }, { status: 400 });
  }

  let client;
  try {
    client = getHAClient();
  } catch (err) {
    const message = err instanceof Error ? err.message : "HA not configured";
    return NextResponse.json({ error: message }, { status: 503 });
  }

  try {
    // Fire a webhook to the voice agent to activate the drop
    await client.fireWebhook("aura_activate_drop", { name });
    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Drop activation failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
