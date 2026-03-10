import httpx
import os

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

PRIORITY_EMOJI = {
    "CRITIQUE": "🔴",
    "IMPORTANT": "🟡",
    "BONUS": "🟢",
}

def send_report(article: dict, report: dict, report_url: str):
    """Send a Discover report summary to Discord."""
    if not WEBHOOK_URL:
        return

    score_before = report.get("score_before", 0)
    score_after = report.get("score_after", 0)
    verdict = report.get("verdict", "")
    fixes = report.get("priority_fixes", [])
    titles = report.get("og_title_rewrites", [])

    # Score bar
    def score_bar(score):
        filled = round(score / 10)
        return "█" * filled + "░" * (10 - filled)

    # Top 3 critical fixes
    critical = [f for f in fixes if f.get("priority") == "CRITIQUE"][:3]
    fixes_text = ""
    for fix in critical:
        emoji = PRIORITY_EMOJI.get(fix["priority"], "⚪")
        fixes_text += f"{emoji} **{fix['category']}** — {fix['action']}\n"

    # Trend info
    trend = report.get("trend_alignment", {})
    timely = "✅ Timely" if trend.get("is_timely") else "⏳ Evergreen"
    freshness = trend.get("freshness_window", "?")

    # Best title rewrite
    best_title = titles[0] if titles else "(voir rapport)"

    embed = {
        "embeds": [{
            "title": f"📊 Nouveau rapport Discover — {article['title'][:60]}{'...' if len(article['title']) > 60 else ''}",
            "url": report_url,
            "color": 0x5865F2,
            "fields": [
                {
                    "name": "📈 Score Discover",
                    "value": f"Avant: `{score_before}/100` {score_bar(score_before)}\nAprès: `{score_after}/100` {score_bar(score_after)} (+{score_after - score_before}pts)",
                    "inline": False
                },
                {
                    "name": "💡 Verdict",
                    "value": verdict or "—",
                    "inline": False
                },
                {
                    "name": "🚨 Corrections critiques",
                    "value": fixes_text or "Aucune correction critique.",
                    "inline": False
                },
                {
                    "name": "✍️ Meilleur og:title proposé",
                    "value": f"`{best_title}`",
                    "inline": False
                },
                {
                    "name": "⏱️ Tendance",
                    "value": f"{timely} · Durée estimée: {freshness}",
                    "inline": True
                },
                {
                    "name": "👤 Auteur",
                    "value": article.get("author", "?"),
                    "inline": True
                },
            ],
            "footer": {
                "text": "Journal du Geek · Discover Optimizer"
            },
            "timestamp": article.get("published_at", "")[:19] if article.get("published_at") else None,
        }],
        "components": [{
            "type": 1,
            "components": [{
                "type": 2,
                "style": 5,
                "label": "Voir le rapport complet →",
                "url": report_url
            }]
        }]
    }

    try:
        httpx.post(WEBHOOK_URL, json=embed, timeout=10)
    except Exception as e:
        print(f"[Discord] Erreur envoi webhook: {e}")
