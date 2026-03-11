import os
import json
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from database import init_db, get_conn
from fetcher import fetch_article_content
from analyzer import analyze_article
from discord_notify import send_report

BASE_URL = os.getenv("BASE_URL", f"http://localhost:{os.getenv('PORT', '8000')}")


# ─── Startup / Shutdown ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Discover Optimizer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


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
async def analyze_url(request: Request, url: str = Form(...), content: str = Form(default="")):
    """Analyse manuelle d'une URL."""
    # Vérifie si déjà analysé
    with get_conn() as conn:
        existing = conn.execute("SELECT r.id FROM reports r JOIN articles a ON a.id = r.article_id WHERE a.link = ?", (url,)).fetchone()
        if existing:
            return RedirectResponse(f"/report/{existing['id']}", status_code=303)

    # Fetch complet via ScraperAPI (og:image, og:title, contenu, meta robots...)
    page_data = await asyncio.to_thread(fetch_article_content, url)

    # Fallback : contenu collé manuellement si le fetch a échoué
    if not page_data.get("full_content") and content.strip():
        page_data["full_content"] = content.strip()

    if not page_data.get("full_content"):
        return templates.TemplateResponse("index.html", {
            "request": request,
            "articles": [],
            "error": "Impossible de récupérer le contenu. Utilise le bouton '+ Coller le contenu' comme solution de secours.",
            "prefill_url": url,
        }, status_code=422)

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


@app.post("/reanalyze/{report_id}")
async def reanalyze(report_id: int):
    """Refetch l'article et met à jour le rapport existant (synchrone)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT a.id, a.link FROM reports r JOIN articles a ON a.id = r.article_id WHERE r.id = ?",
            (report_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Rapport introuvable")

    article_id, url = row["id"], row["link"]

    page_data = await asyncio.to_thread(fetch_article_content, url)
    if not page_data.get("full_content"):
        raise HTTPException(status_code=422, detail="Impossible de récupérer le contenu de l'article.")

    with get_conn() as conn:
        article = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    item = dict(article)
    item.update(page_data)

    report_data = await asyncio.to_thread(analyze_article, item)

    with get_conn() as conn:
        conn.execute("""
            UPDATE reports SET score_before=?, score_after=?, report_json=?, created_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (
            report_data.get("score_before", 0),
            report_data.get("score_after", 0),
            json.dumps(report_data, ensure_ascii=False),
            report_id,
        ))
        conn.execute("UPDATE articles SET full_content=?, og_image=? WHERE id=?",
                     (page_data.get("full_content", ""), page_data.get("og_image", ""), article_id))

    print(f"[Reanalyze] Rapport {report_id} mis à jour")
    return RedirectResponse(f"/report/{report_id}", status_code=303)

    # Met à jour le contenu de l'article en DB
    with get_conn() as conn:
        conn.execute("""
            UPDATE articles SET full_content=?, og_image=? WHERE id=?
        """, (page_data.get("full_content", ""), page_data.get("og_image", ""), article_id))



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
