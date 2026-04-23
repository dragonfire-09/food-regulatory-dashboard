import feedparser
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import sys
import re
import json

# Birden fazla canlı kaynak
SOURCES = [
    {
        "name": "RASFF Portal API v2",
        "type": "api",
        "url": "https://webgate.ec.europa.eu/rasff-window/backend/public/notification/search/consolidated",
        "method": "POST",
        "payload": {"pageNumber": 1, "itemsPerPage": 10},
    },
    {
        "name": "RASFF Portal API v3",
        "type": "api",
        "url": "https://webgate.ec.europa.eu/rasff-window/backend/public/notifications/search",
        "method": "POST",
        "payload": {"pageNumber": 1, "itemsPerPage": 10},
    },
    {
        "name": "EU Food Fraud Network",
        "type": "rss",
        "url": "https://ec.europa.eu/food/safety/rasff-food-and-feed-safety-alerts_en",
    },
    {
        "name": "WHO Food Safety News",
        "type": "rss",
        "url": "https://www.who.int/rss-feeds/news-english.xml",
    },
    {
        "name": "FSA UK Alerts",
        "type": "rss",
        "url": "https://www.food.gov.uk/rss-feed/alerts",
    },
    {
        "name": "FDA Recalls RSS",
        "type": "rss",
        "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/recalls/rss.xml",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FoodRegDashboard/1.0)",
    "Accept": "application/json,text/html,application/xml,*/*",
}


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
    if any(w in t for w in ["pesticide", "residue", "contaminant", "chemical",
                             "salmonella", "listeria", "aflatoxin", "mercury"]):
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


def fallback_rasff_examples():
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return [
        {
            "id": "rasff-fallback-1",
            "title": "RASFF/Food Safety fallback: Live sources unavailable",
            "source": "RASFF",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "jurisdiction": "EU",
            "topic": "Contaminants",
            "risk_level": "High",
            "ai_summary": "Live food safety data could not be fetched.",
            "business_impact": "This is a fallback record.",
            "recommended_action": "Check RASFF portal manually.",
            "raw_text": "Fallback record.",
            "url": "https://webgate.ec.europa.eu/rasff-window/screen/list",
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        }
    ]


def try_api_source(source, session):
    sys.stderr.write(f"[RASFF] Trying API: {source['name']}\n")
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

        sys.stderr.write(f"[RASFF] {source['name']} status: {resp.status_code}\n")
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

        sys.stderr.write(f"[RASFF] {source['name']} items: {len(notifications)}\n")
        sys.stderr.flush()

        results = []
        for i, notif in enumerate(notifications[:10]):
            ref = str(notif.get("reference", notif.get("id", f"api-{i}")))
            subj = str(notif.get("subject", notif.get("title", "Notification")))
            date_raw = str(notif.get("notificationDate", notif.get("date", "")))
            date_str = date_raw[:10] if len(date_raw) >= 10 else datetime.utcnow().strftime("%Y-%m-%d")

            combined = f"{subj} {notif.get('category', '')} {notif.get('notificationType', '')}"
            topic = detect_topic(combined)
            risk = detect_risk(combined)

            results.append({
                "id": f"rasff-{ref}",
                "title": subj,
                "source": "RASFF",
                "date": date_str,
                "jurisdiction": "EU",
                "topic": topic,
                "risk_level": risk,
                "ai_summary": subj,
                "business_impact": f"{'Urgent' if risk == 'High' else 'Review'} - from {source['name']}",
                "recommended_action": "Review and assess relevance.",
                "raw_text": combined,
                "url": f"https://webgate.ec.europa.eu/rasff-window/screen/notification/{ref}",
                "notification_reference": ref,
                "source_status": "live",
                "fetch_method": "api",
                "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            })

        return results

    except Exception as e:
        sys.stderr.write(f"[RASFF] {source['name']} error: {e}\n")
        sys.stderr.flush()
        return []


def try_rss_source(source, limit=10):
    sys.stderr.write(f"[RASFF] Trying RSS: {source['name']} -> {source['url']}\n")
    sys.stderr.flush()

    try:
        feed = feedparser.parse(source["url"])
        count = len(feed.entries) if feed.entries else 0
        sys.stderr.write(f"[RASFF] {source['name']}: {count} entries\n")
        sys.stderr.flush()

        if count == 0:
            return []

        results = []
        source_label = "RASFF"
        if "FSA" in source["name"]:
            source_label = "FSA UK"
        elif "FDA" in source["name"]:
            source_label = "FDA"
        elif "WHO" in source["name"]:
            source_label = "WHO"

        for i, entry in enumerate(feed.entries[:limit]):
            title = entry.get("title", "Untitled").strip()
            summary = safe_text(entry, "summary")
            link = entry.get("link", source["url"])
            combined = f"{title} {summary}"

            # WHO feed'den sadece food safety ile ilgili olanları al
            if "WHO" in source["name"]:
                food_keywords = ["food", "safety", "contamination", "outbreak",
                                 "salmonella", "listeria", "recall", "nutrition"]
                if not any(kw in combined.lower() for kw in food_keywords):
                    continue

            topic = detect_topic(combined)
            risk = detect_risk(combined)

            pp = entry.get("published_parsed") or entry.get("updated_parsed")
            date_str = normalize_date(pp) if pp else datetime.utcnow().strftime("%Y-%m-%d")

            results.append({
                "id": f"rasff-{source_label.lower()}-{i}-{date_str}",
                "title": title,
                "source": source_label,
                "date": date_str,
                "jurisdiction": "EU" if source_label in ["RASFF", "FSA UK"] else "International",
                "topic": topic,
                "risk_level": risk,
                "ai_summary": summary if summary else title,
                "business_impact": f"Signal from {source_label} - review for relevance.",
                "recommended_action": "Evaluate and determine if action needed.",
                "raw_text": combined,
                "url": link,
                "notification_reference": f"{source_label}-{i}",
                "source_status": "live",
                "fetch_method": "rss_feed",
                "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            })

        return results

    except Exception as e:
        sys.stderr.write(f"[RASFF] {source['name']} error: {e}\n")
        sys.stderr.flush()
        return []


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
            sys.stderr.write(f"[RASFF] Got {len(items)} from {source['name']}\n")
            sys.stderr.flush()

    if all_results:
        # En fazla limit kadar döndür
        all_results = all_results[:limit]
        sys.stderr.write(f"[RASFF] TOTAL SUCCESS: {len(all_results)} live items\n")
        sys.stderr.flush()
        return all_results

    sys.stderr.write("[RASFF] All sources failed, using fallback\n")
    sys.stderr.flush()
    return fallback_rasff_examples()
