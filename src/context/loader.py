from pathlib import Path


def load(folder: str | Path) -> str:
    """Read all markdown files in the context folder and return combined text."""
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"Context folder not found: {folder}")
    parts = []
    for f in sorted(folder.glob("*.md")):
        parts.append(f"## {f.stem}\n\n{f.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)
