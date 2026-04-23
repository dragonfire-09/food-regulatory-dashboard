import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

RASFF_API_URL = "https://webgate.ec.europa.eu/rasff-window/backend/shared/notifications"
RASFF_DETAIL_BASE = "https://webgate.ec.europa.eu/rasff-window/screen/notification"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FoodRegDashboard/1.0)"}


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
    if any(w in t for w in ["salmonella", "listeria", "contamination", "undeclared allergen", "recall", "aflatoxin"]):
        return "High"
    if any(w in t for w in ["traceability", "fraud", "origin", "residue", "pesticide"]):
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
            "ai_summary": "RASFF live data could not be fetched. Showing fallback.",
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


def fetch_rasff_updates(limit=5):
    """RASFF backend API'den canlı bildirim çeker."""
    try:
        params = {
            "searcher": "notification",
            "pageSize": str(limit),
            "page": "1",
            "notificationStatus": "OPEN",
            "ordering": "notificationDate=DESC",
        }

        session = requests.Session()
        session.headers.update(HEADERS)

        response = session.get(RASFF_API_URL, params=params, timeout=20)
        response.raise_for_status()

        data = response.json()
        notifications = data.get("notifications", data.get("content", []))

        if not notifications:
            return fallback_rasff_examples()

        results = []
        for i, notif in enumerate(notifications[:limit]):
            # API alanlarını oku
            reference = notif.get("reference", f"rasff-{i}")
            subject = notif.get("subject", "RASFF Notification")
            notif_type = notif.get("notificationType", "")
            category = notif.get("category", "")
            date_raw = notif.get("notificationDate", "")
            country = notif.get("notifyingCountry", "EU")

            # Tarih
            try:
                if "T" in str(date_raw):
                    date_str = date_raw[:10]
                else:
                    date_str = str(date_raw)[:10]
            except Exception:
                date_str = datetime.utcnow().strftime("%Y-%m-%d")

            combined_text = f"{subject} {category} {notif_type}"
            topic = detect_topic(combined_text)
            risk = detect_risk(combined_text)

            detail_url = f"{RASFF_DETAIL_BASE}/{reference}"

            if risk == "High":
                impact = "This may require immediate compliance escalation, supplier review, or product containment."
                action = "Assess exposure, review supplier controls, and determine whether market action is needed."
            elif risk == "Medium":
                impact = "This may affect documentation, traceability, labeling, or commercial claims."
                action = "Review internal records and identify whether teams need to respond."
            else:
                impact = "Lower urgency but may still be relevant for compliance review."
                action = "Monitor developments and document relevance."

            results.append({
                "id": f"rasff-{reference}",
                "title": f"{notif_type}: {subject}" if notif_type else subject,
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

        return results if results else fallback_rasff_examples()

    except Exception:
        return fallback_rasff_examples()
