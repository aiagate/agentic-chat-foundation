"""Test helpers for the built-in agent profile bundle."""

from __future__ import annotations

from pathlib import Path


def copy_agent_profile_bundle(target_root: Path) -> None:
    """Copy the checked-in agent profile bundle into a temporary memory root."""

    source_root = Path(__file__).resolve().parents[1] / "memory" / "profiles" / "agent"
    target_dir = target_root / "profiles" / "agent"
    target_dir.mkdir(parents=True, exist_ok=True)
    for part in ("AGENTS", "SOUL", "PERSONAL", "MEMORY"):
        source_path = source_root / f"{part}.md"
        target_path = target_dir / f"{part}.md"
        target_path.write_text(
            source_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
