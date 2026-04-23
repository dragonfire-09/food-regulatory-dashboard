import requests
from datetime import datetime

RASFF_API_URL = (
    "https://webgate.ec.europa.eu/rasff-window/backend/shared/notifications/"
    "search/consolidated"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FoodRegDashboard/1.0)",
    "Accept": "application/json",
    "Content-Type": "application/json",
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
        "e. coli", "hepatitis", "norovirus", "clostridium"
    ]):
        return "High"
    if any(w in t for w in [
        "traceability", "fraud", "origin", "residue",
        "pesticide", "migration", "heavy metal"
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
            "url": "https://webgate.ec.europa.eu/rasff-window/screen/list",
            "notification_reference": "n/a",
            "source_status": "fallback",
            "fetch_method": "fallback",
            "last_verified": now_str,
        }
    ]


def fetch_rasff_updates(limit=10):
    try:
        payload = {
            "pageNumber": 1,
            "itemsPerPage": limit,
            "ordering": {
                "field": "notificationDate",
                "direction": "DESC"
            }
        }

        session = requests.Session()
        session.headers.update(HEADERS)

        response = session.post(
            RASFF_API_URL,
            json=payload,
            timeout=25
        )
        response.raise_for_status()

        data = response.json()

        notifications = (
            data.get("notifications", [])
            or data.get("content", [])
            or data.get("results", [])
            or []
        )

        if not notifications:
            print("[RASFF] API returned empty notifications")
            return fallback_rasff_examples()

        results = []
        for i, notif in enumerate(notifications[:limit]):
            reference = str(
                notif.get("reference", "")
                or notif.get("notificationReference", "")
                or f"unknown-{i}"
            )
            subject = str(
                notif.get("subject", "")
                or notif.get("title", "")
                or "RASFF Notification"
            )
            notif_type = str(notif.get("notificationType", "") or "")
            category = str(notif.get("category", "") or "")

            date_raw = str(
                notif.get("notificationDate", "")
                or notif.get("date", "")
                or ""
            )
            try:
                date_str = date_raw[:10] if len(date_raw) >= 10 else datetime.utcnow().strftime("%Y-%m-%d")
            except Exception:
                date_str = datetime.utcnow().strftime("%Y-%m-%d")

            combined_text = f"{subject} {category} {notif_type}"
            topic = detect_topic(combined_text)
            risk = detect_risk(combined_text)

            detail_url = f"https://webgate.ec.europa.eu/rasff-window/screen/notification/{reference}"

            if risk == "High":
                impact = "May require immediate compliance escalation or product containment."
                action = "Assess exposure and review supplier controls."
            elif risk == "Medium":
                impact = "May affect documentation, traceability, or labeling."
                action = "Review internal records."
            else:
                impact = "Lower urgency but relevant for compliance review."
                action = "Monitor developments."

            title = f"{notif_type}: {subject}".strip(": ") if notif_type else subject

            results.append({
                "id": f"rasff-{reference}",
                "title": title,
                "source": "RASFF",
                "date": date_str,
                "jurisdiction": "EU",
                "topic": topic,
                "risk_level": risk,
                "ai_summary": subject,
                "business_impact": impact,
                "recommended_action": action,
                "raw_text": combined_text,
                "url": detail_url,
                "notification_reference": reference,
                "source_status": "live",
                "fetch_method": "rasff_api",
                "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            })

        print(f"[RASFF] Fetched {len(results)} live items")
        return results if results else fallback_rasff_examples()

    except Exception as e:
        print(f"[RASFF] Error: {e}")
        return fallback_rasff_examples()
