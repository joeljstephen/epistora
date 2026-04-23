"""Free mirror/embed fallback helpers for X/Twitter extraction.

Supports fxtwitter, vxtwitter, oEmbed, and page/OG scraping.
"""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _rewrite_url(original_url: str, mirror_host: str) -> str:
    """Replace x.com or twitter.com host with a mirror host."""
    return re.sub(
        r"https?://(www\.)?(twitter\.com|x\.com)",
        f"https://{mirror_host}",
        original_url,
    )


async def fetch_via_fxtwitter(url: str, *, timeout: int = 20) -> dict | None:
    """Use the fxtwitter API (api.fxtwitter.com) to fetch post data."""
    api_url = _rewrite_url(url, "api.fxtwitter.com")
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": "Epistora/1.0"}
        ) as client:
            resp = await client.get(api_url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            tweet = data.get("tweet") or data.get("status") or data
            has_article = bool(tweet.get("article") or tweet.get("twitter_card", {}).get("article"))
            if not tweet.get("text") and not has_article:
                return None
            return _normalize_fxtwitter(tweet)
    except Exception as exc:
        logger.debug("fxtwitter failed: %s", exc)
        return None


async def fetch_via_vxtwitter(url: str, *, timeout: int = 20) -> dict | None:
    """Use the vxtwitter API (api.vxtwitter.com) to fetch post data."""
    api_url = _rewrite_url(url, "api.vxtwitter.com")
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": "Epistora/1.0"}
        ) as client:
            resp = await client.get(api_url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data.get("text"):
                return None
            return _normalize_vxtwitter(data)
    except Exception as exc:
        logger.debug("vxtwitter failed: %s", exc)
        return None


async def fetch_via_oembed(url: str, *, timeout: int = 15) -> dict | None:
    """Fetch oEmbed HTML for an X/Twitter URL. Falls back to noembed."""
    for endpoint in [
        "https://publish.twitter.com/oembed",
        "https://noembed.com/embed",
    ]:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(endpoint, params={"url": url})
                if resp.status_code != 200:
                    continue
                data = resp.json()
                html = data.get("html", "")
                text = _extract_text_from_oembed_html(html)
                if text:
                    return {
                        "text": text,
                        "author_name": data.get("author_name", ""),
                        "author_url": data.get("author_url", ""),
                        "source": endpoint.split("/")[2],
                    }
        except Exception as exc:
            logger.debug("oEmbed via %s failed: %s", endpoint, exc)
            continue
    return None


async def fetch_via_page_scrape(url: str, *, timeout: int = 20) -> dict | None:
    """Direct page fetch for OG metadata and visible text."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; bot)"},
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            html = resp.text
    except Exception as exc:
        logger.debug("Page scrape failed: %s", exc)
        return None

    soup = BeautifulSoup(html, "html.parser")
    result: dict = {}

    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        result["text"] = og_desc["content"]

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        result["title"] = og_title["content"]

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not result.get("text") and meta_desc and meta_desc.get("content"):
        result["text"] = meta_desc["content"]

    if result.get("text"):
        result["source"] = "page_scrape"
        return result

    return None


def _render_article_blocks(article: dict) -> str:
    """Convert fxtwitter Draft.js-style article content to markdown text."""
    content = article.get("content")
    if not isinstance(content, dict):
        return article.get("text") or article.get("body") or article.get("preview_text") or ""

    blocks = content.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return article.get("preview_text") or ""

    entity_map = content.get("entityMap") or {}
    if isinstance(entity_map, list):
        entity_map = {
            str(e.get("key", "")): e.get("value", {}) for e in entity_map if isinstance(e, dict)
        }
    parts: list[str] = []

    for block in blocks:
        block_text = block.get("text", "")
        if not block_text:
            if block.get("type") != "unstyled":
                continue
            parts.append("")
            continue

        inline_styles: list[dict] = sorted(
            block.get("inlineStyleRanges", []),
            key=lambda s: s.get("offset", 0),
        )
        entity_ranges: list[dict] = sorted(
            block.get("entityRanges", []),
            key=lambda e: e.get("offset", 0),
        )

        if inline_styles or entity_ranges:
            block_text = _apply_inline_formatting(
                block_text, inline_styles, entity_ranges, entity_map
            )

        block_type = block.get("type", "unstyled")
        data = block.get("data") or {}

        if block_type == "header-two":
            parts.append(f"## {block_text}")
        elif block_type == "header-three":
            parts.append(f"### {block_text}")
        elif block_type == "blockquote":
            parts.append(f"> {block_text}")
        elif block_type == "code-block":
            parts.append(f"```\n{block_text}\n```")
        elif block_type == "unordered-list-item":
            parts.append(f"- {block_text}")
        elif block_type == "ordered-list-item":
            parts.append(f"1. {block_text}")
        else:
            mentions = data.get("mentions")
            urls = data.get("urls")
            if mentions or urls:
                parts.append(_apply_data_entities(block_text, data))
            else:
                parts.append(block_text)

    return "\n\n".join(parts)


def _apply_inline_formatting(
    text: str,
    styles: list[dict],
    entity_ranges: list[dict],
    entity_map: dict,
) -> str:
    """Apply Draft.js inline styles (bold, italic) and entity links to text."""
    ops: list[tuple[int, int, str, str]] = []
    for s in styles:
        style = s.get("style", "")
        if style == "Bold":
            ops.append((s["offset"], s["offset"] + s["length"], "**", "**"))
        elif style == "Italic":
            ops.append((s["offset"], s["offset"] + s["length"], "*", "*"))
        elif style == "Strikethrough":
            ops.append((s["offset"], s["offset"] + s["length"], "~~", "~~"))

    for e in entity_ranges:
        key = str(e.get("key", ""))
        entity = entity_map.get(key, {})
        entity_type = entity.get("type", "")
        url = ""
        data = entity.get("data", {})
        if entity_type == "LINK":
            url = data.get("url") or data.get("href", "")
        if url:
            ops.append((e["offset"], e["offset"] + e["length"], "[", f"]({url})"))

    ops.sort(key=lambda o: o[0])
    result = []
    last = 0
    for start, end, prefix, suffix in ops:
        if start < last:
            start = last
        if end <= start:
            continue
        result.append(text[last:start])
        result.append(prefix)
        result.append(text[start:end])
        result.append(suffix)
        last = end
    result.append(text[last:])
    return "".join(result)


def _apply_data_entities(text: str, data: dict) -> str:
    """Replace entity spans (mentions, urls, hashtags) in block data."""
    result = text
    for key in ("urls", "mentions", "hashtags", "cashtags"):
        entities = data.get(key)
        if not isinstance(entities, list):
            continue
        for entity in reversed(entities):
            if not isinstance(entity, dict):
                continue
            from_idx = entity.get("fromIndex", 0)
            to_idx = entity.get("toIndex", len(text))
            entity_text = entity.get("text", "")
            url = entity.get("url", "")
            if url and entity_text:
                result = result[:from_idx] + f"[{entity_text}]({url})" + result[to_idx:]
    return result


def _normalize_fxtwitter(tweet: dict) -> dict:
    """Normalize fxtwitter API response into a common shape."""
    author = tweet.get("author") or {}
    text = tweet.get("text", "")

    thread_tweets = tweet.get("thread", [])
    if thread_tweets:
        all_texts = [text] + [t.get("text", "") for t in thread_tweets if t.get("text")]
        text = "\n\n".join(all_texts)

    article = tweet.get("article") or tweet.get("twitter_card", {}).get("article")
    article_text = ""
    article_title = ""
    if isinstance(article, dict):
        article_title = article.get("title", "")
        article_text = _render_article_blocks(article)

    return {
        "text": text,
        "article_text": article_text,
        "article_title": article_title,
        "author_name": author.get("name", ""),
        "username": author.get("screen_name") or author.get("username", ""),
        "created_at": tweet.get("created_at", ""),
        "likes": tweet.get("likes", 0),
        "retweets": tweet.get("retweets", 0),
        "replies": tweet.get("replies", 0),
        "source": "fxtwitter",
        "is_thread": bool(thread_tweets),
        "has_article": bool(article_text),
    }


def _normalize_vxtwitter(data: dict) -> dict:
    """Normalize vxtwitter API response into a common shape."""
    article = data.get("article")
    article_text = ""
    article_title = ""
    if isinstance(article, dict):
        article_title = article.get("title", "")
        preview = article.get("preview_text", "")
        if preview:
            article_text = preview

    return {
        "text": data.get("text", ""),
        "article_text": article_text,
        "article_title": article_title,
        "author_name": data.get("user_name", ""),
        "username": data.get("user_screen_name", ""),
        "created_at": data.get("date", ""),
        "likes": data.get("likes", 0),
        "retweets": data.get("retweets", 0),
        "replies": data.get("replies", 0),
        "source": "vxtwitter",
        "is_thread": False,
        "has_article": bool(article_text),
    }


def _extract_text_from_oembed_html(html: str) -> str:
    """Strip HTML from oEmbed response to get plain tweet text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    blockquote = soup.find("blockquote")
    if blockquote:
        for a in blockquote.find_all("a"):
            a.decompose()
        return blockquote.get_text(separator="\n").strip()
    return ""
