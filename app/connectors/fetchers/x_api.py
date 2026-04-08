"""Official X/Twitter API v2 client for authenticated post/thread extraction."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.twitter.com/2"

_TWEET_FIELDS = (
    "created_at,author_id,conversation_id,text,"
    "public_metrics,referenced_tweets,note_tweet"
)
_USER_FIELDS = "name,username"
_EXPANSIONS = "author_id,referenced_tweets.id"


async def fetch_post_via_api(
    post_id: str,
    bearer_token: str,
    *,
    timeout: int = 30,
) -> dict | None:
    """Fetch a single post with full text and metadata. Returns normalized dict or None."""
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "ids": post_id,
        "tweet.fields": _TWEET_FIELDS,
        "user.fields": _USER_FIELDS,
        "expansions": _EXPANSIONS,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{_API_BASE}/tweets", headers=headers, params=params)
            if resp.status_code != 200:
                logger.warning("X API returned %d for post %s", resp.status_code, post_id)
                return None
            data = resp.json()
    except Exception as exc:
        logger.warning("X API request failed for %s: %s", post_id, exc)
        return None

    tweets = data.get("data", [])
    if not tweets:
        return None

    tweet = tweets[0]
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    author_info = users.get(tweet.get("author_id"), {})

    return _normalize_tweet(tweet, author_info)


async def fetch_thread_via_api(
    post_id: str,
    bearer_token: str,
    *,
    timeout: int = 30,
) -> list[dict] | None:
    """Reconstruct a thread using the conversation_id search endpoint.

    Returns a list of normalized tweet dicts in chronological order, or None on failure.
    """
    headers = {"Authorization": f"Bearer {bearer_token}"}

    root = await fetch_post_via_api(post_id, bearer_token, timeout=timeout)
    if not root:
        return None

    conversation_id = root.get("conversation_id")
    author_id = root.get("author_id")
    if not conversation_id or not author_id:
        return [root]

    search_params = {
        "query": f"conversation_id:{conversation_id} from:{root.get('username', '')}",
        "tweet.fields": _TWEET_FIELDS,
        "user.fields": _USER_FIELDS,
        "expansions": _EXPANSIONS,
        "max_results": "100",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{_API_BASE}/tweets/search/recent",
                headers=headers,
                params=search_params,
            )
            if resp.status_code != 200:
                logger.debug("Thread search returned %d; returning single post", resp.status_code)
                return [root]
            data = resp.json()
    except Exception as exc:
        logger.debug("Thread search failed: %s; returning single post", exc)
        return [root]

    tweets_data = data.get("data", [])
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

    thread = [_normalize_tweet(t, users.get(t.get("author_id"), {})) for t in tweets_data]
    thread.sort(key=lambda t: t.get("created_at", ""))

    if not any(t["id"] == root["id"] for t in thread):
        thread.insert(0, root)

    return thread


def _normalize_tweet(tweet: dict, author_info: dict) -> dict:
    text = tweet.get("note_tweet", {}).get("text") or tweet.get("text", "")
    metrics = tweet.get("public_metrics", {})

    return {
        "id": tweet.get("id", ""),
        "text": text,
        "author_id": tweet.get("author_id", ""),
        "author_name": author_info.get("name", ""),
        "username": author_info.get("username", ""),
        "created_at": tweet.get("created_at", ""),
        "conversation_id": tweet.get("conversation_id", ""),
        "metrics": {
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "replies": metrics.get("reply_count", 0),
        },
        "referenced_tweets": tweet.get("referenced_tweets", []),
    }


def assemble_thread_text(thread: list[dict]) -> str:
    """Join thread tweets into a single readable text block."""
    parts = []
    for i, t in enumerate(thread, 1):
        text = t.get("text", "")
        if len(thread) > 1:
            parts.append(f"[{i}/{len(thread)}] {text}")
        else:
            parts.append(text)
    return "\n\n".join(parts)
