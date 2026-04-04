import { NextRequest, NextResponse } from "next/server";
import { getHAClient } from "@/lib/ha-client";

export const dynamic = "force-dynamic";

// POST /api/habits — log a habit completion from the dashboard.
// Body: { person: string, habit: string, completed: boolean }
// Forwards the payload to the Pi via the aura_habit_log HA webhook,
// which the voice agent's webhook dispatcher picks up and hands to
// the habit tracker's log_habit() method.
export async function POST(req: NextRequest) {
  let body: { person?: string; habit?: string; completed?: boolean };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { person, habit, completed = true } = body;
  if (!person || !habit) {
    return NextResponse.json(
      { error: "person and habit are required" },
      { status: 400 }
    );
  }

  let client;
  try {
    client = getHAClient();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "HA not configured";
    return NextResponse.json({ error: msg }, { status: 503 });
  }

  try {
    await client.fireWebhook("aura_habit_log", { person, habit, completed });
    return NextResponse.json({ ok: true });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Webhook failed";
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
