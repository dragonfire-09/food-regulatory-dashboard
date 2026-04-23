import feedparser
import urllib.request
from datetime import datetime
import sys

# ================================================================
# SOURCES - Sadece doğrulanmış ve hızlı kaynaklar
# ================================================================

SOURCES = [
    {
        "name": "WHO Food Safety",
        "url": "https://www.who.int/rss-feeds/news-english.xml",
        "source_label": "WHO",
        "jurisdiction": "International",
        "filter": True,
    },
    {
        "name": "FSA UK Alerts",
        "url": "https://www.food.gov.uk/rss-feed/alerts",
        "source_label": "FSA UK",
        "jurisdiction": "UK",
        "filter": False,
    },
    {
        "name": "FDA Recalls",
        "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/recalls/rss.xml",
        "source_label": "FDA",
        "jurisdiction": "USA",
        "filter": False,
    },
    {
        "name": "ANSES France",
        "url": "https://www.anses.fr/en/rss.xml",
        "source_label": "ANSES",
        "jurisdiction": "France",
        "filter": False,
    },
    {
        "name": "Food Safety News",
        "url": "https://www.foodsafetynews.com/feed/",
        "source_label": "FSN",
        "jurisdiction": "International",
        "filter": False,
    },
    {
        "name": "GOV UK Food",
        "url": "https://www.gov.uk/search/all.atom?keywords=food+safety&order=updated-newest",
        "source_label": "GOV UK",
        "jurisdiction": "UK",
        "filter": False,
    },
]

FOOD_KEYWORDS = [
    "food", "safety", "contamination", "outbreak",
    "salmonella", "listeria", "recall", "nutrition",
    "foodborne", "hygiene", "allergen", "pesticide",
]


# ================================================================
# HELPERS
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
        "pesticide", "migration", "heavy metal",
        "border rejection"
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
            "id": "fallback-1",
            "title": "Food Safety fallback: Live sources unavailable",
            "source": "System",
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
# FETCH SINGLE SOURCE
# ================================================================

def fetch_single_source(source, limit=10):
    name = source["name"]
    url = source["url"]
    source_label = source["source_label"]
    jurisdiction = source["jurisdiction"]
    needs_filter = source.get("filter", False)

    sys.stderr.write(f"[SOURCE] {name} -> {url}\n")
    sys.stderr.flush()

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; FoodRegDashboard/1.0)"
            }
        )
        response = urllib.request.urlopen(req, timeout=10)
        raw = response.read()
    except Exception as e:
        sys.stderr.write(f"[SOURCE] {name} timeout/error: {e}\n")
        sys.stderr.flush()
        return []

    feed = feedparser.parse(raw)
    count = len(feed.entries) if feed.entries else 0
    sys.stderr.write(f"[SOURCE] {name}: {count} entries\n")
    sys.stderr.flush()

    if count == 0:
        return []

    results = []
    for i, entry in enumerate(feed.entries[:limit]):
        title = entry.get("title", "Untitled").strip()
        summary = safe_text(entry, "summary")
        link = entry.get("link", url)
        combined = f"{title} {summary}"

        # Filtre gereken kaynaklar (WHO gibi)
        if needs_filter:
            if not any(kw in combined.lower() for kw in FOOD_KEYWORDS):
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


# ================================================================
# MAIN FETCH FUNCTION
# ================================================================

def fetch_rasff_updates(limit=30):
    all_results = []

    for source in SOURCES:
        try:
            items = fetch_single_source(source, limit=10)
            if items:
                all_results.extend(items)
                sys.stderr.write(f"[SOURCE] Got {len(items)} from {source['name']}\n")
                sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"[SOURCE] {source['name']} failed: {e}\n")
            sys.stderr.flush()
            continue

    if all_results:
        sys.stderr.write(f"[SOURCE] TOTAL: {len(all_results)} live items\n")
        sys.stderr.flush()
        return all_results

    sys.stderr.write("[SOURCE] All sources failed, using fallback\n")
    sys.stderr.flush()
    return fallback_rasff_examples()
