# Discover Optimizer — Journal du Geek

Outil interne d'optimisation Google Discover pour les articles du Journal du Geek.
Analyse chaque article via Claude AI et génère un rapport actionnable avec scores, corrections prioritaires, et propositions de balises prêtes à copier.

---

## Fonctionnalités

- **Analyse par URL** — colle l'URL d'un article publié, l'outil fetche le contenu via ScraperAPI (bypass Cloudflare) et génère un rapport complet
- **Analyse de brouillon** — colle le texte d'un article non encore publié pour obtenir des recommandations avant publication
- **Rapport Discover** — score avant/après, verdict, corrections CRITIQUE / IMPORTANT / BONUS, quick wins
- **Propositions de balises** — `<title>`, `og:title`, `og:description`, alt text image, nom de fichier SEO
- **Bloc meta complet** — snippet HTML prêt à coller dans le `<head>`, bouton "Tout copier"
- **Re-analyse** — après avoir appliqué les corrections, relance l'analyse pour mesurer l'impact
- **Dashboard** — historique des 50 derniers rapports avec scores, verdicts et badges critiques
- **Notifications Discord** — webhook envoyé après chaque analyse

---

## Stack technique

| Composant | Technologie |
|---|---|
| Backend | Python 3.12 · FastAPI · Uvicorn |
| IA | Claude Sonnet (`claude-sonnet-4-6`) via Anthropic API |
| Base de données | SQLite (fichier local / volume Railway) |
| Fetch articles | ScraperAPI + BeautifulSoup4 |
| Templates | Jinja2 |
| Déploiement | Railway (Docker) · GitHub Actions auto-deploy |

---

## Architecture

```
discover/
├── main.py              # Routes FastAPI (/, /analyze, /analyze-draft, /reanalyze, /report, /api/stats)
├── analyzer.py          # Prompts Claude + fonctions analyze_article() / analyze_draft()
├── fetcher.py           # Fetch RSS + contenu article via ScraperAPI
├── database.py          # Init SQLite, schema, get_conn()
├── discord_notify.py    # Envoi rapport vers webhook Discord
├── templates/
│   ├── index.html       # Dashboard + formulaires (URL et brouillon)
│   └── report.html      # Page rapport complète
├── static/
│   └── style.css        # Thème sombre · couleurs JDG (#7b2282)
├── Dockerfile
└── railway.toml
```

---

## Variables d'environnement

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Clé API Anthropic (Claude) |
| `SCRAPER_API_KEY` | Clé ScraperAPI pour bypasser Cloudflare |
| `DISCORD_WEBHOOK_URL` | URL du webhook Discord pour les notifications |
| `DB_PATH` | Chemin SQLite (défaut : `discover.db`, Railway : `/data/discover.db`) |
| `BASE_URL` | URL publique de l'app (ex: `https://mon-app.railway.app`) |
| `PORT` | Port d'écoute (défaut : `8000`) |

Crée un fichier `.env` à la racine pour le développement local :

```env
ANTHROPIC_API_KEY=sk-ant-...
SCRAPER_API_KEY=...
DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/...
DB_PATH=discover.db
BASE_URL=http://localhost:8000
PORT=8000
```

---

## Installation locale

```bash
# Cloner le dépôt
git clone https://github.com/lapuj77/discover-optimizer.git
cd discover-optimizer

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env  # puis éditer .env

# Lancer le serveur
python main.py
# ou
uvicorn main:app --reload --port 8000
```

L'interface est accessible sur [http://localhost:8000](http://localhost:8000).

---

## Utilisation

### Analyser un article publié

1. Colle l'URL d'un article JDG dans le champ **"🔗 URL existante"**
2. Clique sur **Analyser →**
3. L'outil fetche le contenu via ScraperAPI (~8s) puis envoie à Claude (~20s)
4. Le rapport s'affiche avec score avant/après, corrections et balises optimisées

### Analyser un brouillon

1. Clique sur l'onglet **"✍️ Article brouillon"**
2. Renseigne le titre et colle le contenu de l'article
3. Les métadonnées (og:title, og:description, catégories) sont optionnelles
4. Le rapport recommande tout ce qui doit être créé avant publication

### Re-analyser après corrections

Sur la page d'un rapport, clique sur **↻ Re-analyser l'article** après avoir appliqué les corrections — le rapport est mis à jour avec les nouveaux scores.

---

## Format du rapport

```json
{
  "score_before": 42,
  "score_after": 78,
  "verdict": "...",
  "priority_fixes": [{ "priority": "CRITIQUE|IMPORTANT|BONUS", "category": "...", "problem": "...", "action": "...", "example": "..." }],
  "meta_title_rewrites": ["...", "...", "..."],
  "og_title_rewrites": ["...", "...", "..."],
  "og_description_rewrite": "...",
  "image_seo": { "alt_texts": ["...", "...", "..."], "filenames": ["...", "...", "..."] },
  "image_status": { "has_image": true, "max_image_preview_detected": true, "estimated_width_ok": true, "recommendation": "..." },
  "entity_analysis": { "entities_found": ["..."], "entities_missing": ["..."], "knowledge_graph_strength": "fort|moyen|faible" },
  "trend_alignment": { "is_timely": true, "trend_context": "...", "freshness_window": "..." },
  "quick_wins": ["...", "...", "..."]
}
```

---

## Coût estimé

| Opération | Coût approximatif |
|---|---|
| Analyse d'un article (ScraperAPI + Claude Sonnet) | ~0,04 € |
| Re-analyse | ~0,04 € |
| Analyse brouillon (Claude seul, pas de fetch) | ~0,02 € |

---

## Déploiement Railway

Le projet se déploie automatiquement via GitHub Actions à chaque push sur `master`.

- Builder : **Dockerfile**
- Restart policy : `ON_FAILURE`
- Volume persistant monté sur `/data` pour la base SQLite
- Variables d'environnement à configurer dans le dashboard Railway
