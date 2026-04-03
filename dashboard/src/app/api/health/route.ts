import { NextResponse } from "next/server";
import { getHAClient } from "@/lib/ha-client";

export const dynamic = "force-dynamic";

interface ServiceStatus {
  name: string;
  status: "online" | "offline" | "unknown";
  detail?: string;
}

interface HealthResponse {
  timestamp: string;
  ha_connected: boolean;
  ha_version?: string;
  services: ServiceStatus[];
  entity_count?: number;
}

// GET /api/health
// Returns system health: HA connection status, service statuses, entity count.
// Used by the SystemHealth dashboard component.
export async function GET() {
  const response: HealthResponse = {
    timestamp: new Date().toISOString(),
    ha_connected: false,
    services: [],
  };

  let client;
  try {
    client = getHAClient();
  } catch {
    // HA not configured
    response.services = [
      { name: "Home Assistant", status: "offline", detail: "Not configured" },
      { name: "Voice Agent", status: "unknown" },
      { name: "Clap Detector", status: "unknown" },
      { name: "Learning Engine", status: "unknown" },
    ];
    return NextResponse.json(response);
  }

  // Check HA connection
  try {
    const haOnline = await client.ping();
    response.ha_connected = haOnline;

    if (haOnline) {
      response.services.push({
        name: "Home Assistant",
        status: "online",
      });

      // Get entity count and check for service-specific entities
      const states = await client.getStates();
      response.entity_count = states.length;

      // Check voice agent status via input_boolean
      const voiceEntity = states.find(
        (s) => s.entity_id === "input_boolean.aura_voice_active"
      );
      response.services.push({
        name: "Voice Agent",
        status: voiceEntity?.state === "on" ? "online" : "offline",
        detail: voiceEntity ? `State: ${voiceEntity.state}` : "Entity not found",
      });

      // Check clap detector via input_boolean
      const clapEntity = states.find(
        (s) => s.entity_id === "input_boolean.aura_clap_active"
      );
      response.services.push({
        name: "Clap Detector",
        status: clapEntity?.state === "on" ? "online" : "offline",
        detail: clapEntity ? `State: ${clapEntity.state}` : "Entity not found",
      });

      // Check learning engine
      const learningEntity = states.find(
        (s) => s.entity_id === "input_boolean.aura_learning_active"
      );
      response.services.push({
        name: "Learning Engine",
        status: learningEntity?.state === "on" ? "online" : "offline",
        detail: learningEntity
          ? `State: ${learningEntity.state}`
          : "Entity not found",
      });
    } else {
      response.services.push({
        name: "Home Assistant",
        status: "offline",
        detail: "Ping failed",
      });
    }
  } catch (err) {
    response.services.push({
      name: "Home Assistant",
      status: "offline",
      detail: err instanceof Error ? err.message : "Connection failed",
    });
  }

  return NextResponse.json(response);
}
