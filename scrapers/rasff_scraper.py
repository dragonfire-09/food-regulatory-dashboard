import feedparser
import requests
from datetime import datetime
import sys
import re
import json

# ================================================================
# SOURCES
# ================================================================

SOURCES = [
    # RASFF API (şu an kapalı ama gelecekte açılabilir)
    {
        "name": "RASFF Portal API v2",
        "type": "api",
        "url": "https://webgate.ec.europa.eu/rasff-window/backend/public/notification/search/consolidated",
        "method": "POST",
        "payload": {"pageNumber": 1, "itemsPerPage": 10},
        "source_label": "RASFF",
        "jurisdiction": "EU",
    },
    # Aktif RSS kaynakları
    {
        "name": "WHO Food Safety",
        "type": "rss",
        "url": "https://www.who.int/rss-feeds/news-english.xml",
        "source_label": "WHO",
        "jurisdiction": "International",
    },
    {
        "name": "FSA UK Alerts",
        "type": "rss",
        "url": "https://www.food.gov.uk/rss-feed/alerts",
        "source_label": "FSA UK",
        "jurisdiction": "UK",
    },
    {
        "name": "FDA Recalls",
        "type": "rss",
        "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/recalls/rss.xml",
        "source_label": "FDA",
        "jurisdiction": "USA",
    },
    # Yeni kaynaklar
    {
        "name": "EFSA Scientific Opinions",
        "type": "rss",
        "url": "https://www.efsa.europa.eu/en/rss/scientific-outputs",
        "source_label": "EFSA Science",
        "jurisdiction": "EU",
    },
    {
        "name": "CFIA Canada Recalls",
        "type": "rss",
        "url": "https://recalls-rappels.canada.ca/en/feed/cfia-food-recall-warnings-702",
        "source_label": "CFIA",
        "jurisdiction": "Canada",
    },
    {
        "name": "EU Official Journal",
        "type": "rss",
        "url": "https://eur-lex.europa.eu/rss/document/OJ-L.xml",
        "source_label": "EU Law",
        "jurisdiction": "EU",
    },
    {
        "name": "Codex Alimentarius",
        "type": "rss",
        "url": "https://www.fao.org/fao-who-codexalimentarius/rss/en/",
        "source_label": "Codex",
        "jurisdiction": "International",
    },
    {
        "name": "BfR Germany",
        "type": "rss",
        "url": "https://www.bfr.bund.de/en/rss/press_information.xml",
        "source_label": "BfR",
        "jurisdiction": "Germany",
    },
    {
        "name": "ANSES France",
        "type": "rss",
        "url": "https://www.anses.fr/en/rss.xml",
        "source_label": "ANSES",
        "jurisdiction": "France",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FoodRegDashboard/1.0)",
    "Accept": "application/json,text/html,application/xml,*/*",
}


# ================================================================
# HELPER FUNCTIONS
# ================================================================

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
    if any(w in t for w in [
        "pesticide", "residue", "contaminant", "chemical",
        "salmonella", "listeria", "aflatoxin", "mercury"
    ]):
        return "Contaminants"
    return "Food Safety"


def detect_risk(text):
    t = text.lower()
    if any(w in t for w in [
        "salmonella", "listeria", "contamination", "recall",
        "undeclared allergen", "aflatoxin", "e. coli",
        "hepatitis", "norovirus", "pathogen", "dangerous",
        "serious", "alert", "warning", "death", "outbreak"
    ]):
        return "High"
    if any(w in t for w in [
        "traceability", "fraud", "origin", "residue",
        "pesticide", "migration", "heavy metal", "border rejection"
    ]):
        return "Medium"
    return "Low"


def normalize_date(struct_time_obj):
    try:
        return datetime(*struct_time_obj[:6]).strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def safe_text(entry, field):
    val = entry.get(field, "") or ""
    return val.replace("\n", " ").strip()[:2000]


# ================================================================
# FALLBACK
# ================================================================

def fallback_rasff_examples():
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return [
        {
            "id": "rasff-fallback-1",
            "title": "Food Safety fallback: Live sources unavailable",
            "source": "RASFF",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "jurisdiction": "EU",
            "topic": "Contaminants",
            "risk_level": "High",
            "ai_summary": "Live food safety data could not be fetched.",
            "business_impact": "This is a fallback record.",
            "recommended_action": "Check sources manually.",
            "raw_text": "Fallback record.",
            "url": "https://webgate.ec.europa.eu/rasff-window/screen/list",
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        }
    ]


# ================================================================
# API SOURCE
# ================================================================

def try_api_source(source, session):
    sys.stderr.write(f"[SOURCE] Trying API: {source['name']}\n")
    sys.stderr.flush()

    try:
        if source.get("method") == "POST":
            resp = session.post(
                source["url"],
                json=source.get("payload", {}),
                headers={"Content-Type": "application/json"},
                timeout=20,
            )
        else:
            resp = session.get(source["url"], timeout=20)

        sys.stderr.write(f"[SOURCE] {source['name']} status: {resp.status_code}\n")
        sys.stderr.flush()

        if resp.status_code != 200:
            return []

        data = resp.json()
        notifications = []
        if isinstance(data, list):
            notifications = data
        elif isinstance(data, dict):
            for key in ["notifications", "content", "results", "data", "items"]:
                if key in data and isinstance(data[key], list):
                    notifications = data[key]
                    break

        sys.stderr.write(f"[SOURCE] {source['name']} items: {len(notifications)}\n")
        sys.stderr.flush()

        if not notifications:
            return []

        source_label = source.get("source_label", "RASFF")
        jurisdiction = source.get("jurisdiction", "EU")

        results = []
        for i, notif in enumerate(notifications[:10]):
            ref = str(notif.get("reference", notif.get("id", f"api-{i}")))
            subj = str(notif.get("subject", notif.get("title", "Notification")))
            date_raw = str(notif.get("notificationDate", notif.get("date", "")))
            date_str = date_raw[:10] if len(date_raw) >= 10 else datetime.utcnow().strftime("%Y-%m-%d")

            combined = f"{subj} {notif.get('category', '')} {notif.get('notificationType', '')}"
            topic = detect_topic(combined)
            risk = detect_risk(combined)

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
                "id": f"rasff-{ref}",
                "title": subj,
                "source": source_label,
                "date": date_str,
                "jurisdiction": jurisdiction,
                "topic": topic,
                "risk_level": risk,
                "ai_summary": subj,
                "business_impact": impact,
                "recommended_action": action,
                "raw_text": combined,
                "url": f"https://webgate.ec.europa.eu/rasff-window/screen/notification/{ref}",
                "notification_reference": ref,
                "source_status": "live",
                "fetch_method": "api",
                "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            })

        return results

    except Exception as e:
        sys.stderr.write(f"[SOURCE] {source['name']} error: {e}\n")
        sys.stderr.flush()
        return []


# ================================================================
# RSS SOURCE
# ================================================================

def try_rss_source(source, limit=10):
    sys.stderr.write(f"[SOURCE] Trying RSS: {source['name']} -> {source['url']}\n")
    sys.stderr.flush()

    try:
        feed = feedparser.parse(source["url"])
        count = len(feed.entries) if feed.entries else 0
        sys.stderr.write(f"[SOURCE] {source['name']}: {count} entries\n")
        sys.stderr.flush()

        if count == 0:
            return []

        source_label = source.get("source_label", "RASFF")
        jurisdiction = source.get("jurisdiction", "EU")

        results = []
        for i, entry in enumerate(feed.entries[:limit]):
            title = entry.get("title", "Untitled").strip()
            summary = safe_text(entry, "summary")
            link = entry.get("link", source["url"])
            combined = f"{title} {summary}"

            # WHO - sadece food safety
            if source_label == "WHO":
                food_keywords = [
                    "food", "safety", "contamination", "outbreak",
                    "salmonella", "listeria", "recall", "nutrition",
                    "foodborne", "hygiene"
                ]
                if not any(kw in combined.lower() for kw in food_keywords):
                    continue

            # EU Official Journal - sadece food
            if source_label == "EU Law":
                food_keywords = [
                    "food", "regulation", "commission", "health",
                    "contaminant", "additive", "novel", "feed",
                    "pesticide", "residue", "hygiene", "labelling"
                ]
                if not any(kw in combined.lower() for kw in food_keywords):
                    continue

            topic = detect_topic(combined)
            risk = detect_risk(combined)

            pp = entry.get("published_parsed") or entry.get("updated_parsed")
            date_str = normalize_date(pp) if pp else datetime.utcnow().strftime("%Y-%m-%d")

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
                "id": f"{source_label.lower()}-{i}-{date_str}",
                "title": title,
                "source": source_label,
                "date": date_str,
                "jurisdiction": jurisdiction,
                "topic": topic,
                "risk_level": risk,
                "ai_summary": summary if summary else title,
                "business_impact": impact,
                "recommended_action": action,
                "raw_text": combined,
                "url": link,
                "notification_reference": f"{source_label}-{i}",
                "source_status": "live",
                "fetch_method": "rss_feed",
                "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            })

        return results

    except Exception as e:
        sys.stderr.write(f"[SOURCE] {source['name']} error: {e}\n")
        sys.stderr.flush()
        return []


# ================================================================
# MAIN FETCH FUNCTION
# ================================================================

def fetch_rasff_updates(limit=10):
    session = requests.Session()
    session.headers.update(HEADERS)

    all_results = []

    for source in SOURCES:
        if source["type"] == "api":
            items = try_api_source(source, session)
        else:
            items = try_rss_source(source, limit)

        if items:
            all_results.extend(items)
            sys.stderr.write(f"[SOURCE] Got {len(items)} from {source['name']}\n")
            sys.stderr.flush()

    if all_results:
        all_results = all_results[:limit]
        sys.stderr.write(f"[SOURCE] TOTAL SUCCESS: {len(all_results)} live items\n")
        sys.stderr.flush()
        return all_results

    sys.stderr.write("[SOURCE] All sources failed, using fallback\n")
    sys.stderr.flush()
    return fallback_rasff_examples()
