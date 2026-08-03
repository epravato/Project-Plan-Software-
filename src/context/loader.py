from pathlib import Path


def is_reachable(folder: str | Path) -> bool:
    """Cheap existence check (same as opening the path in File Explorer) — used to
    warn in Settings when a configured company-drive folder can't currently be reached,
    e.g. off the H2M network/VPN or the drive isn't mapped on this machine."""
    try:
        return Path(folder).exists()
    except OSError:
        return False


def load(folder: str | Path) -> str:
    """Read all markdown files in the context folder and return combined text."""
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"Context folder not found: {folder}")
    parts = []
    for f in sorted(folder.glob("*.md")):
        parts.append(f"## {f.stem}\n\n{f.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)


def load_sources(sources: list[dict]) -> str:
    """Reads a list of {"label", "path"} context sources (e.g. company-drive folders)
    and combines them into one labeled block. Read fresh on every call so content stays
    current without a code change. Fails soft: an unreachable path is skipped, never
    raises — a missing network drive should never block a plan from generating."""
    parts = []
    for source in sources:
        label = source.get("label") or source.get("path", "")
        path = source.get("path")
        if not path:
            continue
        try:
            text = load(path)
        except Exception:
            continue
        if text.strip():
            parts.append(f"# {label}\n\n{text}")
    return "\n\n---\n\n".join(parts)
