import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup


RASFF_RESULTS_URL = "https://webgate.ec.europa.eu/rasff-window/screen/list"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FoodRegDashboard/1.0)"
}


def fallback_rasff_examples():
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    return [
        {
            "id": "rasff-demo-1",
            "title": "RASFF Alert: Salmonella detected in poultry product",
            "source": "RASFF",
            "date": "2026-03-01",
            "jurisdiction": "EU",
            "topic": "Contaminants",
            "risk_level": "High",
            "ai_summary": "A contamination alert related to Salmonella in poultry products may require immediate review of supply chain exposure.",
            "business_impact": "This may create recall, supplier control, and market compliance risks for affected operators.",
            "recommended_action": "Review suppliers, identify exposed batches, and assess whether any rapid response action is required.",
            "raw_text": "RASFF contamination notification related to poultry and microbiological risk.",
            "url": RASFF_RESULTS_URL,
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        },
        {
            "id": "rasff-demo-2",
            "title": "RASFF Alert: Pesticide residues found in vegetables",
            "source": "RASFF",
            "date": "2026-02-26",
            "jurisdiction": "EU",
            "topic": "Contaminants",
            "risk_level": "High",
            "ai_summary": "A pesticide residue issue has been flagged, which may affect importers, distributors, and compliance teams.",
            "business_impact": "This may increase supplier scrutiny, testing requirements, and product release delays.",
            "recommended_action": "Review analytical controls, supplier records, and any affected incoming lots.",
            "raw_text": "RASFF chemical contamination notification involving pesticide residues.",
            "url": RASFF_RESULTS_URL,
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        },
        {
            "id": "rasff-demo-3",
            "title": "RASFF Information: Traceability concerns for imported seafood",
            "source": "RASFF",
            "date": "2026-02-20",
            "jurisdiction": "EU",
            "topic": "Traceability",
            "risk_level": "Medium",
            "ai_summary": "A traceability-related concern may require stronger documentation and product tracking checks.",
            "business_impact": "Operators may need to improve documentation, supplier transparency, and internal tracking records.",
            "recommended_action": "Review traceability files, supplier documentation, and downstream product identification processes.",
            "raw_text": "RASFF information notice associated with incomplete product traceability records.",
            "url": RASFF_RESULTS_URL,
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        },
        {
            "id": "rasff-demo-4",
            "title": "RASFF Alert: Undeclared allergen in packaged snack product",
            "source": "RASFF",
            "date": "2026-02-18",
            "jurisdiction": "EU",
            "topic": "Labeling",
            "risk_level": "High",
            "ai_summary": "An undeclared allergen notification may trigger immediate packaging and market risk review.",
            "business_impact": "This may create recall exposure, customer complaints, and labeling compliance risks.",
            "recommended_action": "Check label controls, affected stock, and escalation procedures for allergen-related incidents.",
            "raw_text": "RASFF allergen-related notification involving undeclared ingredients in a snack product.",
            "url": RASFF_RESULTS_URL,
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        },
        {
            "id": "rasff-demo-5",
            "title": "RASFF Notification: Food fraud concern linked to origin declaration",
            "source": "RASFF",
            "date": "2026-02-15",
            "jurisdiction": "EU",
            "topic": "Fraud",
            "risk_level": "Medium",
            "ai_summary": "A fraud-related concern involving origin claims may increase scrutiny on supporting documentation.",
            "business_impact": "This may affect product claims, documentary controls, and supplier verification processes.",
            "recommended_action": "Review provenance records, claim substantiation, and supplier authenticity checks.",
            "raw_text": "RASFF fraud-related communication linked to product origin declaration.",
            "url": RASFF_RESULTS_URL,
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        },
    ]


def detect_topic(text: str) -> str:
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


def detect_risk(text: str) -> str:
    t = text.lower()

    if any(word in t for word in [
        "salmonella", "listeria", "contamination", "undeclared allergen",
        "recall", "aflatoxin", "pathogen"
    ]):
        return "High"

    if any(word in t for word in [
        "traceability", "fraud", "origin", "migration", "residue", "pesticide"
    ]):
        return "Medium"

    return "Low"


def normalize_date(text: str) -> str:
    match = re.search(r"(\d{2})-(\d{2})-(\d{4})", text)
    if match:
        d, m, y = match.groups()
        return f"{y}-{m}-{d}"
    return datetime.utcnow().strftime("%Y-%m-%d")


def extract_notification_links(html: str, limit: int = 5):
    pattern = r"https://webgate\.ec\.europa\.eu/rasff-window/screen/notification/\d+"
    urls = re.findall(pattern, html)

    seen = set()
    deduped = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
        if len(deduped) >= limit:
            break

    return deduped


def parse_detail_page(detail_url: str, session: requests.Session, index: int):
    response = session.get(detail_url, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    title_match = re.search(
        r"Notification\s+\d{4}\.\d+\.\s*(.*?)(?:Date of notification|Notifying country|Product|$)",
        text
    )
    if title_match:
        title = title_match.group(1).strip(" ;")
    else:
        title = text[:160].strip()

    date_match = re.search(r"Date of notification\s+(\d{2}-\d{2}-\d{4})", text)
    date_str = normalize_date(date_match.group(1)) if date_match else datetime.utcnow().strftime("%Y-%m-%d")

    reference_match = re.search(r"Notification\s+(\d{4}\.\d+)", text)
    reference = reference_match.group(1) if reference_match else f"unknown-{index}"

    topic = detect_topic(text)
    risk = detect_risk(text)

    if risk == "High":
        impact = "This may require immediate compliance escalation, supplier review, or product containment measures."
        action = "Assess product and batch exposure, review supplier controls, and determine whether market action is needed."
    elif risk == "Medium":
        impact = "This may affect documentation, product traceability, labeling, or commercial claims."
        action = "Review internal records and identify whether legal, quality, or supply chain teams need to respond."
    else:
        impact = "This appears lower urgency but may still be relevant for future compliance review."
        action = "Monitor developments and document relevance for internal horizon scanning."

    return {
        "id": f"rasff-{reference}",
        "title": title,
        "source": "RASFF",
        "date": date_str,
        "jurisdiction": "EU",
        "topic": topic,
        "risk_level": risk,
        "ai_summary": title,
        "business_impact": impact,
        "recommended_action": action,
        "raw_text": text[:2500],
        "url": detail_url,
        "notification_reference": reference,
        "source_status": "live",
        "fetch_method": "detail_page",
        "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }


def fetch_rasff_updates(limit: int = 5):
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        response = session.get(RASFF_RESULTS_URL, timeout=20)
        response.raise_for_status()

        links = extract_notification_links(response.text, limit=limit)

        if not links:
            return fallback_rasff_examples()[:limit]

        results = []
        for i, link in enumerate(links):
            try:
                item = parse_detail_page(link, session, i)
                results.append(item)
            except Exception:
                continue

        if results:
            return results[:limit]

        return fallback_rasff_examples()[:limit]

    except Exception:
        return fallback_rasff_examples()[:limit]
