import requests
from datetime import datetime
from bs4 import BeautifulSoup
import sys
import re

RASFF_CONSUMERS_URL = "https://webgate.ec.europa.eu/rasff-window/screen/consumers"
RASFF_LIST_URL = "https://webgate.ec.europa.eu/rasff-window/screen/list"
RASFF_SEARCH_URL = "https://webgate.ec.europa.eu/rasff-window/screen/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
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
    return "Contaminants"


def detect_risk(text):
    t = text.lower()
    if any(w in t for w in [
        "salmonella", "listeria", "contamination",
        "undeclared allergen", "recall", "aflatoxin",
        "e. coli", "hepatitis", "norovirus", "pathogen",
        "dangerous", "serious", "alert"
    ]):
        return "High"
    if any(w in t for w in [
        "traceability", "fraud", "origin", "residue",
        "pesticide", "migration", "heavy metal",
        "information notification", "border rejection"
    ]):
        return "Medium"
    return "Low"


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
            "url": RASFF_LIST_URL,
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        }
    ]


def try_scrape_page(url, label, session):
    sys.stderr.write(f"[RASFF] Trying scrape: {label} -> {url}\n")
    sys.stderr.flush()

    try:
        resp = session.get(url, timeout=25)
        sys.stderr.write(f"[RASFF] {label} status: {resp.status_code}, length: {len(resp.text)}\n")
        sys.stderr.flush()

        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and "notification" in script.string.lower():
                sys.stderr.write(f"[RASFF] {label} found script with notification data\n")
                sys.stderr.flush()

        rows = soup.find_all("tr")
        sys.stderr.write(f"[RASFF] {label} table rows: {len(rows)}\n")
        sys.stderr.flush()

        links = soup.find_all("a", href=True)
        notif_links = [
            a for a in links
            if "notification" in a["href"].lower()
        ]
        sys.stderr.write(f"[RASFF] {label} notification links: {len(notif_links)}\n")
        sys.stderr.flush()

        text = soup.get_text(" ", strip=True)
        sys.stderr.write(f"[RASFF] {label} text length: {len(text)}\n")
        sys.stderr.write(f"[RASFF] {label} first 300 chars: {text[:300]}\n")
        sys.stderr.flush()

        return {
            "soup": soup,
            "text": text,
            "rows": rows,
            "notif_links": notif_links,
            "html": resp.text,
        }

    except Exception as e:
        sys.stderr.write(f"[RASFF] {label} error: {e}\n")
        sys.stderr.flush()
        return None


def fetch_rasff_updates(limit=10):
    session = requests.Session()
    session.headers.update(HEADERS)

    for url, label in [
        (RASFF_CONSUMERS_URL, "consumers"),
        (RASFF_LIST_URL, "list"),
        (RASFF_SEARCH_URL, "search"),
    ]:
        result = try_scrape_page(url, label, session)

        if not result:
            continue

        if result["notif_links"]:
            items = []
            for i, link_tag in enumerate(result["notif_links"][:limit]):
                href = link_tag["href"]
                if not href.startswith("http"):
                    href = f"https://webgate.ec.europa.eu{href}"

                text = link_tag.get_text(strip=True)
                if not text or len(text) < 5:
                    continue

                topic = detect_topic(text)
                risk = detect_risk(text)

                ref_match = re.search(r"(\d{4}\.\d{4})", text + href)
                reference = ref_match.group(1) if ref_match else f"rasff-{i}"

                if risk == "High":
                    impact = "May require immediate compliance escalation."
                    action = "Assess exposure and review supplier controls."
                elif risk == "Medium":
                    impact = "May affect documentation or traceability."
                    action = "Review internal records."
                else:
                    impact = "Lower urgency, monitor developments."
                    action = "Document for compliance review."

                items.append({
                    "id": f"rasff-{reference}",
                    "title": text[:200],
                    "source": "RASFF",
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                    "jurisdiction": "EU",
                    "topic": topic,
                    "risk_level": risk,
                    "ai_summary": text[:200],
                    "business_impact": impact,
                    "recommended_action": action,
                    "raw_text": text,
                    "url": href,
                    "notification_reference": reference,
                    "source_status": "live",
                    "fetch_method": "html_scrape",
                    "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                })

            if items:
                sys.stderr.write(f"[RASFF] SUCCESS from {label}: {len(items)} items\n")
                sys.stderr.flush()
                return items

    sys.stderr.write("[RASFF] All scraping attempts failed, using fallback\n")
    sys.stderr.flush()
    return fallback_rasff_examples()
