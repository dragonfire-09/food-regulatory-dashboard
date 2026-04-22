import requests
from bs4 import BeautifulSoup
from datetime import datetime


RASFF_URL = "https://webgate.ec.europa.eu/rasff-window/screen/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def fallback_rasff_examples():
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
            "url": RASFF_URL,
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
            "url": RASFF_URL,
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
            "url": RASFF_URL,
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
            "url": RASFF_URL,
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
            "url": RASFF_URL,
        },
    ]


def detect_topic(text: str) -> str:
    t = text.lower()
    if "allergen" in t or "label" in t:
        return "Labeling"
    if "traceability" in t:
        return "Traceability"
    if "fraud" in t or "origin" in t:
        return "Fraud"
    return "Contaminants"


def detect_risk(text: str) -> str:
    t = text.lower()
    if any(word in t for word in ["salmonella", "listeria", "contamination", "undeclared allergen", "recall"]):
        return "High"
    if any(word in t for word in ["traceability", "fraud", "origin"]):
        return "Medium"
    return "Low"


def parse_possible_cards(soup):
    text_blocks = []
    for tag in soup.find_all(["div", "td", "span", "p"]):
        txt = tag.get_text(" ", strip=True)
        if txt and len(txt) > 40:
            text_blocks.append(txt)

    results = []
    seen = set()

    for i, block in enumerate(text_blocks[:20]):
        if block in seen:
            continue
        seen.add(block)

        topic = detect_topic(block)
        risk = detect_risk(block)

        if risk == "High":
            impact = "This may require immediate compliance escalation, supplier review, or product containment measures."
            action = "Assess product and batch exposure, review supplier controls, and determine whether market action is needed."
        elif risk == "Medium":
            impact = "This may affect documentation, product traceability, or commercial claims."
            action = "Review internal records and identify whether legal, quality, or supply chain teams need to respond."
        else:
            impact = "This appears lower urgency but may still be relevant for future compliance review."
            action = "Monitor developments and document relevance for internal horizon scanning."

        short_title = block[:120].strip()
        results.append({
            "id": f"rasff-live-{i}",
            "title": short_title,
            "source": "RASFF",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "jurisdiction": "EU",
            "topic": topic,
            "risk_level": risk,
            "ai_summary": block[:320],
            "business_impact": impact,
            "recommended_action": action,
            "raw_text": block,
            "url": RASFF_URL,
        })

    return results[:5]


def fetch_rasff_updates(limit: int = 5):
    try:
        response = requests.get(RASFF_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        parsed = parse_possible_cards(soup)

        if parsed:
            return parsed[:limit]

        return fallback_rasff_examples()[:limit]

    except Exception:
        return fallback_rasff_examples()[:limit]
