import httpx
import feedparser
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

RSS_URL = os.getenv("RSS_URL", "https://www.journaldugeek.com/feed/")
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")

def _scraper_url(target: str) -> str:
    """Wrappe une URL via ScraperAPI pour bypasser Cloudflare."""
    if SCRAPER_API_KEY:
        return f"https://api.scraperapi.com/?api_key={SCRAPER_API_KEY}&url={target}"
    return target

def fetch_rss_items() -> list[dict]:
    """Fetch et parse le flux RSS via ScraperAPI pour bypasser Cloudflare."""
    try:
        resp = httpx.get(_scraper_url(RSS_URL), timeout=30)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        print(f"[RSS] Feed fetché: {len(feed.entries)} entrées")
    except Exception as e:
        print(f"[RSS] Erreur fetch feed: {e}")
        return []

    if not feed.entries:
        return []
    items = []
    for entry in feed.entries:
        categories = [t.term for t in entry.get("tags", [])]
        items.append({
            "guid": entry.get("id", entry.get("link", "")),
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "author": entry.get("author", ""),
            "published_at": entry.get("published", ""),
            "categories": ", ".join(categories),
            "description": _strip_html(entry.get("summary", "")),
        })
    return items


def _parse_rss2json(data: dict) -> list[dict]:
    """Parse rss2json API response into item dicts."""
    items = []
    for item in data.get("items", []):
        categories = item.get("categories", [])
        if isinstance(categories, str):
            categories = [categories]
        items.append({
            "guid": item.get("guid", item.get("link", "")),
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "author": item.get("author", ""),
            "published_at": item.get("pubDate", ""),
            "categories": ", ".join(categories),
            "description": _strip_html(item.get("description", "")),
        })
    return items


def fetch_article_content(url: str) -> dict:
    """Fetch full article page and extract content + og:image."""
    try:
        resp = httpx.get(_scraper_url(url), timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # og:image
        og_image = ""
        og_img_tag = soup.find("meta", property="og:image")
        if og_img_tag:
            og_image = og_img_tag.get("content", "")

        # og:title (may differ from RSS title)
        og_title = ""
        og_title_tag = soup.find("meta", property="og:title")
        if og_title_tag:
            og_title = og_title_tag.get("content", "")

        # og:description
        og_desc = ""
        og_desc_tag = soup.find("meta", property="og:description")
        if og_desc_tag:
            og_desc = og_desc_tag.get("content", "")

        # robots meta (check max-image-preview)
        robots_tag = soup.find("meta", attrs={"name": "robots"})
        robots_content = robots_tag.get("content", "") if robots_tag else ""

        # Extract main article text
        article_text = ""
        for selector in ["article", ".entry-content", ".post-content", ".article-content", "main"]:
            el = soup.select_one(selector)
            if el:
                article_text = el.get_text(separator="\n", strip=True)[:8000]
                break
        if not article_text:
            article_text = soup.get_text(separator="\n", strip=True)[:8000]

        # Image dimensions hint (check img tags in article)
        main_img_width = 0
        if og_image:
            img_tag = soup.find("img", src=lambda s: s and og_image.split("/")[-1] in s)
            if img_tag:
                try:
                    main_img_width = int(img_tag.get("width", 0))
                except (ValueError, TypeError):
                    pass

        return {
            "full_content": article_text,
            "og_image": og_image,
            "og_title": og_title,
            "og_description": og_desc,
            "robots_meta": robots_content,
            "main_img_width": main_img_width,
        }

    except Exception as e:
        return {
            "full_content": "",
            "og_image": "",
            "og_title": "",
            "og_description": "",
            "robots_meta": "",
            "main_img_width": 0,
            "error": str(e),
        }


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)[:500]
