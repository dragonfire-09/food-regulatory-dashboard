import feedparser
from datetime import datetime
import sys
import re

RASFF_RSS_URL = "https://webgate.ec.europa.eu/rasff-window/backend/public/notifications/rss"
RASFF_RSS_ALT = "https://webgate.ec.europa.eu/rasff-window/portal/backend/notification/rss"
RASFF_ATOM_URL = "https://webgate.ec.europa.eu/rasff-window/consumers/notifications/atom"

RASFF_PORTAL = "https://webgate.ec.europa.eu/rasff-window/screen/list"


def detect_topic(text):
    t = text.lower()
    if "allergen" in t or "label" in t:
        return "Labeling"
    if "traceability" in t:
        return "Traceability"
    if "fraud" in t or "origin" in t or "authenticity" in t:
        return "Fraud"
    if "novel" in t:
        return "Novel Foods"
    return "Contaminants"


def detect_risk(text):
    t = text.lower()
    if any(w in t for w in [
        "salmonella", "listeria", "contamination",
        "undeclared allergen", "recall", "aflatoxin",
        "e. coli", "hepatitis", "norovirus"
    ]):
        return "High"
    if any(w in t for w in [
        "traceability", "fraud", "origin", "residue",
        "pesticide", "migration", "heavy metal"
    ]):
        return "Medium"
    return "Low"


def normalize_date(struct_time_obj):
    try:
        return datetime(*struct_time_obj[:6]).strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def safe_summary(entry):
    summary = entry.get("summary", "") or entry.get("description", "") or ""
    return summary.replace("\n", " ").strip()[:2000]


def extract_reference(entry):
    title = entry.get("title", "")
    link = entry.get("link", "")

    ref_match = re.search(r"(\d{4}\.\d{4})", title)
    if ref_match:
        return ref_match.group(1)

    ref_match = re.search(r"(\d{4}\.\d{4})", link)
    if ref_match:
        return ref_match.group(1)

    ref_match = re.search(r"/notification/(\d+)", link)
    if ref_match:
        return ref_match.group(1)

    return None


def fallback_rasff_examples():
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return [
        {
            "id": "rasff-fallback-1",
            "title": "RASFF fallback: Live data unavailable",
            "source": "RASFF",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "jurisdiction": "EU",
            "topic": "Contaminants",
            "risk_level": "High",
            "ai_summary": "RASFF live data could not be fetched.",
            "business_impact": "This is a fallback record.",
            "recommended_action": "Check RASFF portal manually.",
            "raw_text": "Fallback RASFF record.",
            "url": RASFF_PORTAL,
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        }
    ]


def try_parse_feed(url, label):
    sys.stderr.write(f"[RASFF] Trying RSS: {label} -> {url}\n")
    sys.stderr.flush()

    feed = feedparser.parse(url)
    count = len(feed.entries) if feed.entries else 0

    sys.stderr.write(f"[RASFF] {label}: {count} entries, bozo={feed.bozo}\n")
    sys.stderr.flush()

    if count > 0:
        return feed
    return None


def fetch_rasff_updates(limit=10):
    feed = None

    for url, label in [
        (RASFF_RSS_URL, "public_rss"),
        (RASFF_RSS_ALT, "portal_rss"),
        (RASFF_ATOM_URL, "consumers_atom"),
    ]:
        feed = try_parse_feed(url, label)
        if feed:
            break

    if not feed or not feed.entries:
        sys.stderr.write("[RASFF] All RSS feeds failed, using fallback\n")
        sys.stderr.flush()
        return fallback_rasff_examples()

    results = []
    for i, entry in enumerate(feed.entries[:limit]):
        title = entry.get("title", "RASFF Notification").strip()
        summary = safe_summary(entry)
        link = entry.get("link", RASFF_PORTAL)
        combined = f"{title} {summary}"

        topic = detect_topic(combined)
        risk = detect_risk(combined)

        pp = entry.get("published_parsed") or entry.get("updated_parsed")
        date_str = normalize_date(pp) if pp else datetime.utcnow().strftime("%Y-%m-%d")

        reference = extract_reference(entry) or f"rasff-{i}-{date_str}"

        if risk == "High":
            impact = "May require immediate compliance escalation or product containment."
            action = "Assess exposure and review supplier controls."
        elif risk == "Medium":
            impact = "May affect documentation, traceability, or labeling."
            action = "Review internal records."
        else:
            impact = "Lower urgency but relevant for compliance review."
            action = "Monitor developments."

        results.append({
            "id": f"rasff-{reference}",
            "title": title,
            "source": "RASFF",
            "date": date_str,
            "jurisdiction": "EU",
            "topic": topic,
            "risk_level": risk,
            "ai_summary": summary if summary else title,
            "business_impact": impact,
            "recommended_action": action,
            "raw_text": combined,
            "url": link,
            "notification_reference": reference,
            "source_status": "live",
            "fetch_method": "rss_feed",
            "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        })

    sys.stderr.write(f"[RASFF] SUCCESS: {len(results)} live items from RSS\n")
    sys.stderr.flush()
    return results if results else fallback_rasff_examples()
