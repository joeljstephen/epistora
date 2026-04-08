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
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(api_url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            tweet = data.get("tweet") or data.get("status") or data
            if not tweet.get("text"):
                return None
            return _normalize_fxtwitter(tweet)
    except Exception as exc:
        logger.debug("fxtwitter failed: %s", exc)
        return None


async def fetch_via_vxtwitter(url: str, *, timeout: int = 20) -> dict | None:
    """Use the vxtwitter API (api.vxtwitter.com) to fetch post data."""
    api_url = _rewrite_url(url, "api.vxtwitter.com")
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
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
            follow_redirects=True, timeout=timeout,
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
    if isinstance(article, dict):
        article_text = article.get("text") or article.get("body") or ""

    return {
        "text": text,
        "article_text": article_text,
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
    return {
        "text": data.get("text", ""),
        "article_text": "",
        "author_name": data.get("user_name", ""),
        "username": data.get("user_screen_name", ""),
        "created_at": data.get("date", ""),
        "likes": data.get("likes", 0),
        "retweets": data.get("retweets", 0),
        "replies": data.get("replies", 0),
        "source": "vxtwitter",
        "is_thread": False,
        "has_article": False,
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
