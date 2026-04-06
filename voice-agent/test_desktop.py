#!/usr/bin/env python3
"""
AURA Desktop Test Harness
=========================
Test the voice agent pipeline from your desktop — no Pi, no Home Assistant,
no microphone required.  Type commands, get AURA responses with full
personality, and optionally hear them spoken via ElevenLabs TTS.

Usage:
    cd voice-agent
    python test_desktop.py              # Interactive chat mode (text + TTS)
    python test_desktop.py --no-tts     # Text-only (no ElevenLabs)
    python test_desktop.py --once "turn the lights blue"   # Single command

Tests:
    - Personality and tone (casual, guest, accountability)
    - Guest mode activation / deactivation
    - Weekly reflection generation
    - Intent handler (Claude API)
    - TTS playback (ElevenLabs)
    - HA commands will gracefully fail (no Pi) — that's expected
"""

from __future__ import annotations

# ── Path setup (MUST come before stdlib imports that touch `types`) ───
# The voice-agent/ directory contains a types.py that shadows the stdlib
# `types` module.  We add it to sys.path *after* the stdlib imports have
# completed, and we import our modules via importlib to avoid the clash.
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Ensure project root is on path (for `import learning`)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# Add voice-agent dir *after* stdlib is loaded
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

import argparse
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import yaml
from personality import AuraPersonality
from guest_mode import GuestMode
from intent_handler import IntentHandler

# Optional imports
try:
    from tts import TTSEngine
    _TTS_AVAILABLE = True
except ImportError:
    _TTS_AVAILABLE = False

try:
    from stt import SpeechRecorder, Transcriber
    _STT_AVAILABLE = True
except ImportError:
    _STT_AVAILABLE = False

try:
    from weekly_reflection import WeeklyReflection
    _REFLECTION_AVAILABLE = True
except ImportError:
    _REFLECTION_AVAILABLE = False

try:
    from learning.habit_tracker import HabitTracker
    _HABITS_AVAILABLE = True
except ImportError:
    _HABITS_AVAILABLE = False


# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("aura.test")

# Quiet down noisy loggers
for name in ("httpx", "httpcore", "urllib3", "requests"):
    logging.getLogger(name).setLevel(logging.WARNING)


# ── Colour helpers (Windows terminal) ─────────────────────────────────
# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

def _c(code: int, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

CYAN = lambda t: _c(36, t)
GREEN = lambda t: _c(32, t)
YELLOW = lambda t: _c(33, t)
RED = lambda t: _c(31, t)
DIM = lambda t: _c(2, t)
BOLD = lambda t: _c(1, t)
MAGENTA = lambda t: _c(35, t)


def banner():
    print()
    print(CYAN("╔══════════════════════════════════════════════════╗"))
    print(CYAN("║") + BOLD("   AURA Desktop Test Harness                     ") + CYAN("║"))
    print(CYAN("║") + DIM("   Talk to AURA — type or speak                   ") + CYAN("║"))
    print(CYAN("║") + DIM("   HA commands will fail (no Pi) — that's fine    ") + CYAN("║"))
    print(CYAN("╠══════════════════════════════════════════════════╣"))
    print(CYAN("║") + YELLOW(" Commands:                                        ") + CYAN("║"))
    print(CYAN("║") + f"   {GREEN('/voice')}    — toggle voice mode (mic input)      " + CYAN("║"))
    print(CYAN("║") + f"   {GREEN('/guest')}    — activate guest mode               " + CYAN("║"))
    print(CYAN("║") + f"   {GREEN('/normal')}   — deactivate guest mode             " + CYAN("║"))
    print(CYAN("║") + f"   {GREEN('/reflect')}  — trigger weekly reflection          " + CYAN("║"))
    print(CYAN("║") + f"   {GREEN('/person')}   — switch speaker (cc/adon)           " + CYAN("║"))
    print(CYAN("║") + f"   {GREEN('/context')}  — switch context (casual/working/..) " + CYAN("║"))
    print(CYAN("║") + f"   {GREEN('/status')}   — show current state                 " + CYAN("║"))
    print(CYAN("║") + f"   {GREEN('/tts')}      — toggle TTS on/off                  " + CYAN("║"))
    print(CYAN("║") + f"   {GREEN('/quit')}     — exit                               " + CYAN("║"))
    print(CYAN("╚══════════════════════════════════════════════════╝"))
    print()


class DesktopTestHarness:
    """Interactive test harness for AURA voice agent components."""

    def __init__(self, tts_enabled: bool = True, voice_mode: bool = False):
        self.person: str = "conaugh"
        self.context: str = "casual"
        self.tts_enabled: bool = tts_enabled
        self.voice_mode: bool = voice_mode

        # Load config
        cfg_path = SCRIPT_DIR / "config.yaml"
        with cfg_path.open("r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        # Load secrets from env
        self.ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123")
        self.ha_token = os.getenv("HA_TOKEN", "")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
        self.elevenlabs_voice = os.getenv("ELEVENLABS_VOICE_ID", "")

        if not self.anthropic_key:
            print(RED("ERROR: ANTHROPIC_API_KEY not set in .env"))
            sys.exit(1)

        # Init components
        print(DIM("Initialising components..."))

        self.guest_mode = GuestMode()
        print(f"  {GREEN('✓')} Guest mode (active={self.guest_mode.active})")

        self.intent_handler = IntentHandler(
            ha_url=self.ha_url,
            ha_token=self.ha_token,
            anthropic_api_key=self.anthropic_key,
            config=self.config,
        )
        print(f"  {GREEN('✓')} Intent handler (Claude API)")

        self.personality = AuraPersonality()
        print(f"  {GREEN('✓')} Personality engine")

        # TTS (optional)
        self.tts: TTSEngine | None = None
        if tts_enabled and _TTS_AVAILABLE and self.elevenlabs_key and self.elevenlabs_voice:
            self.tts = TTSEngine(self.elevenlabs_key, self.elevenlabs_voice, self.config)
            print(f"  {GREEN('✓')} TTS engine (ElevenLabs)")
        elif tts_enabled:
            missing = []
            if not _TTS_AVAILABLE:
                missing.append("pydub not installed")
            if not self.elevenlabs_key:
                missing.append("ELEVENLABS_API_KEY missing")
            if not self.elevenlabs_voice:
                missing.append("ELEVENLABS_VOICE_ID missing")
            print(f"  {YELLOW('⚠')} TTS disabled: {', '.join(missing)}")
            self.tts_enabled = False
        else:
            print(f"  {DIM('○')} TTS disabled (--no-tts)")

        # Habit tracker (optional)
        self.habit_tracker = None
        if _HABITS_AVAILABLE:
            try:
                learning_cfg_path = PROJECT_ROOT / "learning" / "config.yaml"
                self.habit_tracker = HabitTracker(config_path=learning_cfg_path)
                print(f"  {GREEN('✓')} Habit tracker")
            except Exception as e:
                print(f"  {YELLOW('⚠')} Habit tracker failed: {e}")
        else:
            print(f"  {DIM('○')} Habit tracker (learning module not available)")

        # Weekly reflection (optional)
        self.weekly_reflection = None
        if _REFLECTION_AVAILABLE:
            self.weekly_reflection = WeeklyReflection(
                habit_tracker=self.habit_tracker,
                personality=self.personality,
            )
            print(f"  {GREEN('✓')} Weekly reflection")
        else:
            print(f"  {DIM('○')} Weekly reflection (module not available)")

        # Mic + STT (for voice mode)
        self.recorder = None
        self.transcriber = None
        if voice_mode and _STT_AVAILABLE:
            try:
                self.recorder = SpeechRecorder(self.config)
                print(f"  {GREEN('✓')} Microphone (SpeechRecorder)")
            except Exception as e:
                print(f"  {YELLOW('!')} Mic init failed: {e}")
            try:
                self.transcriber = Transcriber(self.config)
                print(f"  {GREEN('✓')} Speech-to-text (faster-whisper)")
            except Exception as e:
                print(f"  {YELLOW('!')} STT init failed: {e}")

            if self.recorder and self.transcriber:
                self.voice_mode = True
            else:
                print(f"  {YELLOW('!')} Voice mode disabled — mic or STT failed")
                self.voice_mode = False
        elif voice_mode:
            print(f"  {YELLOW('!')} Voice mode unavailable — install: pip install pyaudio faster-whisper")
            self.voice_mode = False

        print()

    def speak(self, text: str):
        """Speak text via TTS if enabled, always print to console."""
        print(f"\n{MAGENTA('AURA')}: {text}\n")
        if self.tts_enabled and self.tts:
            try:
                self.tts.speak(text)
            except Exception as e:
                print(f"  {RED('TTS error')}: {e}")

    def listen(self) -> str | None:
        """Record from mic and transcribe. Returns text or None on failure."""
        if not self.recorder or not self.transcriber:
            print(RED("Voice mode not available."))
            return None

        print(CYAN("  Listening... (speak now, stops on silence)"))
        audio = self.recorder.record()
        if audio is None or len(audio) == 0:
            print(YELLOW("  No audio captured."))
            return None

        print(DIM("  Transcribing..."))
        text = self.transcriber.transcribe(audio)
        if not text or not text.strip():
            print(YELLOW("  Couldn't make out what you said."))
            return None

        print(f"  {GREEN('Heard')}: {text}")
        return text.strip()

    def show_status(self):
        """Print current harness state."""
        print(f"\n{BOLD('Current State:')}")
        print(f"  Speaker:    {GREEN(self.person)}")
        print(f"  Context:    {GREEN(self.context)}")
        print(f"  Guest mode: {YELLOW('ON') if self.guest_mode.active else DIM('off')}")
        print(f"  Voice mode: {GREEN('ON') if self.voice_mode else DIM('off')}")
        print(f"  TTS:        {GREEN('ON') if (self.tts_enabled and self.tts) else DIM('off')}")
        print(f"  HA URL:     {DIM(self.ha_url)}")
        print(f"  Model:      {DIM(self.intent_handler._claude_model)}")
        print()

    def handle_command(self, text: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        cmd = text.strip().lower()

        if cmd in ("/quit", "/exit", "/q"):
            print(DIM("Goodbye."))
            return True

        if cmd == "/guest":
            reply = self.guest_mode.activate(activated_by="test_harness")
            self.context = "guest"
            self.speak(reply)
            return True

        if cmd in ("/normal", "/ungust"):
            reply = self.guest_mode.deactivate()
            self.context = "casual"
            self.speak(reply)
            return True

        if cmd == "/reflect":
            if self.weekly_reflection:
                print(DIM("Generating weekly reflection..."))
                reflection = self.weekly_reflection.generate_reflection(self.person)
                if reflection:
                    self.speak(reflection)
                else:
                    print(YELLOW("Reflection returned empty."))
            else:
                print(YELLOW("Weekly reflection module not available."))
            return True

        if cmd.startswith("/person"):
            parts = cmd.split()
            if len(parts) > 1:
                name = parts[1].lower()
                if name in ("cc", "conaugh"):
                    self.person = "conaugh"
                elif name in ("adon",):
                    self.person = "adon"
                else:
                    print(YELLOW(f"Unknown person: {name}. Use 'cc' or 'adon'."))
                    return True
                print(f"Speaker set to: {GREEN(self.person)}")
            else:
                print(f"Current speaker: {GREEN(self.person)}. Use /person cc or /person adon")
            return True

        if cmd.startswith("/context"):
            parts = cmd.split()
            if len(parts) > 1:
                ctx = parts[1].lower()
                from personality import VALID_CONTEXTS
                if ctx in VALID_CONTEXTS:
                    self.context = ctx
                    print(f"Context set to: {GREEN(self.context)}")
                else:
                    print(YELLOW(f"Unknown context. Options: {', '.join(sorted(VALID_CONTEXTS))}"))
            else:
                print(f"Current context: {GREEN(self.context)}")
            return True

        if cmd == "/status":
            self.show_status()
            return True

        if cmd == "/tts":
            if self.tts:
                self.tts_enabled = not self.tts_enabled
                print(f"TTS: {GREEN('ON') if self.tts_enabled else DIM('off')}")
            else:
                print(YELLOW("TTS not available (missing API key or pydub)."))
            return True

        if cmd == "/voice":
            if self.recorder and self.transcriber:
                self.voice_mode = not self.voice_mode
                print(f"Voice mode: {GREEN('ON') if self.voice_mode else DIM('off')}")
                if self.voice_mode:
                    print(DIM("  Press Enter to speak, type to type, /voice to toggle off"))
            else:
                print(YELLOW("Voice mode unavailable — need pyaudio + faster-whisper"))
            return True

        return False

    def process_input(self, text: str):
        """Process user input through the full pipeline."""
        # Check guest mode intents first (mirrors aura_voice.py behaviour)
        if GuestMode.is_activation_intent(text):
            reply = self.guest_mode.activate(activated_by="test_harness")
            self.context = "guest"
            self.speak(reply)
            return

        if GuestMode.is_deactivation_intent(text):
            reply = self.guest_mode.deactivate()
            self.context = "casual"
            self.speak(reply)
            return

        # Determine effective context and person
        person = self.person
        context = self.context
        habit_data = None

        if self.guest_mode.active:
            context = "guest"
            person = None  # Anonymise
            habit_data = None
        elif self.habit_tracker:
            try:
                report = self.habit_tracker.get_daily_report(self.person)
                # Convert DailyReport to the dict format personality.py expects:
                # {habit_name: {"streak": N, "days_missed": M}}
                habit_data = {}
                for entry in getattr(report, "entries", []):
                    habit_data[entry.habit_type] = {
                        "streak": 0,
                        "days_missed": 0 if entry.completed else 1,
                    }
            except Exception:
                pass

        # Get time of day
        now = datetime.now()
        time_of_day = now.strftime("%H:%M")

        # Process through intent handler
        print(DIM(f"  → Claude ({self.intent_handler._claude_model}) | person={person} | context={context} | time={time_of_day}"))
        response = self.intent_handler.process(
            user_text=text,
            person=person,
            context=context,
            time_of_day=time_of_day,
            habit_data=habit_data,
        )

        self.speak(response)

    def run_interactive(self):
        """Run the interactive test loop."""
        banner()
        self.show_status()

        if self.voice_mode:
            print(f"{BOLD('Talk to AURA:')} Press Enter to speak, or type a message. /quit to exit.\n")
        else:
            print(f"{BOLD('Talk to AURA:')} Type a message or /quit to exit. Use /voice to enable mic.\n")

        while True:
            try:
                prompt = f"{GREEN('You')} (Enter=speak): " if self.voice_mode else f"{GREEN('You')}: "
                user_input = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{DIM('Goodbye.')}")
                break

            # Empty Enter in voice mode = record from mic
            if not user_input and self.voice_mode:
                user_input = self.listen()
                if not user_input:
                    continue
            elif not user_input:
                continue

            if user_input.startswith("/"):
                if self.handle_command(user_input):
                    if user_input.strip().lower() in ("/quit", "/exit", "/q"):
                        break
                    continue

            self.process_input(user_input)

    def run_once(self, text: str):
        """Process a single command and exit."""
        self.process_input(text)


def main():
    parser = argparse.ArgumentParser(description="AURA Desktop Test Harness")
    parser.add_argument("--no-tts", action="store_true", help="Disable TTS playback")
    parser.add_argument("--voice", action="store_true", help="Enable voice mode (mic input)")
    parser.add_argument("--once", type=str, help="Process a single command and exit")
    parser.add_argument("--person", type=str, default="conaugh", help="Speaker (conaugh/adon)")
    parser.add_argument("--context", type=str, default="casual", help="Context (casual/working/...)")
    args = parser.parse_args()

    harness = DesktopTestHarness(tts_enabled=not args.no_tts, voice_mode=args.voice)

    if args.person.lower() in ("cc", "conaugh"):
        harness.person = "conaugh"
    elif args.person.lower() == "adon":
        harness.person = "adon"

    if args.context:
        harness.context = args.context

    if args.once:
        harness.run_once(args.once)
    else:
        harness.run_interactive()


if __name__ == "__main__":
    main()
