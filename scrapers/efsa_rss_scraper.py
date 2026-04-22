import feedparser
from dateutil import parser as date_parser


EFSA_FEED_URL = "https://www.efsa.europa.eu/en/press/rss"


def detect_topic(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()

    if "label" in text:
        return "Labeling"
    if "traceability" in text:
        return "Traceability"
    if "novel food" in text or "novel" in text:
        return "Novel Foods"
    if "pesticide" in text or "contaminant" in text:
        return "Contaminants"
    if "animal health" in text:
        return "Animal Health"
    return "Food Safety"


def detect_risk(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()

    if any(word in text for word in ["outbreak", "recall", "urgent", "contamination", "serious"]):
        return "High"
    if any(word in text for word in ["guidance", "consultation", "assessment", "opinion"]):
        return "Medium"
    return "Low"


def safe_date(value):
    try:
        return date_parser.parse(value).strftime("%Y-%m-%d")
    except Exception:
        return "2026-01-01"


def fetch_efsa_updates(limit: int = 10):
    feed = feedparser.parse(EFSA_FEED_URL)
    results = []

    for i, entry in enumerate(feed.entries[:limit]):
        title = getattr(entry, "title", "EFSA Update")
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        published = safe_date(getattr(entry, "published", "2026-01-01"))
        url = getattr(entry, "link", "")

        topic = detect_topic(title, summary)
        risk = detect_risk(title, summary)

        if risk == "High":
            impact = "This may require rapid review by compliance, quality, or supply chain teams depending on product exposure."
            action = "Assess affected product categories, internal controls, and any immediate regulatory implications."
        elif risk == "Medium":
            impact = "This may influence ongoing compliance planning, product assessments, or documentation updates."
            action = "Review the update and determine whether internal guidance or monitoring actions are needed."
        else:
            impact = "This appears more relevant for horizon scanning and future compliance awareness."
            action = "Log the update for monitoring and review relevance in upcoming compliance cycles."

        results.append({
            "id": f"efsa-{i}",
            "title": title,
            "source": "EFSA",
            "date": published,
            "jurisdiction": "EU",
            "topic": topic,
            "risk_level": risk,
            "ai_summary": summary[:350] if summary else "EFSA update published.",
            "business_impact": impact,
            "recommended_action": action,
            "raw_text": summary,
            "url": url
        })

    return results
