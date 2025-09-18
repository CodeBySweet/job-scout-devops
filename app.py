# app.py
import os
import argparse
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from urllib.parse import urlparse

import feedparser
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import uvicorn

DEFAULT_KEYWORDS = [
    "devops",
    "cloud engineer",
    "site reliability",
    "sre",
    "platform engineer",
    "infrastructure",
]

def parse_env_list(value: str) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]

def load_feeds_from_file(path: str) -> List[str]:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

def get_config():
    feed_urls_env = os.getenv("FEED_URLS", "")
    feeds_file = os.getenv("FEEDS_FILE", "feeds.example.txt")
    keywords_env = os.getenv("KEYWORDS", ",".join(DEFAULT_KEYWORDS))
    exclude_env = os.getenv("EXCLUDE_KEYWORDS", "")
    hours_env = int(os.getenv("HOURS", "24"))

    feeds = parse_env_list(feed_urls_env)
    if not feeds:
        feeds = load_feeds_from_file(feeds_file)

    return {
        "feeds": feeds,
        "keywords": [k.lower() for k in parse_env_list(keywords_env)],
        "exclude": [k.lower() for k in parse_env_list(exclude_env)],
        "hours": hours_env,
    }

def within_hours(published_parsed, hours: int) -> bool:
    if not published_parsed:
        return False
    published_dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
    return published_dt >= (datetime.now(timezone.utc) - timedelta(hours=hours))

def match_keywords(text: str, keywords: List[str]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords) if keywords else True

def match_exclusions(text: str, exclude: List[str]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in exclude) if exclude else False

def normalize_entry(entry) -> Dict[str, Any]:
    published = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
        published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc).isoformat()

    return {
        "title": getattr(entry, "title", ""),
        "link": getattr(entry, "link", ""),
        "summary": getattr(entry, "summary", ""),
        "published": published,
        "source": urlparse(getattr(entry, "link", "")).netloc or "",
    }

def fetch_jobs(feeds: List[str], keywords: List[str], exclude: List[str], hours: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
            for e in parsed.entries:
                text = " ".join([
                    getattr(e, "title", ""),
                    getattr(e, "summary", ""),
                    getattr(e, "description", ""),
                ])
                published_parsed = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)

                if not within_hours(published_parsed, hours):
                    continue
                if not match_keywords(text, keywords):
                    continue
                if match_exclusions(text, exclude):
                    continue

                results.append(normalize_entry(e))
        except Exception as ex:
            results.append({"error": f"Failed to parse {url}: {ex}"})
    # de-dupe by link/title
    seen = set()
    deduped = []
    for r in results:
        key = (r.get("link"), r.get("title"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    # sort newest first
    deduped.sort(key=lambda r: r.get("published") or "", reverse=True)
    return deduped

# ---------- FastAPI ----------
app = FastAPI(title="Job Scout (DevOps/Cloud) - 24h")

@app.get("/jobs")
def jobs(
    hours: int = Query(default=None, description="Look-back window in hours"),
    keywords: str = Query(default=None, description="Comma-separated keyword filter"),
    exclude: str = Query(default=None, description="Comma-separated exclude terms"),
):
    cfg = get_config()
    hrs = hours if hours is not None else cfg["hours"]
    ks = [k.strip().lower() for k in keywords.split(",")] if keywords else cfg["keywords"]
    ex = [k.strip().lower() for k in exclude.split(",")] if exclude else cfg["exclude"]

    if not cfg["feeds"]:
        return JSONResponse(
            status_code=400,
            content={"error": "No feeds configured. Set FEED_URLS or provide feeds.example.txt."},
        )

    items = fetch_jobs(cfg["feeds"], ks, ex, hrs)
    return {"count": len(items), "hours": hrs, "keywords": ks, "exclude": ex, "items": items}

# ---------- CLI (one-off run) ----------
def main():
    parser = argparse.ArgumentParser(description="Fetch DevOps/Cloud jobs from feeds")
    parser.add_argument("--once", action="store_true", help="Run once in CLI and print results")
    args = parser.parse_args()

    if args.once:
        cfg = get_config()
        if not cfg["feeds"]:
            print("No feeds configured. Set FEED_URLS or provide feeds.example.txt")
            return
        items = fetch_jobs(cfg["feeds"], cfg["keywords"], cfg["exclude"], cfg["hours"])
        print(f"Found {len(items)} postings in last {cfg['hours']}h matching {cfg['keywords']}")
        for it in items[:25]:
            print(f"- {it['title']}  [{it['source']}]")
            print(f"  {it['link']}")
            if it['published']:
                print(f"  published: {it['published']}")
        return

    # run API if no --once
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

if __name__ == "__main__":
    main()
