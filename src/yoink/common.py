import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


def clean_html(
    html_to_clean: str,
    tags_to_remove: list[str] = ["style", "svg", "script"],
    attributes_to_keep: list[str] = ["id", "href"],
) -> str:
    """Clean HTML by removing specified tags and stripping non-essential attributes.

    Useful for reducing HTML size before passing to an LLM or diff tool.

    Args:
        html_to_clean: Raw HTML string.
        tags_to_remove: Tags whose content will be fully removed. Defaults to style, svg, script.
        attributes_to_keep: Attributes to preserve on all tags. All others are stripped.

    Returns:
        Cleaned HTML string.
    """
    for tag in tags_to_remove:
        html_to_clean = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html_to_clean, flags=re.DOTALL)

    kept = "|".join(attributes_to_keep)
    pattern = rf'\b(?!({kept})\b)\w+(?:-\w+)?\s*=\s*["\'][^"\']*["\']'
    return re.sub(pattern, "", html_to_clean)


def is_valid_url(url: str) -> bool:
    """Return True if url is a well-formed http/https/ftp URL."""
    regex = re.compile(
        r"^(?:http|ftp)s?://"
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"
        r"localhost|"
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"\[?[A-F0-9]*:[A-F0-9:]+\]?)"
        r"(?::\d+)?"
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return re.match(regex, url) is not None


def is_valid_html(html: str) -> bool:
    """Return True if html can be parsed by BeautifulSoup."""
    try:
        BeautifulSoup(html, "html.parser")
        return True
    except Exception:
        return False


def load_urls_from_txt(path: Path) -> list[str]:
    """Load one URL per line from a plain text file, skipping blank lines."""
    with path.open("r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


def load_urls_from_json(path: Path) -> list[str]:
    """Load URLs from a JSON file.

    Accepts either a top-level list or an object with a ``urls`` key.

    Raises:
        ValueError: If the JSON structure is not supported.
    """
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict) and "urls" in data and isinstance(data["urls"], list):
        return [str(x) for x in data["urls"]]
    raise ValueError(f"Unsupported JSON format in {path}: expected a list or {{\"urls\": [...]}}")
