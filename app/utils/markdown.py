from __future__ import annotations

import re
from pathlib import Path

import frontmatter


def build_frontmatter_doc(metadata: dict, body: str) -> str:
    post = frontmatter.Post(body, **metadata)
    return frontmatter.dumps(post) + "\n"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    post = frontmatter.loads(text)
    return dict(post.metadata), post.content


def parse_markdown_file(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    post = frontmatter.load(str(path))
    return dict(post.metadata), post.content


def extract_wikilinks(text: str) -> list[str]:
    return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text)


def wikilink(name: str) -> str:
    return f"[[{name}]]"


def path_wikilink(path: str, label: str | None = None) -> str:
    normalized = path.replace("\\", "/")
    if normalized.endswith(".md"):
        normalized = normalized[:-3]
    if label:
        return f"[[{normalized}|{label}]]"
    return f"[[{normalized}]]"
