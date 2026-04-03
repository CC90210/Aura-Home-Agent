import { NextResponse } from "next/server";
import { getHAClient } from "@/lib/ha-client";

export const dynamic = "force-dynamic";

interface PersonPresence {
  name: string;
  home: boolean;
  entity_id: string;
}

interface ActiveScene {
  name: string;
  entity_id: string;
  active: boolean;
}

interface StatsResponse {
  timestamp: string;
  presence: PersonPresence[];
  active_scenes: ActiveScene[];
  active_mode: string | null;
  lights_on: number;
  lights_total: number;
  switches_on: number;
  current_temperature?: number;
  target_temperature?: number;
}

// GET /api/stats
// Returns current apartment state: who's home, active scenes, device counts.
// Used by dashboard widgets (WhosHome, StatusBar, etc.)
export async function GET() {
  const response: StatsResponse = {
    timestamp: new Date().toISOString(),
    presence: [],
    active_scenes: [],
    active_mode: null,
    lights_on: 0,
    lights_total: 0,
    switches_on: 0,
  };

  let client;
  try {
    client = getHAClient();
  } catch {
    return NextResponse.json(response);
  }

  try {
    const states = await client.getStates();

    // Presence detection
    const personEntities = states.filter((s) =>
      s.entity_id.startsWith("person.")
    );
    response.presence = personEntities.map((p) => ({
      name: (p.attributes?.["friendly_name"] as string | undefined) ?? p.entity_id.replace("person.", ""),
      home: p.state === "home",
      entity_id: p.entity_id,
    }));

    // Light counts
    const lights = states.filter((s) => s.entity_id.startsWith("light."));
    response.lights_total = lights.length;
    response.lights_on = lights.filter((l) => l.state === "on").length;

    // Switch counts
    const switches = states.filter((s) => s.entity_id.startsWith("switch."));
    response.switches_on = switches.filter((s) => s.state === "on").length;

    // Active mode (check input_booleans that represent modes)
    const modeEntities = states.filter(
      (s) =>
        s.entity_id.startsWith("input_boolean.aura_") &&
        s.entity_id.endsWith("_active") &&
        s.state === "on"
    );
    if (modeEntities.length > 0) {
      // Extract mode name from entity_id: input_boolean.aura_studio_active → Studio
      const modeId = modeEntities[0].entity_id;
      const modeName = modeId
        .replace("input_boolean.aura_", "")
        .replace("_active", "")
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c: string) => c.toUpperCase());
      response.active_mode = modeName;
    }

    // Climate
    const climate = states.find((s) => s.entity_id.startsWith("climate."));
    if (climate) {
      response.current_temperature = climate.attributes?.["current_temperature"] as number | undefined;
      response.target_temperature = climate.attributes?.["temperature"] as number | undefined;
    }
  } catch {
    // Return partial data on error
  }

  return NextResponse.json(response);
}
