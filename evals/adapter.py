"""AURA (home-automation voice agent) eval adapter — exercises REAL code in dry-run.

Three real suites, three real functions from voice-agent/, all offline & deterministic
(no Anthropic API key, no Home Assistant network — only pure logic + local YAML):

  local_intent  → intent_handler._try_local_intent
                  The offline utterance->action fast-path that short-circuits Claude
                  for unambiguous commands (time/date/thanks/nevermind). Locks CURRENT
                  behavior so a future edit to the matcher trips a red build.

  security_gate → security.VoiceSecurityGuard.check_action  (+ verify_pin)
                  The voice security policy: sensitive actions (lock/alarm/camera) ->
                  pin_required when a PIN is configured (blocked when not), infra
                  actions (homeassistant.stop/restart, hassio.*) -> blocked always,
                  ordinary device control -> allowed. This is the correctness suite:
                  expected = the KNOWN-correct safety verdict, not a captured snapshot.

  response_parse → intent_handler.IntentHandler._parse_response
                  Claude's JSON-response parser (3 strategies: direct json, ```json
                  fence, first {...} brace). Decides what device actions actually fire.
                  Correctness suite: malformed JSON must degrade safely, never invent
                  actions.

Not a reimplementation — these are the exact functions the live voice pipeline calls
in aura_voice.py / intent_handler.process(). The adapter patches NOTHING in the logic;
it only avoids constructing a full IntentHandler (which needs an API key) by calling the
unbound _parse_response on a bare instance, and forces the security guard offline by
configuring its PIN via the documented AURA_VOICE_PIN env override.

mistakes → mined from memory/MISTAKES.md (see eval_mine_mistakes.py); scored
needs-model until each is wired to a deterministic check (honest pending, never fake).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VOICE_AGENT = REPO / "voice-agent"
sys.path.insert(0, str(VOICE_AGENT))


def _meta(cd: Path) -> dict:
    m, f = {}, cd / "meta.yaml"
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ":" in ln and not ln.strip().startswith("#"):
                k, _, v = ln.partition(":")
                m[k.strip()] = v.strip()
    return m


def _task_lines(cd: Path) -> list[str]:
    """Non-comment, non-blank lines of task.md."""
    txt = (cd / "task.md").read_text(encoding="utf-8")
    return [l.rstrip("\n") for l in txt.splitlines()
            if l.strip() and not l.strip().startswith("#")]


# ---------------------------------------------------------------------------
# Suite 1 — local utterance -> action fast-path  (regression / lock-behavior)
# ---------------------------------------------------------------------------
def _local_intent(cd: Path) -> dict:
    import intent_handler as ih
    lines = _task_lines(cd)
    utterance = lines[0] if lines else ""
    result = ih._try_local_intent(utterance)
    if result is None:
        # No local match -> would fall through to Claude (the API path).
        return {"matched": False, "response": None, "n_actions": None}
    return {
        "matched": True,
        "response": result.get(ih._RESPONSE_KEY, ""),
        "n_actions": len(result.get(ih._ACTIONS_KEY, [])),
    }


# ---------------------------------------------------------------------------
# Suite 2 — voice security gate  (correctness; the money-gate analog)
# ---------------------------------------------------------------------------
def _security_gate(cd: Path) -> dict:
    from security import VoiceSecurityGuard
    lines = _task_lines(cd)
    # task.md line 1 = "domain.service"; optional line 2 = "pin: <value>"
    action = lines[0] if lines else ""
    domain, _, service = action.partition(".")

    pin = None
    for ln in lines[1:]:
        if ln.strip().lower().startswith("pin:"):
            pin = ln.split(":", 1)[1].strip()

    # Configure the guard exactly as production does. A configured PIN exercises
    # the pin_required path; no PIN exercises the fail-safe (sensitive -> blocked).
    cfg = VOICE_AGENT_CONFIG if VOICE_AGENT_CONFIG.exists() else None
    if pin:
        os.environ["AURA_VOICE_PIN"] = pin
    else:
        os.environ.pop("AURA_VOICE_PIN", None)
    guard = VoiceSecurityGuard(config_path=cfg)

    status, _msg = guard.check_action(domain, service)
    return {"status": status, "action": action}


# ---------------------------------------------------------------------------
# Suite 3 — Claude JSON response parser  (correctness; controls what fires)
# ---------------------------------------------------------------------------
def _response_parse(cd: Path) -> dict:
    import intent_handler as ih
    raw = (cd / "task.md").read_text(encoding="utf-8")
    # task.md is the literal model output. Strip a leading comment line if present
    # (lines starting with '#') so cases can be self-documenting.
    body = "\n".join(
        l for l in raw.splitlines() if not l.lstrip().startswith("# ")
    ).strip()
    # Call the real parser without building a full IntentHandler (no API key needed):
    # _parse_response uses self only for logging.
    inst = ih.IntentHandler.__new__(ih.IntentHandler)
    parsed = ih.IntentHandler._parse_response(inst, body)
    return {
        "response": parsed.get(ih._RESPONSE_KEY, ""),
        "n_actions": len(parsed.get(ih._ACTIONS_KEY, [])),
    }


def _mistakes(_cd: Path) -> dict:
    # Mined from MISTAKES.md as a regression backlog. Each becomes a real check
    # only once wired to a deterministic assertion that would have caught it;
    # until then it is honestly needs-model, never a fake pass.
    return {"verdict": "needs-model"}


VOICE_AGENT_CONFIG = VOICE_AGENT / "config.yaml"

DISPATCH = {
    "local_intent": _local_intent,
    "security_gate": _security_gate,
    "response_parse": _response_parse,
    "mistakes": _mistakes,
}


def run_case(case_dir) -> dict:
    cd = Path(case_dir)
    suite = _meta(cd).get("suite") or cd.parent.name
    fn = DISPATCH.get(suite)
    if fn is None:
        raise NotImplementedError(f"no adapter wired for suite {suite!r}")
    return fn(cd)
