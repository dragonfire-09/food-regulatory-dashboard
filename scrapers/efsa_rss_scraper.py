import feedparser
from datetime import datetime


EFSA_RSS_URL = "https://www.efsa.europa.eu/en/press/rss"


def detect_topic(text: str) -> str:
    t = text.lower()

    if any(word in t for word in ["label", "labelling", "allergen"]):
        return "Labeling"
    if any(word in t for word in ["traceability", "tracking", "supply chain"]):
        return "Traceability"
    if any(word in t for word in ["fraud", "origin", "authenticity"]):
        return "Fraud"
    if any(word in t for word in ["novel food", "novel foods"]):
        return "Novel Foods"
    if any(word in t for word in ["pesticide", "residue", "contaminant", "chemical", "salmonella", "listeria"]):
        return "Contaminants"

    return "Food Safety"


def detect_risk(text: str) -> str:
    t = text.lower()

    if any(word in t for word in ["salmonella", "listeria", "outbreak", "contamination", "recall", "aflatoxin"]):
        return "High"
    if any(word in t for word in ["label", "traceability", "fraud", "residue", "pesticide"]):
        return "Medium"

    return "Low"


def normalize_date(struct_time_obj):
    try:
        return datetime(*struct_time_obj[:6]).strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def safe_summary(entry):
    summary = entry.get("summary", "") or ""
    summary = summary.replace("\n", " ").strip()
    return summary[:2000]


def build_business_impact(risk_level: str, topic: str) -> str:
    if risk_level == "High":
        return "This may influence ongoing compliance planning, product assessments, or documentation updates."
    if topic == "Labeling":
        return "This may affect packaging reviews, claims, and internal label approval workflows."
    if topic == "Traceability":
        return "This may affect documentation consistency and supply chain visibility."
    if topic == "Fraud":
        return "This may influence provenance checks, claim substantiation, and supplier verification."
    if topic == "Contaminants":
        return "This may affect supplier review, testing assumptions, and product risk assessments."

    return "This may affect QA workflows, specifications, and operational risk exposure."


def build_recommended_action(risk_level: str, topic: str) -> str:
    if risk_level == "High":
        return "Review the update promptly and determine whether internal escalation or additional controls are required."
    if topic == "Labeling":
        return "Review current labels and determine whether any guidance, claims, or declarations need attention."
    if topic == "Traceability":
        return "Review traceability documentation and assess whether any process updates are needed."
    if topic == "Fraud":
        return "Review provenance and supplier documentation for any control gaps."
    if topic == "Contaminants":
        return "Review supplier controls, testing assumptions, and relevance to your product categories."

    return "Review the update and determine whether internal guidance or monitoring actions are needed."


def fallback_efsa_examples():
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return [
        {
            "id": "efsa-fallback-1",
            "title": "EFSA fallback sample: no live RSS items returned",
            "source": "EFSA",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "jurisdiction": "EU",
            "topic": "Food Safety",
            "risk_level": "Low",
            "ai_summary": "No live EFSA RSS items were returned at fetch time, so a fallback record is being shown.",
            "business_impact": "This is a fallback sample and should not be treated as live regulatory intelligence.",
            "recommended_action": "Check the EFSA feed URL and retry the live fetch.",
            "raw_text": "Fallback EFSA sample record.",
            "url": EFSA_RSS_URL,
            "source_status": "fallback",
            "fetch_method": "fallback",
            "notification_reference": "n/a",
            "last_verified": now_str,
        }
    ]


def fetch_efsa_updates(limit: int = 10):
    feed = feedparser.parse(EFSA_RSS_URL)

    if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
        return fallback_efsa_examples()

    if not getattr(feed, "entries", None):
        return fallback_efsa_examples()

    results = []

    for i, entry in enumerate(feed.entries[:limit]):
        title = entry.get("title", "Untitled EFSA update").strip()
        summary = safe_summary(entry)
        combined_text = f"{title} {summary}"

        topic = detect_topic(combined_text)
        risk_level = detect_risk(combined_text)

        published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        date_str = normalize_date(published_parsed) if published_parsed else datetime.utcnow().strftime("%Y-%m-%d")

        link = entry.get("link", "https://www.efsa.europa.eu/")

        item = {
            "id": f"efsa-{i}-{date_str}",
            "title": title,
            "source": "EFSA",
            "date": date_str,
            "jurisdiction": "EU",
            "topic": topic,
            "risk_level": risk_level,
            "ai_summary": summary if summary else title,
            "business_impact": build_business_impact(risk_level, topic),
            "recommended_action": build_recommended_action(risk_level, topic),
            "raw_text": summary if summary else title,
            "url": link,
            "source_status": "live",
            "fetch_method": "rss_feed",
            "notification_reference": "n/a",
            "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }

        results.append(item)

    return results if results else fallback_efsa_examples()
