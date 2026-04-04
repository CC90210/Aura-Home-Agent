import { NextRequest, NextResponse } from "next/server";
import { getHAClient } from "@/lib/ha-client";

export const dynamic = "force-dynamic";

// POST /api/mirror-mode — trigger Mirror Mode with a mood phrase.
// Body: { mood: string }
// Forwards the mood to the Pi via the aura_mirror_mode HA webhook,
// which the voice agent's webhook dispatcher calls mirror_mode.activate()
// and speaks a confirmation back through the speakers.
export async function POST(req: NextRequest) {
  let body: { mood?: string };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { mood } = body;
  if (!mood || typeof mood !== "string") {
    return NextResponse.json({ error: "mood is required" }, { status: 400 });
  }

  let client;
  try {
    client = getHAClient();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "HA not configured";
    return NextResponse.json({ error: msg }, { status: 503 });
  }

  try {
    await client.fireWebhook("aura_mirror_mode", { mood });
    return NextResponse.json({ ok: true });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Webhook failed";
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
