"""
AURA Capabilities Registry
===========================
Loads the capabilities registry from ``capabilities.yaml`` and exposes
structured access methods so the intent handler and personality engine can
give informed, accurate answers when users ask what AURA can do.

Design decisions
----------------
- All content is data-driven via ``capabilities.yaml`` — adding new features
  requires only a YAML edit, not a code change.
- ``search_capabilities`` uses simple keyword overlap rather than an external
  fuzzy-matching library so there are no extra runtime dependencies.
- All public methods return plain strings or plain dicts of strings so they
  can be embedded directly in Claude system prompts without serialisation.
- Failures in YAML loading are non-fatal; a minimal fallback ensures the voice
  pipeline continues to function even if ``capabilities.yaml`` is missing.

Usage::

    caps = AuraCapabilities()
    print(caps.get_full_summary())
    print(caps.get_category_help("lighting"))
    print(caps.get_onboarding_tour())
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("aura.capabilities")

# Canonical path — sibling of this file.
_CAPABILITIES_YAML = Path(__file__).resolve().parent / "capabilities.yaml"

# Phrases that should trigger a capabilities response.
# Used by intent_handler to detect help requests before sending to Claude.
HELP_TRIGGER_PHRASES: frozenset[str] = frozenset(
    {
        "what can you do",
        "what can you do?",
        "help me",
        "help",
        "what are your capabilities",
        "what are your capabilities?",
        "what do you do",
        "what do you do?",
        "show me what you can do",
        "tell me what you can do",
        "what's possible",
        "what can aura do",
        "give me a tour",
        "how do you work",
    }
)


class AuraCapabilities:
    """
    Provides structured access to the AURA capabilities registry.

    Parameters
    ----------
    yaml_path:
        Path to ``capabilities.yaml``.  Defaults to the sibling file in the
        same directory as this module.

    Notes
    -----
    If the YAML file is missing or unparseable, the instance falls back to
    an empty registry and logs a warning.  All methods return graceful
    fallback strings rather than raising so the voice pipeline never crashes
    due to a missing capabilities file.
    """

    def __init__(self, yaml_path: Path = _CAPABILITIES_YAML) -> None:
        self._cfg: dict[str, Any] = {}
        self._yaml_path = yaml_path

        if not yaml_path.exists():
            log.warning(
                "capabilities.yaml not found at %s — capabilities registry unavailable.",
                yaml_path,
            )
            return

        try:
            with yaml_path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                self._cfg = loaded
                log.info("AuraCapabilities loaded from %s", yaml_path)
            else:
                log.warning(
                    "capabilities.yaml did not parse to a dict — registry unavailable."
                )
        except yaml.YAMLError as exc:
            log.warning("Failed to parse capabilities.yaml: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_full_summary(self) -> str:
        """
        Return a conversational overview of everything AURA can do.

        Intended for responses to "what can you do?" style questions.
        The returned string is plain prose with no markdown so it reads
        naturally when passed to ElevenLabs TTS.

        Returns
        -------
        str
            Multi-sentence summary covering all capability categories.
        """
        if not self._cfg:
            return (
                "I control your apartment — lights, music, climate, security, "
                "and smart appliances. Just tell me what you need."
            )

        intro: str = self._cfg.get("introduction", "")
        categories: dict[str, Any] = self._cfg.get("categories", {})

        if not categories:
            return intro or "I run the apartment. Ask me about anything."

        category_names: list[str] = [
            cat_data.get("name", key)
            for key, cat_data in categories.items()
            if isinstance(cat_data, dict)
        ]

        names_str = self._join_natural(category_names)
        summary = (
            f"{intro.strip()}\n\n"
            f"Here's what I cover: {names_str}. "
            f"You can ask me about any of those in detail, "
            f"or just tell me what you want and I'll figure it out."
        )
        return summary.strip()

    def get_category_help(self, category: str) -> str:
        """
        Return detailed help for a specific capability category.

        Parameters
        ----------
        category:
            The category key as it appears in capabilities.yaml
            (e.g. ``"lighting"``, ``"music"``).  Case-insensitive.

        Returns
        -------
        str
            A conversational description of what AURA can do in that
            category, including example commands.  Returns a fallback
            string if the category does not exist.
        """
        categories: dict[str, Any] = self._cfg.get("categories", {})
        key = category.lower().strip()
        cat_data: dict[str, Any] | None = categories.get(key)

        if not cat_data:
            # Try a loose match against category names
            for cat_key, data in categories.items():
                if isinstance(data, dict):
                    name: str = data.get("name", "").lower()
                    if key in name or name in key:
                        cat_data = data
                        break

        if not cat_data:
            available = ", ".join(categories.keys())
            return (
                f"I don't have a category called '{category}'. "
                f"Available categories: {available}."
            )

        name: str = cat_data.get("name", category.capitalize())
        description: str = cat_data.get("description", "")
        capabilities: list[str] = cat_data.get("capabilities", [])
        examples: list[str] = cat_data.get("example_commands", [])

        lines: list[str] = [f"{name}: {description}."]

        if capabilities:
            cap_str = ", ".join(capabilities)
            lines.append(f"I can: {cap_str}.")

        if examples:
            examples_str = self._join_natural(
                [f'"{ex}"' for ex in examples[:3]]
            )
            lines.append(f"Try saying: {examples_str}.")

        # Include protocols if this is the scenes/protocols category
        protocols: dict[str, Any] = cat_data.get("protocols", {})
        if protocols:
            protocol_names = [
                data.get("trigger", key).split("/")[0].strip()
                for key, data in protocols.items()
                if isinstance(data, dict)
            ]
            proto_str = self._join_natural(protocol_names[:5])
            lines.append(
                f"Built-in protocols include: {proto_str}, and more."
            )

        return " ".join(lines)

    def get_command_examples(self, category: str | None = None) -> str:
        """
        Return example voice commands, optionally filtered to one category.

        Parameters
        ----------
        category:
            Category key to filter by, or ``None`` to return examples
            from all categories (capped at a readable number).

        Returns
        -------
        str
            A plain-text list of example commands suitable for TTS.
        """
        categories: dict[str, Any] = self._cfg.get("categories", {})

        if not categories:
            return "Try saying: 'turn the lights to blue', 'play some lo-fi', or 'close down protocol'."

        examples: list[str] = []

        if category is not None:
            key = category.lower().strip()
            cat_data = categories.get(key, {})
            examples = cat_data.get("example_commands", []) if isinstance(cat_data, dict) else []
        else:
            # Pull up to 2 examples per category for a representative set
            for cat_data in categories.values():
                if isinstance(cat_data, dict):
                    cat_examples: list[str] = cat_data.get("example_commands", [])
                    examples.extend(cat_examples[:2])

        if not examples:
            return "I don't have examples for that category yet."

        formatted = self._join_natural([f'"{ex}"' for ex in examples[:10]])
        return f"Here are some things you can say: {formatted}."

    def get_protocol_list(self) -> str:
        """
        Return all available protocols with their trigger phrases and
        descriptions in a TTS-friendly format.

        Returns
        -------
        str
            Plain-text description of every protocol, one per sentence.
        """
        categories: dict[str, Any] = self._cfg.get("categories", {})
        scenes_cat: dict[str, Any] = categories.get("scenes_and_protocols", {})
        protocols: dict[str, Any] = scenes_cat.get("protocols", {}) if isinstance(scenes_cat, dict) else {}

        if not protocols:
            return "No protocols are configured yet."

        lines: list[str] = ["Here are my built-in protocols:"]
        for proto_data in protocols.values():
            if not isinstance(proto_data, dict):
                continue
            trigger: str = proto_data.get("trigger", "")
            description: str = proto_data.get("description", "")
            if trigger and description:
                lines.append(f"{trigger}: {description}.")

        return " ".join(lines)

    def get_scheduled_tasks(self) -> str:
        """
        Return a description of all currently configured scheduled tasks.

        These are automations that run on a timer without any trigger phrase.

        Returns
        -------
        str
            Plain-text description of scheduled tasks suitable for TTS.
        """
        tasks: list[dict[str, Any]] = self._cfg.get("scheduled_tasks", [])

        if not tasks:
            return "I don't have any scheduled tasks configured yet."

        lines: list[str] = ["Here's what I run automatically:"]
        for task in tasks:
            if not isinstance(task, dict):
                continue
            name: str = task.get("name", "")
            schedule: str = task.get("schedule", "")
            description: str = task.get("description", "")
            if name and schedule:
                line = f"{name} — {schedule}"
                if description:
                    line += f": {description}."
                lines.append(line)

        return " ".join(lines)

    def search_capabilities(self, query: str) -> str:
        """
        Search the capabilities registry for features matching the query.

        Uses keyword overlap against the ``search_keywords`` section of the
        YAML.  Returns matching categories with their descriptions and
        example commands.  Designed to answer "can you do X?" style questions.

        Parameters
        ----------
        query:
            Free-text search string from the user.

        Returns
        -------
        str
            Plain-text description of matching capabilities, or a
            "not sure, but here's everything I do" fallback.
        """
        if not query or not query.strip():
            return self.get_full_summary()

        query_lower = query.lower().strip()
        query_words: set[str] = set(query_lower.split())

        search_index: dict[str, list[str]] = self._cfg.get("search_keywords", {})
        categories: dict[str, Any] = self._cfg.get("categories", {})

        matched_keys: list[str] = []
        best_scores: dict[str, int] = {}

        for cat_key, keywords in search_index.items():
            if not isinstance(keywords, list):
                continue
            score = 0
            for kw in keywords:
                kw_lower = kw.lower()
                # Exact substring match scores higher than word match
                if kw_lower in query_lower:
                    score += 2
                elif kw_lower in query_words:
                    score += 1
            if score > 0:
                best_scores[cat_key] = score

        # Sort by score descending, take top 3
        matched_keys = sorted(best_scores, key=lambda k: best_scores[k], reverse=True)[:3]

        if not matched_keys:
            return (
                f"I'm not sure exactly what you mean by '{query}', but here's "
                f"everything I can do: {self.get_full_summary()}"
            )

        result_parts: list[str] = []
        for key in matched_keys:
            cat_data = categories.get(key)
            if not isinstance(cat_data, dict):
                continue
            name: str = cat_data.get("name", key)
            description: str = cat_data.get("description", "")
            examples: list[str] = cat_data.get("example_commands", [])[:2]
            part = f"{name}: {description}."
            if examples:
                examples_str = self._join_natural([f'"{ex}"' for ex in examples])
                part += f" For example: {examples_str}."
            result_parts.append(part)

        prefix = f"For '{query}', here's what I can do: " if len(result_parts) > 1 else ""
        return prefix + " ".join(result_parts)

    def get_onboarding_tour(self) -> str:
        """
        Return the first-time onboarding walkthrough as a single TTS-ready
        string.

        Intended for new residents or clients who have just had AURA installed.
        Covers the most important features in a natural, encouraging sequence.

        Returns
        -------
        str
            The full onboarding script as plain prose.
        """
        onboarding: dict[str, Any] = self._cfg.get("onboarding", {})

        if not onboarding:
            return (
                "Welcome. I'm Aura. I control the lights, music, and everything "
                "else in here. Just say 'Hey Aura' and tell me what you need."
            )

        welcome: str = onboarding.get("welcome_message", "").strip()
        steps: list[dict[str, Any]] = onboarding.get("tour_steps", [])

        parts: list[str] = []
        if welcome:
            parts.append(welcome)

        for step in steps:
            if not isinstance(step, dict):
                continue
            text: str = step.get("text", "").strip()
            if text:
                parts.append(text)

        return " ".join(parts)

    def get_capabilities_for_prompt(self) -> str:
        """
        Return a compact, structured summary of all capabilities formatted
        specifically for inclusion in a Claude system prompt.

        Unlike ``get_full_summary()`` (which is for TTS), this method returns
        a tightly structured block that gives Claude a complete map of AURA's
        capabilities without being verbose.

        Returns
        -------
        str
            Multi-line structured capabilities block for the system prompt.
        """
        if not self._cfg:
            return "Capabilities registry unavailable."

        categories: dict[str, Any] = self._cfg.get("categories", {})
        lines: list[str] = ["AURA CAPABILITIES:"]

        for cat_key, cat_data in categories.items():
            if not isinstance(cat_data, dict):
                continue
            name: str = cat_data.get("name", cat_key)
            description: str = cat_data.get("description", "")
            capabilities: list[str] = cat_data.get("capabilities", [])
            examples: list[str] = cat_data.get("example_commands", [])[:3]

            lines.append(f"\n[{name}] — {description}")

            if capabilities:
                for cap in capabilities:
                    lines.append(f"  • {cap}")

            if examples:
                examples_str = " | ".join(examples)
                lines.append(f"  Examples: {examples_str}")

            # Inline protocols for the scenes category
            protocols: dict[str, Any] = cat_data.get("protocols", {})
            if protocols:
                lines.append("  Protocols:")
                for proto_key, proto_data in protocols.items():
                    if not isinstance(proto_data, dict):
                        continue
                    trigger: str = proto_data.get("trigger", proto_key)
                    desc: str = proto_data.get("description", "")
                    lines.append(f"    - {trigger}: {desc}")

        # Scheduled tasks
        tasks: list[dict[str, Any]] = self._cfg.get("scheduled_tasks", [])
        if tasks:
            lines.append("\n[Scheduled Automations]")
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                task_name: str = task.get("name", "")
                schedule: str = task.get("schedule", "")
                task_desc: str = task.get("description", "")
                if task_name:
                    lines.append(f"  • {task_name} ({schedule}): {task_desc}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _join_natural(items: list[str]) -> str:
        """
        Join a list of strings with commas and 'and' for the last item.

        Examples
        --------
        ["a", "b", "c"] -> "a, b, and c"
        ["a", "b"]      -> "a and b"
        ["a"]           -> "a"
        """
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return ", ".join(items[:-1]) + f", and {items[-1]}"
