"""
AURA ↔ Bravo Bridge — Business Intelligence for the Apartment Agent
====================================================================
Connects AURA's voice agent to CC's Business-Empire-Agent data so pulse
checks, greetings, and accountability nudges can reference real business
context: MRR, calendar, client health, content due dates.

Data flows in both directions:

  Bravo → AURA (read via Supabase REST API):
    - Revenue/MRR (revenue_events table)
    - Client health (leads table)
    - Content calendar (content_calendar table)
    - Active tasks (read from Supabase agent_state)

  AURA → Bravo (write to shared JSON, Bravo reads on demand):
    - Habit data (streaks, completions)
    - Presence (who's home)
    - Context mode (working, creating, casual)

All credentials come from .env — NEVER hardcoded.

Usage:
    bridge = BravoBridge()
    context = bridge.get_business_context()
    # Returns dict with mrr, clients, content_due, calendar, tasks

    bridge.push_aura_state(habits={...}, presence={...}, mode="working")

Standalone test:
    python bravo_bridge.py --test
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("aura.bravo_bridge")

# Shared state file — Bravo reads this for AURA context
AURA_STATE_FILE = Path(__file__).parent.parent / "memory" / "aura_state.json"

# Cache business context for 10 minutes (avoid hammering Supabase)
_CACHE_TTL = 600
_cache: dict[str, Any] = {}
_cache_ts: float = 0


def _load_env() -> dict[str, str]:
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent.parent / ".env"
    env_vars = dict(os.environ)
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env_vars[key.strip()] = val.strip().strip('"').strip("'")
    return env_vars


class BravoBridge:
    """Reads business data from Bravo's Supabase and pushes AURA state back."""

    def __init__(self):
        env = _load_env()
        self.supabase_url = env.get("BRAVO_SUPABASE_URL", "")
        self.supabase_key = env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY", "")
        self.enabled = bool(self.supabase_url and self.supabase_key)
        if not self.enabled:
            log.warning("BravoBridge disabled — BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY not set in .env")

    def _supabase_get(self, table: str, params: str = "", limit: int = 20) -> list[dict]:
        """Query Bravo's Supabase REST API."""
        if not self.enabled:
            return []
        try:
            import requests
            url = f"{self.supabase_url}/rest/v1/{table}?select=*&limit={limit}"
            if params:
                url += f"&{params}"
            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
            }
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            log.error(f"Supabase query failed ({r.status_code}): {r.text[:200]}")
        except Exception as e:
            log.error(f"Supabase request failed: {e}")
        return []

    # ------------------------------------------------------------------
    # Bravo → AURA: Read business context
    # ------------------------------------------------------------------

    def get_mrr(self) -> dict:
        """Get current MRR breakdown from Bravo's revenue_events table."""
        rows = self._supabase_get(
            "revenue_events",
            "type=in.(subscription_start)&order=created_at.desc"
        )
        total = sum(r.get("amount_usd", 0) for r in rows)
        clients = [
            {"name": r.get("client_name", "?"), "mrr": r.get("amount_usd", 0)}
            for r in rows if r.get("amount_usd", 0) > 0
        ]
        return {
            "total_mrr": total,
            "goal": 5000,
            "progress_pct": round(total / 5000 * 100, 1) if total else 0,
            "gap": max(0, 5000 - total),
            "clients": clients,
        }

    def get_client_health(self) -> list[dict]:
        """Get client health alerts (leads with low engagement)."""
        rows = self._supabase_get(
            "leads",
            "status=in.(won,active)&order=last_contact_at.asc.nullsfirst",
            limit=10
        )
        alerts = []
        for lead in rows:
            name = lead.get("name") or lead.get("company", "Unknown")
            last_contact = lead.get("last_contact_at")
            days_since = None
            if last_contact:
                try:
                    dt = datetime.fromisoformat(last_contact.replace("Z", "+00:00"))
                    days_since = (datetime.now(timezone.utc) - dt).days
                except Exception:
                    pass
            if days_since and days_since > 14:
                alerts.append({"name": name, "days_since_contact": days_since})
        return alerts

    def get_content_due(self) -> list[dict]:
        """Get content that's due or overdue."""
        rows = self._supabase_get(
            "content_calendar",
            "status=eq.draft&order=scheduled_for.asc",
            limit=5
        )
        items = []
        for row in rows:
            items.append({
                "platform": row.get("platform", "?"),
                "pillar": row.get("pillar", "?"),
                "scheduled": row.get("scheduled_for", "?"),
                "body_preview": (row.get("body") or "")[:60],
            })
        return items

    def get_active_tasks(self) -> str:
        """Get CC's current top priority from agent_state."""
        rows = self._supabase_get("agent_state", "order=updated_at.desc", limit=1)
        if rows:
            state = rows[0]
            return state.get("focus", state.get("current_focus", ""))
        return ""

    def get_business_context(self) -> dict:
        """Aggregated business context for AURA voice prompts.
        Cached for 10 minutes to avoid excessive API calls."""
        global _cache, _cache_ts
        if time.time() - _cache_ts < _CACHE_TTL and _cache:
            return _cache

        context = {
            "mrr": self.get_mrr(),
            "client_alerts": self.get_client_health(),
            "content_due": self.get_content_due(),
            "top_priority": self.get_active_tasks(),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _cache = context
        _cache_ts = time.time()
        return context

    def format_for_prompt(self) -> str:
        """Format business context as a concise string for Claude system prompts."""
        ctx = self.get_business_context()
        parts = []

        mrr = ctx.get("mrr", {})
        if mrr.get("total_mrr"):
            parts.append(
                f"Business: ${mrr['total_mrr']:,.0f} MRR "
                f"({mrr['progress_pct']}% of ${mrr['goal']:,} goal). "
                f"Gap: ${mrr['gap']:,.0f}."
            )

        alerts = ctx.get("client_alerts", [])
        if alerts:
            names = ", ".join(f"{a['name']} ({a['days_since_contact']}d)" for a in alerts[:3])
            parts.append(f"Client alerts: {names} — need outreach.")

        content = ctx.get("content_due", [])
        if content:
            platforms = ", ".join(c["platform"] for c in content[:3])
            parts.append(f"Content due: {len(content)} piece(s) on {platforms}.")

        priority = ctx.get("top_priority")
        if priority:
            parts.append(f"Top priority: {priority}")

        return " ".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # AURA → Bravo: Push apartment state
    # ------------------------------------------------------------------

    def push_aura_state(
        self,
        habits: dict | None = None,
        presence: dict | None = None,
        mode: str | None = None,
    ):
        """Write AURA state to a JSON file that Bravo can read."""
        state = {}
        if AURA_STATE_FILE.exists():
            try:
                state = json.loads(AURA_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                state = {}

        if habits:
            state["habits"] = habits
        if presence:
            state["presence"] = presence
        if mode:
            state["mode"] = mode
        state["updated_at"] = datetime.now(timezone.utc).isoformat()

        AURA_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        AURA_STATE_FILE.write_text(
            json.dumps(state, indent=2, default=str),
            encoding="utf-8"
        )
        log.info(f"AURA state pushed to {AURA_STATE_FILE}")

    # ------------------------------------------------------------------
    # Standalone test
    # ------------------------------------------------------------------


def _test():
    """Test the bridge by fetching business context."""
    logging.basicConfig(level=logging.INFO)
    bridge = BravoBridge()
    if not bridge.enabled:
        print("Bridge disabled — set BRAVO_SUPABASE_URL and BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env")
        return

    print("=== Business Context ===")
    ctx = bridge.get_business_context()
    print(json.dumps(ctx, indent=2, default=str))
    print()
    print("=== Prompt Format ===")
    print(bridge.format_for_prompt())
    print()
    print("=== Push Test ===")
    bridge.push_aura_state(
        habits={"gym": {"streak": 3, "today": True}, "wake_up": {"streak": 5, "today": True}},
        presence={"conaugh": "home", "adon": "away"},
        mode="working"
    )
    print(f"State written to {AURA_STATE_FILE}")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        _test()
    else:
        print("Usage: python bravo_bridge.py --test")
