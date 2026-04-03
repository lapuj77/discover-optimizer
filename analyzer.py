import json
import anthropic
import os

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """Tu es un expert SEO spécialisé dans Google Discover, avec une connaissance approfondie de l'algorithme, du modèle pCTR, des signaux E-E-A-T, et des mécaniques de distribution.

Tu analyses des articles d'un média d'actualité tech et pop culture (Journal du Geek) et tu génères des rapports d'optimisation Discover actionnables, précis, et priorisés.

Réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans texte avant ou après."""

ANALYSIS_PROMPT = """Analyse cet article pour Google Discover et génère un rapport d'optimisation.

## DONNÉES DE L'ARTICLE

**Titre RSS/H1:** {title}
**og:title actuel:** {og_title}
**og:description actuelle:** {og_description}
**Auteur:** {author}
**Date de publication:** {published_at}
**Catégories/Tags:** {categories}
**URL:** {link}
**og:image URL:** {og_image}
**Meta robots (max-image-preview présent ?):** {robots_meta}
**Contenu de l'article (extrait):**
{full_content}

---

## CONNAISSANCES DISCOVER À APPLIQUER

**Signaux critiques à vérifier :**
1. Image 1200px+ 16:9 + meta `max-image-preview:large` obligatoire → jusqu'à +79% CTR
2. `og:title` : 50-80 caractères, spécifique, émotionnel, honnête, entité nommée + enjeu clair
3. `og:description` : accroche complémentaire au titre, renforce la curiosité sans spoiler
4. Entités Knowledge Graph clairement nommées (personnes, marques, produits, lieux)
5. Fraîcheur : le sujet colle-t-il à un trend actuel ? Y a-t-il un angle plus fort ?
6. E-E-A-T : auteur visible, expertise démontrée dans le contenu
7. Angle émotionnel : surprise, curiosité, polémique, urgence, exclusivité
8. Éviter le clickbait pur (pénalise le pCTR après le 1er cycle)
9. Image IA : génère 2 prompts prêts pour Midjourney/DALL-E — 1 photoréaliste, 1 illustratif/graphique — en anglais, détaillés (sujet, ambiance, éclairage, style)

---

## FORMAT DE RÉPONSE (JSON strict)

{{
  "score_before": <entier 0-100, score Discover actuel estimé>,
  "score_after": <entier 0-100, score estimé après tes optimisations>,
  "verdict": "<phrase 1 ligne résumant le potentiel Discover de cet article>",
  "priority_fixes": [
    {{
      "priority": "CRITIQUE|IMPORTANT|BONUS",
      "category": "Image|og:title|og:description|Contenu|Entités|Angle|Technique",
      "problem": "<ce qui est problématique actuellement>",
      "action": "<action concrète et précise à réaliser>",
      "example": "<exemple concret : nouveau titre, nouvelle description, etc. si pertinent>"
    }}
  ],
  "meta_title_rewrites": [
    "<proposition 1 de balise <title> SEO (55-65 car., mot-clé principal en tête)>",
    "<proposition 2 de balise <title>>",
    "<proposition 3 de balise <title>>"
  ],
  "og_title_rewrites": [
    "<proposition 1 de nouveau og:title (50-80 car., émotionnel, entité nommée)>",
    "<proposition 2 de nouveau og:title>",
    "<proposition 3 de nouveau og:title>"
  ],
  "og_description_rewrite": "<nouvelle og:description optimisée (120-160 car.)>",
  "image_seo": {{
    "alt_texts": [
      "<alt text 1 : descriptif, mot-clé principal, sans 'image de'>",
      "<alt text 2>",
      "<alt text 3>"
    ],
    "filenames": [
      "<nom-de-fichier-seo-1.jpg (tirets, mots-clés, sans accents)>",
      "<nom-de-fichier-seo-2.jpg>",
      "<nom-de-fichier-seo-3.jpg>"
    ]
  }},
  "image_status": {{
    "has_image": <true|false>,
    "max_image_preview_detected": <true|false>,
    "estimated_width_ok": <true|false>,
    "recommendation": "<recommandation image spécifique>"
  }},
  "entity_analysis": {{
    "entities_found": ["<entité 1>", "<entité 2>", "..."],
    "entities_missing": ["<entité qui devrait être mentionnée>"],
    "knowledge_graph_strength": "<fort|moyen|faible>"
  }},
  "trend_alignment": {{
    "is_timely": <true|false>,
    "trend_context": "<explication du contexte de tendance>",
    "freshness_window": "<durée de vie estimée dans Discover>"
  }},
  "quick_wins": [
    "<action rapide 1 (< 5 min)>",
    "<action rapide 2>",
    "<action rapide 3>"
  ],
  "image_prompts": [
    "<prompt image IA en anglais, style photoréaliste>",
    "<prompt image IA en anglais, style illustratif/graphique>"
  ]
}}"""


DRAFT_PROMPT = """Tu vas analyser un article BROUILLON (non encore publié) pour optimiser sa distribution dans Google Discover.

## DONNÉES DU BROUILLON

**Titre H1 rédigé :** {title}
**og:title envisagé :** {og_title}
**og:description envisagée :** {og_description}
**Catégories/Tags :** {categories}
**Contenu de l'article :**
{full_content}

---

## CONNAISSANCES DISCOVER À APPLIQUER

**L'article n'est pas encore publié. Génère des recommandations "de création" :**
1. Image à créer : 1200px+ 16:9 obligatoire, + meta `max-image-preview:large` dans le head → jusqu'à +79% CTR. Décris précisément l'image idéale pour ce sujet.
2. `og:title` à rédiger : 50-80 caractères, entité nommée + enjeu clair, angle émotionnel (surprise, curiosité, polémique)
3. `og:description` à rédiger : accroche complémentaire, renforce la curiosité sans spoiler, 120-160 caractères
4. Entités Knowledge Graph à nommer dans le contenu (personnes, marques, produits, lieux)
5. Angle : est-ce que le sujet est timely (trend actuel) ou evergreen ? Comment renforcer l'angle ?
6. E-E-A-T : recommandations pour renforcer l'expertise visible dans le texte
7. Structure du contenu : intro, sous-titres, longueur idéale pour Discover
8. Éviter le clickbait pur (pénalise le pCTR après le 1er cycle)
9. Image IA : génère 2 prompts prêts pour Midjourney/DALL-E — 1 photoréaliste, 1 illustratif/graphique — en anglais, détaillés (sujet, ambiance, éclairage, style)

---

## FORMAT DE RÉPONSE (JSON strict)

{{
  "score_before": <entier 0-100, score Discover estimé du brouillon tel quel>,
  "score_after": <entier 0-100, score estimé après tes optimisations>,
  "verdict": "<phrase 1 ligne résumant le potentiel Discover de cet article>",
  "priority_fixes": [
    {{
      "priority": "CRITIQUE|IMPORTANT|BONUS",
      "category": "Image|og:title|og:description|Contenu|Entités|Angle|Technique|Structure",
      "problem": "<ce qui manque ou est sous-optimal dans le brouillon>",
      "action": "<action concrète et précise à réaliser avant publication>",
      "example": "<exemple concret : titre suggéré, description, type d'image, etc.>"
    }}
  ],
  "meta_title_rewrites": [
    "<proposition 1 de balise <title> SEO (55-65 car., mot-clé principal en tête)>",
    "<proposition 2 de balise <title>>",
    "<proposition 3 de balise <title>>"
  ],
  "og_title_rewrites": [
    "<proposition 1 de og:title optimisé (50-80 car., émotionnel, entité nommée)>",
    "<proposition 2 de og:title optimisé>",
    "<proposition 3 de og:title optimisé>"
  ],
  "og_description_rewrite": "<og:description optimisée prête à copier (120-160 car.)>",
  "image_seo": {{
    "alt_texts": [
      "<alt text 1 : descriptif, mot-clé principal, sans 'image de'>",
      "<alt text 2>",
      "<alt text 3>"
    ],
    "filenames": [
      "<nom-de-fichier-seo-1.jpg (tirets, mots-clés, sans accents)>",
      "<nom-de-fichier-seo-2.jpg>",
      "<nom-de-fichier-seo-3.jpg>"
    ]
  }},
  "image_status": {{
    "has_image": false,
    "max_image_preview_detected": false,
    "estimated_width_ok": false,
    "recommendation": "<description précise de l'image idéale à créer pour ce sujet : sujet, cadrage, style, format>"
  }},
  "entity_analysis": {{
    "entities_found": ["<entité déjà présente dans le texte>"],
    "entities_missing": ["<entité à ajouter dans le contenu pour renforcer l'ancrage KG>"],
    "knowledge_graph_strength": "<fort|moyen|faible>"
  }},
  "trend_alignment": {{
    "is_timely": <true|false>,
    "trend_context": "<explication du contexte de tendance et fenêtre de publication idéale>",
    "freshness_window": "<durée de vie estimée dans Discover une fois publié>"
  }},
  "quick_wins": [
    "<action rapide 1 à faire avant de publier (< 5 min)>",
    "<action rapide 2>",
    "<action rapide 3>"
  ],
  "image_prompts": [
    "<prompt image IA en anglais, style photoréaliste>",
    "<prompt image IA en anglais, style illustratif/graphique>"
  ]
}}"""


QUICK_OPTIMIZE_PROMPT = """Tu es un expert SEO Google Discover pour Journal du Geek (média tech/pop culture).

Sujet de l'article : {subject}

Génère en JSON strict :
{{
  "tags": ["<tag 1>", "<tag 2>"],
  "image_filenames": [
    "<nom-de-fichier-seo-1.jpg>",
    "<nom-de-fichier-seo-2.jpg>",
    "<nom-de-fichier-seo-3.jpg>"
  ],
  "image_alts": [
    "<description alt 1>",
    "<description alt 2>",
    "<description alt 3>"
  ],
  "discover_titles": [
    "<titre Discover optimisé 1>",
    "<titre Discover optimisé 2>",
    "<titre Discover optimisé 3>"
  ],
  "image_prompts": [
    "<prompt image IA en anglais, style photoréaliste>",
    "<prompt image IA en anglais, style illustratif/graphique>"
  ]
}}

Règles :
- Tags : 6 à 10 mots-clés courts, sans hashtag, adaptés au CMS JDG (ex: "Intelligence artificielle", "OpenAI", "GPT-5")
- Noms de fichiers : minuscules, tirets, sans accents, .jpg (ex: "gpt-5-openai-intelligence-artificielle.jpg")
- Alt texts : descriptifs, entité principale incluse, 8-15 mots, sans "image de" ni "photo de"
- Titres Discover : 50-80 caractères, angle émotionnel (surprise/curiosité/polémique), entité nommée, évite le clickbait vide
- Prompts image IA : en anglais, détaillés (sujet principal, ambiance, éclairage, style), prêts pour Midjourney ou DALL-E, illustrent l'article sans être du clickbait visuel — 1 style photoréaliste, 1 style illustratif/graphique
Réponds UNIQUEMENT avec le JSON, sans markdown."""


def quick_optimize(subject: str) -> dict:
    """Génère tags, noms de fichier image, alt texts et titres Discover à partir d'un sujet."""
    import time
    prompt = QUICK_OPTIMIZE_PROMPT.format(subject=subject)

    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except Exception as e:
            if attempt == 2 or "overloaded" not in str(e).lower():
                raise
            time.sleep(5 * (attempt + 1))

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    return json.loads(raw)


def analyze_draft(article_data: dict) -> dict:
    """Send draft article to Claude and get pre-publication Discover optimization report."""
    prompt = DRAFT_PROMPT.format(
        title=article_data.get("title", ""),
        og_title=article_data.get("og_title", "(non défini)"),
        og_description=article_data.get("og_description", "(non définie)"),
        categories=article_data.get("categories", ""),
        full_content=article_data.get("full_content", "")[:8000],
    )

    import time
    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT,
            )
            break
        except Exception as e:
            if attempt == 2 or "overloaded" not in str(e).lower():
                raise
            time.sleep(5 * (attempt + 1))

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    return json.loads(raw)


def analyze_article(article_data: dict) -> dict:
    """Send article to Claude and get Discover optimization report."""
    prompt = ANALYSIS_PROMPT.format(
        title=article_data.get("title", ""),
        og_title=article_data.get("og_title", "(non détecté)"),
        og_description=article_data.get("og_description", "(non détectée)"),
        author=article_data.get("author", ""),
        published_at=article_data.get("published_at", ""),
        categories=article_data.get("categories", ""),
        link=article_data.get("link", ""),
        og_image=article_data.get("og_image", "(aucune)"),
        robots_meta=article_data.get("robots_meta", "(non détectée)"),
        full_content=article_data.get("full_content", "")[:6000],
    )

    import time
    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT,
            )
            break
        except Exception as e:
            if attempt == 2 or "overloaded" not in str(e).lower():
                raise
            time.sleep(5 * (attempt + 1))

    raw = message.content[0].text.strip()

    # Clean potential markdown code fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    return json.loads(raw)
