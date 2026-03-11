import os
import json
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import init_db, get_conn
from fetcher import fetch_rss_items, fetch_article_content
from analyzer import analyze_article
from discord_notify import send_report

POLL_INTERVAL = 30
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{os.getenv('PORT', '8000')}")
PARIS_TZ = ZoneInfo("Europe/Paris")
QUIET_START = 22  # heure de début de la plage silencieuse
QUIET_END = 7     # heure de fin (exclusif)

scheduler = AsyncIOScheduler()


# ─── Startup / Shutdown ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(poll_rss, "interval", minutes=POLL_INTERVAL, id="rss_poll")
    scheduler.start()
    print(f"[Scheduler] Polling RSS toutes les {POLL_INTERVAL} min (silence 22h-7h heure de Paris)")
    # Run once immediately at startup (respecte aussi la plage silencieuse)
    asyncio.create_task(poll_rss())
    yield
    scheduler.shutdown()


app = FastAPI(title="Discover Optimizer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ─── RSS Polling & Processing ─────────────────────────────────────────────────

def _is_quiet_hours() -> bool:
    """Retourne True si on est dans la plage silencieuse (22h-7h heure de Paris)."""
    now = datetime.now(PARIS_TZ)
    h = now.hour
    return h >= QUIET_START or h < QUIET_END


async def poll_rss(force: bool = False):
    if not force and _is_quiet_hours():
        now = datetime.now(PARIS_TZ)
        print(f"[RSS] Plage silencieuse ({now.strftime('%H:%M')} heure de Paris) — scan ignoré")
        return
    print("[RSS] Polling en cours...")
    try:
        items = await asyncio.to_thread(fetch_rss_items)
    except Exception as e:
        print(f"[RSS] Erreur fetch RSS: {e}")
        return
    print(f"[RSS] {len(items)} articles dans le feed")
    new_count = 0

    for item in items:
        try:
            with get_conn() as conn:
                exists = conn.execute(
                    "SELECT id FROM articles WHERE guid = ?", (item["guid"],)
                ).fetchone()
                if exists:
                    continue

            # Fetch full content (hors transaction, dans un thread pour ne pas bloquer asyncio)
            page_data = await asyncio.to_thread(fetch_article_content, item["link"])
            item.update(page_data)

            # Save article
            with get_conn() as conn:
                cur = conn.execute("""
                    INSERT INTO articles (guid, title, link, author, published_at, categories, description, full_content, og_image)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["guid"], item["title"], item["link"], item["author"],
                    item["published_at"], item["categories"], item["description"],
                    item.get("full_content", ""), item.get("og_image", ""),
                ))
                article_id = cur.lastrowid
            print(f"[RSS] Nouvel article sauvé: {item['title'][:60]}")

            # Analyze with Claude (dans un thread)
            try:
                report_data = await asyncio.to_thread(analyze_article, item)
            except Exception as e:
                print(f"[Analyzer] Erreur: {e}")
                continue

            # Save report
            with get_conn() as conn:
                conn.execute("""
                    INSERT INTO reports (article_id, score_before, score_after, report_html, report_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    article_id,
                    report_data.get("score_before", 0),
                    report_data.get("score_after", 0),
                    "",
                    json.dumps(report_data, ensure_ascii=False),
                ))

            # Fetch the report id
            with get_conn() as conn:
                report_row = conn.execute(
                    "SELECT id FROM reports WHERE article_id = ?", (article_id,)
                ).fetchone()
            report_id = report_row["id"] if report_row else 0

        except Exception as e:
            print(f"[RSS] Erreur traitement article '{item.get('title','?')[:40]}': {e}")
            continue

            # Discord notification
            report_url = f"{BASE_URL}/report/{report_id}"
            try:
                send_report(item, report_data, report_url)
            except Exception as e:
                print(f"[Discord] Erreur: {e}")

            new_count += 1

    print(f"[RSS] {new_count} nouvel(s) article(s) traité(s)")


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                r.id as report_id,
                r.score_before,
                r.score_after,
                r.created_at,
                r.report_json,
                a.title,
                a.link,
                a.author,
                a.published_at,
                a.categories,
                a.og_image
            FROM reports r
            JOIN articles a ON a.id = r.article_id
            ORDER BY r.created_at DESC
            LIMIT 50
        """).fetchall()

    articles = []
    for row in rows:
        data = dict(row)
        report = json.loads(data["report_json"])
        data["verdict"] = report.get("verdict", "")
        data["critical_count"] = sum(
            1 for f in report.get("priority_fixes", []) if f.get("priority") == "CRITIQUE"
        )
        data["score_delta"] = data["score_after"] - data["score_before"]
        articles.append(data)

    return templates.TemplateResponse("index.html", {"request": request, "articles": articles})


@app.get("/report/{report_id}", response_class=HTMLResponse)
async def report_view(request: Request, report_id: int):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT r.*, a.title, a.link, a.author, a.published_at, a.categories, a.og_image
            FROM reports r JOIN articles a ON a.id = r.article_id
            WHERE r.id = ?
        """, (report_id,)).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Rapport introuvable")

    data = dict(row)
    report = json.loads(data["report_json"])
    return templates.TemplateResponse("report.html", {
        "request": request,
        "article": data,
        "report": report,
    })


@app.post("/analyze")
async def analyze_url(url: str = Form(...), content: str = Form(default="")):
    """Analyse manuelle d'une URL."""
    # Vérifie si déjà analysé
    with get_conn() as conn:
        existing = conn.execute("SELECT r.id FROM reports r JOIN articles a ON a.id = r.article_id WHERE a.link = ?", (url,)).fetchone()
        if existing:
            return RedirectResponse(f"/report/{existing['id']}", status_code=303)

    if not content.strip():
        return templates.TemplateResponse("index.html", {
            "request": request,
            "articles": [],
            "error": "Colle le contenu de l'article dans le champ texte (ouvre l'article, Ctrl+A, Ctrl+C, colle ici).",
            "prefill_url": url,
        }, status_code=422)

    # Tente le fetch pour récupérer og:image / og:title, ignore les erreurs
    page_data = await asyncio.to_thread(fetch_article_content, url)
    if not page_data.get("full_content"):
        page_data["full_content"] = content.strip()

    item = {
        "guid": url,
        "title": page_data.get("og_title") or url,
        "link": url,
        "author": "",
        "published_at": "",
        "categories": "",
        "description": page_data.get("og_description", ""),
        **page_data,
    }

    # Save article
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT OR IGNORE INTO articles (guid, title, link, author, published_at, categories, description, full_content, og_image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (item["guid"], item["title"], item["link"], item["author"],
              item["published_at"], item["categories"], item["description"],
              item.get("full_content", ""), item.get("og_image", "")))
        article_id = cur.lastrowid

    # Analyze (dans un thread)
    report_data = await asyncio.to_thread(analyze_article, item)

    # Save report
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO reports (article_id, score_before, score_after, report_html, report_json)
            VALUES (?, ?, ?, ?, ?)
        """, (article_id, report_data.get("score_before", 0), report_data.get("score_after", 0),
              "", json.dumps(report_data, ensure_ascii=False)))
        report_id = cur.lastrowid

    return RedirectResponse(f"/report/{report_id}", status_code=303)


@app.post("/trigger-poll")
async def trigger_poll(background_tasks: BackgroundTasks):
    """Manually trigger an RSS poll."""
    background_tasks.add_task(poll_rss, True)
    return {"status": "poll lancé"}


@app.get("/api/stats")
async def stats():
    with get_conn() as conn:
        total_articles = conn.execute("SELECT COUNT(*) as c FROM articles").fetchone()["c"]
        total_reports = conn.execute("SELECT COUNT(*) as c FROM reports").fetchone()["c"]
        avg_score_before = conn.execute("SELECT AVG(score_before) as a FROM reports").fetchone()["a"] or 0
        avg_score_after = conn.execute("SELECT AVG(score_after) as a FROM reports").fetchone()["a"] or 0
    return {
        "total_articles": total_articles,
        "total_reports": total_reports,
        "avg_score_before": round(avg_score_before, 1),
        "avg_score_after": round(avg_score_after, 1),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
