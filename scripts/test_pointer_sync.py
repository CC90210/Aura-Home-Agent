"""Hermetic tests for scripts/pointer_sync.py.

Every test runs against a throwaway repo root in tmp_path with its own tiny
PERSONAL.md, so nothing here depends on the real seed, the real pointer files,
or the host's line-ending settings. Windows is production: assertions compare
LF-normalised text (read_text) and the byte-level idempotence check uses the
script's own writer.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # importlib mode: no auto sys.path

import pointer_sync as ps  # noqa: E402

CARD = (
    "\n## Operating card v0 (test)\n\n"
    "1. You are Aura — test seed.\n"
    "2. Never read `.env*`.\n"
)
SEED = (
    "---\nname: aura\n---\n\n# PERSONAL.md (test)\n\n"
    "<!-- LOCKSTEP:seed_core -->\nunrelated block\n<!-- /LOCKSTEP:seed_core -->\n\n"
    f"<!-- LOCKSTEP:operating_card -->{CARD}<!-- /LOCKSTEP:operating_card -->\n"
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "PERSONAL.md").write_text(SEED, encoding="utf-8")
    return tmp_path


def _all_pointers() -> list[str]:
    return [*ps.POINTER_FILES, *ps.STATIC_POINTERS]


# ---------------------------------------------------------------------------
# stamping
# ---------------------------------------------------------------------------

def test_stamp_creates_every_pointer_with_the_card(root: Path, capsys):
    assert ps.main(["--root", str(root)]) == 0
    out = capsys.readouterr().out
    for rel in _all_pointers():
        assert (root / rel).exists(), rel
        assert f"created: {rel}" in out
    for rel, header in ps.POINTER_FILES.items():
        text = (root / rel).read_text(encoding="utf-8")
        assert text.startswith(header), rel
        assert "Read AGENTS.md for the full contract." in text
        assert ps._blocks(text, rel)["operating_card"] == CARD, rel
        assert text.count("<!-- LOCKSTEP:operating_card -->") == 1
    assert (root / ".aider.conf.yml").read_text(encoding="utf-8") == ps.STATIC_POINTERS[".aider.conf.yml"]


def test_cursor_rule_has_always_apply_frontmatter(root: Path):
    ps.main(["--root", str(root)])
    text = (root / ".cursor/rules/aura-operating-card.mdc").read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert "alwaysApply: true" in head
    assert "description:" in head


def test_stamp_is_idempotent(root: Path):
    ps.main(["--root", str(root)])
    first = {rel: (root / rel).read_bytes() for rel in _all_pointers()}
    assert ps.main(["--root", str(root)]) == 0
    second = {rel: (root / rel).read_bytes() for rel in _all_pointers()}
    assert first == second


def test_stamp_writes_lf_only(root: Path):
    ps.main(["--root", str(root)])
    for rel in _all_pointers():
        assert b"\r" not in (root / rel).read_bytes(), rel


def test_seed_edit_propagates_and_narration_survives(root: Path):
    ps.main(["--root", str(root)])
    rel = ".github/copilot-instructions.md"
    path = root / rel
    hand = path.read_text(encoding="utf-8") + "\nA hand-written Copilot note under the footer.\n"
    path.write_text(hand, encoding="utf-8")
    new_card = CARD.replace("v0 (test)", "v1 (test)")
    (root / "PERSONAL.md").write_text(SEED.replace(CARD, new_card), encoding="utf-8")
    assert ps.main(["--root", str(root)]) == 0
    text = path.read_text(encoding="utf-8")
    assert ps._blocks(text, rel)["operating_card"] == new_card
    assert "A hand-written Copilot note under the footer." in text
    assert text.startswith(ps.POINTER_FILES[rel])


def test_existing_markerless_file_is_kept_and_card_appended(root: Path, capsys):
    rel = ".junie/guidelines.md"
    path = root / rel
    path.parent.mkdir(parents=True)
    path.write_text("# Someone's own Junie guidelines\n", encoding="utf-8")
    assert ps.main(["--root", str(root)]) == 0
    assert f"appended: {rel}" in capsys.readouterr().out
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Someone's own Junie guidelines\n")
    assert ps._blocks(text, rel)["operating_card"] == CARD


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------

def test_check_is_clean_after_stamp(root: Path, capsys):
    ps.main(["--root", str(root)])
    assert ps.main(["--root", str(root), "--check"]) == 0
    assert "pointer-sync check: CLEAN" in capsys.readouterr().out


def test_check_fails_before_any_stamp(root: Path, capsys):
    assert ps.main(["--root", str(root), "--check"]) == 1
    out = capsys.readouterr().out
    assert out.count("DRIFT") == len(_all_pointers())
    assert "pointer-sync check: CLEAN" not in out


def test_check_detects_block_drift_in_one_pointer(root: Path, capsys):
    ps.main(["--root", str(root)])
    rel = ".windsurf/rules/aura-operating-card.md"
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8").replace("Never read", "Feel free to read"),
                    encoding="utf-8")
    assert ps.main(["--root", str(root), "--check"]) == 1
    out = capsys.readouterr().out
    assert f"DRIFT {rel}: LOCKSTEP:operating_card differs" in out
    assert out.count("DRIFT") == 1
    assert "1 drift(s)" in out


def test_check_detects_missing_pointer_and_stamp_restores_it(root: Path, capsys):
    ps.main(["--root", str(root)])
    rel = ".roo/rules/aura-operating-card.md"
    (root / rel).unlink()
    assert ps.main(["--root", str(root), "--check"]) == 1
    assert f"DRIFT {rel}: pointer file missing" in capsys.readouterr().out
    assert ps.main(["--root", str(root)]) == 0
    assert ps.main(["--root", str(root), "--check"]) == 0


def test_check_detects_static_pointer_drift(root: Path, capsys):
    ps.main(["--root", str(root)])
    (root / ".aider.conf.yml").write_text("read:\n  - .env.agents\n", encoding="utf-8")
    assert ps.main(["--root", str(root), "--check"]) == 1
    assert "DRIFT .aider.conf.yml: differs" in capsys.readouterr().out


def test_check_never_writes(root: Path):
    ps.main(["--root", str(root), "--check"])
    assert not any((root / rel).exists() for rel in _all_pointers())


# ---------------------------------------------------------------------------
# failure modes + CLI surface
# ---------------------------------------------------------------------------

def test_seed_without_the_block_aborts(tmp_path: Path):
    (tmp_path / "PERSONAL.md").write_text("# no blocks here\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="defines no LOCKSTEP:operating_card"):
        ps.main(["--root", str(tmp_path)])


def test_missing_seed_aborts(tmp_path: Path):
    with pytest.raises(SystemExit, match="seed missing"):
        ps.main(["--root", str(tmp_path)])


def test_duplicate_markers_in_a_pointer_abort(root: Path):
    ps.main(["--root", str(root)])
    rel = ".clinerules/aura-operating-card.md"
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8") + "<!-- LOCKSTEP:operating_card -->\n",
                    encoding="utf-8")
    with pytest.raises(SystemExit, match="malformed LOCKSTEP markers"):
        ps.main(["--root", str(root), "--check"])


def test_help_is_clean():
    proc = subprocess.run(
        [sys.executable, str(Path(ps.__file__)), "--help"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert "--check" in proc.stdout and "--root" in proc.stdout
