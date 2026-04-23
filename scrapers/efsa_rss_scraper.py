import feedparser
from datetime import datetime

EFSA_RSS_URL = "https://www.efsa.europa.eu/en/press/rss"


def detect_topic(text):
    t = text.lower()
    if any(w in t for w in ["label", "labelling", "allergen"]):
        return "Labeling"
    if any(w in t for w in ["traceability", "tracking", "supply chain"]):
        return "Traceability"
    if any(w in t for w in ["fraud", "origin", "authenticity"]):
        return "Fraud"
    if any(w in t for w in ["novel food", "novel foods"]):
        return "Novel Foods"
    if any(w in t for w in ["pesticide", "residue", "contaminant", "chemical", "salmonella", "listeria"]):
        return "Contaminants"
    return "Food Safety"


def detect_risk(text):
    t = text.lower()
    if any(w in t for w in ["salmonella", "listeria", "outbreak", "contamination", "recall", "aflatoxin"]):
        return "High"
    if any(w in t for w in ["label", "traceability", "fraud", "residue", "pesticide"]):
        return "Medium"
    return "Low"


def normalize_date(struct_time_obj):
    try:
        return datetime(*struct_time_obj[:6]).strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def safe_summary(entry):
    summary = entry.get("summary", "") or ""
    return summary.replace("\n", " ").strip()[:2000]


def build_business_impact(risk_level, topic):
    if risk_level == "High":
        return "This may influence ongoing compliance planning, product assessments, or documentation updates."
    if topic == "Labeling":
        return "This may affect packaging reviews, claims, and internal label approval workflows."
    if topic == "Traceability":
        return "This may affect documentation consistency and supply chain visibility."
    if topic == "Fraud":
        return "This may influence provenance checks and supplier verification."
    if topic == "Contaminants":
        return "This may affect supplier review, testing assumptions, and product risk assessments."
    return "This may affect QA workflows, specifications, and operational risk exposure."


def build_recommended_action(risk_level, topic):
    if risk_level == "High":
        return "Review the update promptly and determine whether internal escalation is required."
    if topic == "Labeling":
        return "Review current labels and determine whether any declarations need attention."
    if topic == "Traceability":
        return "Review traceability documentation and assess whether process updates are needed."
    if topic == "Fraud":
        return "Review provenance and supplier documentation for any control gaps."
    if topic == "Contaminants":
        return "Review supplier controls and relevance to your product categories."
    return "Review the update and determine whether monitoring actions are needed."


def fallback_efsa_examples():
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return [
        {
            "id": "efsa-fallback-1",
            "title": "EFSA fallback: no live RSS items returned",
            "source": "EFSA",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "jurisdiction": "EU",
            "topic": "Food Safety",
            "risk_level": "Low",
            "ai_summary": "No live EFSA RSS items were returned.",
            "business_impact": "This is a fallback sample.",
            "recommended_action": "Check the EFSA feed URL and retry.",
            "raw_text": "Fallback EFSA sample record.",
            "url": EFSA_RSS_URL,
            "source_status": "fallback",
            "fetch_method": "fallback",
            "notification_reference": "n/a",
            "last_verified": now_str,
        }
    ]


def fetch_efsa_updates(limit=10):
    try:
        feed = feedparser.parse(EFSA_RSS_URL)

        if not feed.entries:
            print("[EFSA] No entries found in RSS feed")
            return fallback_efsa_examples()

        results = []
        for i, entry in enumerate(feed.entries[:limit]):
            title = entry.get("title", "Untitled EFSA update").strip()
            summary = safe_summary(entry)
            combined = f"{title} {summary}"

            topic = detect_topic(combined)
            risk_level = detect_risk(combined)

            pp = entry.get("published_parsed") or entry.get("updated_parsed")
            date_str = normalize_date(pp) if pp else datetime.utcnow().strftime("%Y-%m-%d")
            link = entry.get("link", "https://www.efsa.europa.eu/")

            results.append({
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
            })

        print(f"[EFSA] Fetched {len(results)} live items")
        return results if results else fallback_efsa_examples()

    except Exception as e:
        print(f"[EFSA] Error: {e}")
        return fallback_efsa_examples()
