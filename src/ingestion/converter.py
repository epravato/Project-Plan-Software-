from pathlib import Path
from markitdown import MarkItDown

_md = MarkItDown()

SUPPORTED = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".png", ".jpg", ".jpeg"}


def convert(path: str | Path) -> str:
    """Convert a document to markdown text. Returns the markdown string."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {p.suffix}")
    result = _md.convert(str(p))
    return result.text_content


def convert_many(paths: list[str | Path]) -> dict[str, str]:
    """Convert multiple documents. Returns {filename: markdown} dict."""
    return {Path(p).name: convert(p) for p in paths}
