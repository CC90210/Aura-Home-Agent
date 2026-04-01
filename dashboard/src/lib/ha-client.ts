import type {
  HAState,
  HAServiceCallPayload,
  HAWebSocketMessage,
} from "./types";

// Home Assistant REST + WebSocket API client.
// All network errors surface as thrown Error instances so callers can handle
// them with try/catch and display appropriate UI feedback.
export class HAClient {
  private readonly baseUrl: string;
  private readonly token: string;
  private ws: WebSocket | null = null;
  private wsMessageId = 1;
  private wsAuthPending = true;

  constructor(baseUrl: string, token: string) {
    // Strip trailing slash so all endpoint paths can start with /
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
  }

  // ---------------------------------------------------------------------------
  // REST helpers
  // ---------------------------------------------------------------------------

  private buildHeaders(): HeadersInit {
    return {
      Authorization: `Bearer ${this.token}`,
      "Content-Type": "application/json",
    };
  }

  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const res = await fetch(url, {
      ...options,
      headers: {
        ...this.buildHeaders(),
        ...options.headers,
      },
    });

    if (!res.ok) {
      throw new Error(
        `HA API error ${res.status} ${res.statusText} — ${path}`
      );
    }

    // Some HA endpoints return 200 with an empty body (e.g. webhook)
    const text = await res.text();
    if (!text) return {} as T;

    return JSON.parse(text) as T;
  }

  // ---------------------------------------------------------------------------
  // Entity states
  // ---------------------------------------------------------------------------

  /** Fetch all entity states from Home Assistant. */
  async getStates(): Promise<HAState[]> {
    return this.request<HAState[]>("/api/states");
  }

  /** Fetch the state for a single entity. */
  async getState(entityId: string): Promise<HAState> {
    return this.request<HAState>(`/api/states/${entityId}`);
  }

  // ---------------------------------------------------------------------------
  // Services
  // ---------------------------------------------------------------------------

  /**
   * Call a Home Assistant service.
   *
   * @param domain  HA domain, e.g. "light", "media_player", "climate"
   * @param service Service name, e.g. "turn_on", "media_play_pause"
   * @param entityId Entity to target, or omit to target no specific entity
   * @param data    Additional service call data (brightness, temperature, etc.)
   */
  async callService(
    domain: string,
    service: string,
    entityId?: string,
    data: HAServiceCallPayload = {}
  ): Promise<HAState[]> {
    const payload: HAServiceCallPayload = { ...data };
    if (entityId) {
      payload.entity_id = entityId;
    }

    return this.request<HAState[]>(`/api/services/${domain}/${service}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  // ---------------------------------------------------------------------------
  // Webhooks — used by scene buttons and clap trigger automations
  // ---------------------------------------------------------------------------

  /**
   * Fire a Home Assistant webhook automation trigger.
   *
   * @param webhookId The webhook ID configured in the HA automation
   * @param data      Optional JSON payload sent with the webhook POST
   */
  async fireWebhook(
    webhookId: string,
    data: Record<string, unknown> = {}
  ): Promise<void> {
    await this.request<unknown>(`/api/webhook/${webhookId}`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // ---------------------------------------------------------------------------
  // WebSocket — real-time state change subscriptions
  // ---------------------------------------------------------------------------

  /**
   * Open a WebSocket connection to HA and subscribe to state_changed events.
   * The callback is invoked with each incoming message after authentication.
   *
   * Call the returned cleanup function to close the connection gracefully.
   */
  subscribeToEvents(
    callback: (message: HAWebSocketMessage) => void
  ): () => void {
    const wsUrl = this.baseUrl
      .replace(/^http/, "ws")
      .replace(/^https/, "wss")
      .concat("/api/websocket");

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      // HA sends an auth_required message immediately on connect
    };

    this.ws.onmessage = (event: MessageEvent<string>) => {
      let message: HAWebSocketMessage;
      try {
        message = JSON.parse(event.data) as HAWebSocketMessage;
      } catch {
        // Malformed frame — ignore
        return;
      }

      if (message.type === "auth_required") {
        this.ws?.send(
          JSON.stringify({ type: "auth", access_token: this.token })
        );
        return;
      }

      if (message.type === "auth_ok") {
        this.wsAuthPending = false;
        // Subscribe to all state_changed events
        this.ws?.send(
          JSON.stringify({
            id: this.wsMessageId++,
            type: "subscribe_events",
            event_type: "state_changed",
          })
        );
        return;
      }

      if (message.type === "auth_invalid") {
        throw new Error("Home Assistant WebSocket auth failed — check HA_TOKEN");
      }

      if (!this.wsAuthPending) {
        callback(message);
      }
    };

    this.ws.onerror = () => {
      // Surface connection errors silently; the UI polls status independently
    };

    // Return cleanup function
    return () => {
      if (this.ws) {
        this.ws.close(1000, "Component unmounted");
        this.ws = null;
      }
    };
  }

  // ---------------------------------------------------------------------------
  // Convenience helpers
  // ---------------------------------------------------------------------------

  /** Check whether the HA API is reachable. Returns true if the /api/ endpoint
   *  responds with the expected object shape. */
  async ping(): Promise<boolean> {
    try {
      const result = await this.request<{ message: string }>("/api/");
      return result.message === "API running.";
    } catch {
      return false;
    }
  }
}

// ---------------------------------------------------------------------------
// Module-level singleton built from environment variables.
// Use this pre-built instance anywhere server or client code needs HA access.
// On the client side, only NEXT_PUBLIC_HA_URL is available; the token must
// come from a server-side API route to avoid leaking it to the browser.
// ---------------------------------------------------------------------------

/** Returns an HAClient configured from environment variables.
 *  Throws if required variables are not set. */
export function getHAClient(): HAClient {
  const url = process.env.HA_URL ?? process.env.NEXT_PUBLIC_HA_URL;
  const token = process.env.HA_TOKEN;

  if (!url) {
    throw new Error(
      "HA_URL / NEXT_PUBLIC_HA_URL environment variable is not set"
    );
  }
  if (!token) {
    throw new Error("HA_TOKEN environment variable is not set");
  }

  return new HAClient(url, token);
}
