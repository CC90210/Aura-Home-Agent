#!/usr/bin/env python3
"""pointer_sync.py — stamp Aura's operating card into the per-tool pointer files.

Why this exists (2026-09-27): Cursor, Windsurf, Cline, GitHub Copilot, Roo Code,
Kilo Code, Continue, Junie and Trae each read their OWN rules file and never open
AGENTS.md or CLAUDE.md. Without a pointer file, an AI opened inside one of those
tools wakes up with no idea it is Aura, no NEVER list, and no four-line report.
Every pointer file therefore carries the same `operating_card` LOCKSTEP block the
five entry points carry, plus a three-line header that names the tool and sends
it to AGENTS.md for the full contract.

Why a separate script (not genome_sync.py): genome_sync.py is shared substrate,
kept byte-identical across the sibling agents (Bravo, Atlas, Maven) and pinned
by the empire harness. Its job is the five entry points. This file is
Aura-owned (copied from Maven's CMO-Agent on 2026-09-27; only the agent and repo
name strings and the POINTER_FILES table differ), follows the same contract (seed = PERSONAL.md, blocks replaced
between existing markers, --check exits 1 on drift), and can be adopted by a
sibling by copying it and editing the POINTER_FILES table only.

CLI (run from the repo root):
  python scripts/pointer_sync.py            # stamp: create missing pointer files, refresh the block
  python scripts/pointer_sync.py --check    # verify only; exit 1 on any drift (CI gate)
  python scripts/pointer_sync.py --root DIR # act on another checkout (used by the tests)

Rules:
  - The card is read from PERSONAL.md's `operating_card` block. Edit it THERE,
    then run this script (and scripts/genome_sync.py for the entry points).
  - A pointer file that already carries the marker pair keeps everything
    outside the markers (its narration) and gets only the block refreshed.
  - A pointer file that exists WITHOUT markers is never overwritten: the block
    is appended below the existing text, so a hand-written rules file survives.
  - `.aider.conf.yml` is YAML and cannot hold markdown, so it is a STATIC
    pointer: its whole expected text is fixed here and checked byte-for-byte.
  - Windows is production: pathlib everywhere, UTF-8, LF line endings written
    explicitly so a CRLF checkout never produces a false drift.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_NAME = "PERSONAL.md"
BLOCK = "operating_card"

# Same marker grammar as scripts/genome_sync.py — kept in sync by hand on
# purpose (importing genome_sync would couple this Maven-owned tool to shared
# substrate that may be re-vendored under us).
LOCKSTEP_RE = re.compile(
    r"<!--\s*LOCKSTEP:([A-Za-z0-9_-]+)\s*-->(.*?)<!--\s*/LOCKSTEP:\1\s*-->",
    re.DOTALL,
)
OPENER_RE = re.compile(r"<!--\s*LOCKSTEP:([A-Za-z0-9_-]+)\s*-->")
CLOSER_RE = re.compile(r"<!--\s*/LOCKSTEP:([A-Za-z0-9_-]+)\s*-->")

try:  # Windows consoles default to cp1252; the card has em dashes and arrows.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover — non-reconfigurable stdout (older runtimes)
    pass


def _header(tool: str) -> str:
    """The three-line header every card carrier opens with."""
    return (
        f"You are Aura inside {tool}.\n"
        "Read AGENTS.md for the full contract.\n"
        "This card is the minimum.\n"
    )


# path (relative to the repo root) -> header template written ABOVE the block.
# Add a tool here and re-run the stamp; nothing else needs to change.
POINTER_FILES: dict[str, str] = {
    # Cursor wants YAML frontmatter; alwaysApply makes it load in every session.
    ".cursor/rules/aura-operating-card.mdc": (
        "---\n"
        "description: Aura operating card (aura-home-agent). Read first in every session, whatever model you are.\n"
        "globs:\n"
        "alwaysApply: true\n"
        "---\n"
        + _header("Cursor")
    ),
    ".windsurf/rules/aura-operating-card.md": _header("Windsurf"),
    ".clinerules/aura-operating-card.md": _header("Cline"),
    ".github/copilot-instructions.md": _header("GitHub Copilot"),
    ".roo/rules/aura-operating-card.md": _header("Roo Code"),
    ".kilocode/rules/aura-operating-card.md": _header("Kilo Code"),
    ".continue/rules/aura-operating-card.md": _header("Continue"),
    ".junie/guidelines.md": _header("Junie"),
    ".trae/rules/project_rules.md": _header("Trae"),
}

# Whole-file pointers whose format cannot carry a markdown block.
STATIC_POINTERS: dict[str, str] = {
    ".aider.conf.yml": (
        "# Aura (aura-home-agent) — aider configuration, stamped by scripts/pointer_sync.py (2026-09-27).\n"
        "# `read:` loads AGENTS.md (the operating card + the full contract) into every aider\n"
        "# chat as read-only context, so aider wakes up as Aura too. Never list .env* here.\n"
        "read:\n"
        "  - AGENTS.md\n"
    ),
}

FOOTER = (
    "\n<!-- Stamped by scripts/pointer_sync.py from PERSONAL.md. "
    "Do not hand-edit the block above: edit PERSONAL.md, then run "
    "`python scripts/pointer_sync.py` (and `python scripts/genome_sync.py` for the entry points). -->\n"
)


def _read(path: Path) -> str:
    # read_text() applies universal newlines, so a CRLF checkout compares as LF.
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _blocks(text: str, where: str) -> dict[str, str]:
    """Extract LOCKSTEP blocks; abort on duplicate/nested/unclosed markers."""
    openers = Counter(m.group(1) for m in OPENER_RE.finditer(text))
    closers = Counter(m.group(1) for m in CLOSER_RE.finditer(text))
    bad = {n for n in (set(openers) | set(closers))
           if openers.get(n, 0) != 1 or closers.get(n, 0) != 1}
    if bad:
        raise SystemExit(
            f"ERROR {where}: malformed LOCKSTEP markers (duplicate/nested/unclosed): "
            f"{sorted(bad)} — fix the markers by hand before syncing.")
    return {m.group(1): m.group(2) for m in LOCKSTEP_RE.finditer(text)}


def _wrap(content: str) -> str:
    return f"<!-- LOCKSTEP:{BLOCK} -->{content}<!-- /LOCKSTEP:{BLOCK} -->\n"


def render(header: str, content: str) -> str:
    """A freshly created pointer file: header, blank line, block, footer."""
    return header + "\n" + _wrap(content) + FOOTER


def _stamp_block(text: str, content: str) -> str:
    pattern = re.compile(
        rf"(<!--\s*LOCKSTEP:{re.escape(BLOCK)}\s*-->).*?(<!--\s*/LOCKSTEP:{re.escape(BLOCK)}\s*-->)",
        re.DOTALL,
    )
    return pattern.sub(lambda m: m.group(1) + content + m.group(2), text, count=1)


def load_card(root: Path) -> str:
    """The operating_card block content from the seed (markers excluded)."""
    seed = root / SEED_NAME
    if not seed.exists():
        raise SystemExit(f"ERROR: seed missing: {seed}")
    blocks = _blocks(_read(seed), where=SEED_NAME)
    if BLOCK not in blocks:
        raise SystemExit(f"ERROR: {SEED_NAME} defines no LOCKSTEP:{BLOCK} block")
    return blocks[BLOCK]


def run(root: Path, check: bool) -> int:
    """Stamp (or verify) every pointer. Returns the process exit code."""
    content = load_card(root)
    drift = 0
    changed = 0

    for rel, header in POINTER_FILES.items():
        path = root / rel
        if not path.exists():
            if check:
                print(f"DRIFT {rel}: pointer file missing (run `python scripts/pointer_sync.py`)")
                drift += 1
            else:
                _write(path, render(header, content))
                print(f"created: {rel}")
                changed += 1
            continue
        text = _read(path)
        have = _blocks(text, where=rel)
        if BLOCK not in have:
            if check:
                print(f"DRIFT {rel}: marker pair LOCKSTEP:{BLOCK} missing")
                drift += 1
            else:
                # Hand-written rules file: keep it, put the card underneath.
                sep = "" if text.endswith("\n") else "\n"
                _write(path, text + sep + "\n" + _wrap(content) + FOOTER)
                print(f"appended: {rel} (existing text kept above the block)")
                changed += 1
            continue
        if have[BLOCK] != content:
            if check:
                print(f"DRIFT {rel}: LOCKSTEP:{BLOCK} differs from {SEED_NAME}")
                drift += 1
            else:
                _write(path, _stamp_block(text, content))
                print(f"stamped: {rel}")
                changed += 1

    for rel, expected in STATIC_POINTERS.items():
        path = root / rel
        existed = path.exists()  # decided BEFORE the write, or "created" can never print
        if existed and _read(path) == expected:
            continue
        if check:
            why = "differs from the expected text" if existed else "missing"
            print(f"DRIFT {rel}: {why}")
            drift += 1
        else:
            _write(path, expected)
            print(f"{'rewritten' if existed else 'created'}: {rel}")
            changed += 1

    if check:
        print("pointer-sync check: " + ("CLEAN" if drift == 0 else f"{drift} drift(s)"))
        return 0 if drift == 0 else 1
    total = len(POINTER_FILES) + len(STATIC_POINTERS)
    print(f"pointer-sync: {changed} file(s) written, {total} pointer(s) carry the card")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Stamp PERSONAL.md's operating_card block into every per-tool pointer file "
                    "(Cursor, Windsurf, Cline, Copilot, Roo, Kilo, Continue, Junie, Trae, aider).")
    p.add_argument("--check", action="store_true", help="verify only; exit 1 on drift")
    p.add_argument("--root", type=Path, default=REPO_ROOT,
                   help="repo root to act on (default: this checkout)")
    args = p.parse_args(argv)
    return run(args.root.resolve(), check=args.check)


if __name__ == "__main__":
    sys.exit(main())
