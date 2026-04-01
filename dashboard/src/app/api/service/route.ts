import { NextRequest, NextResponse } from "next/server";
import { getHAClient } from "@/lib/ha-client";

// POST /api/service
// Body: { domain: string; service: string; entity_id?: string; data?: Record<string, unknown> }
// Proxies a Home Assistant service call through the server so HA_TOKEN stays
// server-side only.
export async function POST(req: NextRequest) {
  let body: {
    domain?: string;
    service?: string;
    entity_id?: string;
    data?: Record<string, unknown>;
  };

  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { domain, service, entity_id, data = {} } = body;

  if (!domain || typeof domain !== "string") {
    return NextResponse.json({ error: "domain is required" }, { status: 400 });
  }
  if (!service || typeof service !== "string") {
    return NextResponse.json(
      { error: "service is required" },
      { status: 400 }
    );
  }

  let client;
  try {
    client = getHAClient();
  } catch (err) {
    const message = err instanceof Error ? err.message : "HA not configured";
    return NextResponse.json({ error: message }, { status: 503 });
  }

  try {
    const result = await client.callService(domain, service, entity_id, data);
    return NextResponse.json({ ok: true, result });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Service call failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
