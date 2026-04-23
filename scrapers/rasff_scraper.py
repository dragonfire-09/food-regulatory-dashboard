import requests
from datetime import datetime

RASFF_API_URL = "https://webgate.ec.europa.eu/rasff-window/backend/shared/notifications"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FoodRegDashboard/1.0)",
    "Accept": "application/json",
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
        "e. coli", "hepatitis", "norovirus"
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
    """RASFF backend API'den bildirim çeker - birden fazla endpoint dener."""
    import sys

    endpoints = [
        {
            "name": "GET notifications",
            "method": "GET",
            "url": "https://webgate.ec.europa.eu/rasff-window/backend/shared/notifications",
            "params": {"pageSize": str(limit), "page": "1"},
            "json_body": None,
        },
        {
            "name": "POST search",
            "method": "POST",
            "url": "https://webgate.ec.europa.eu/rasff-window/backend/shared/notifications/search",
            "params": None,
            "json_body": {"pageNumber": 1, "itemsPerPage": limit},
        },
        {
            "name": "GET list",
            "method": "GET",
            "url": "https://webgate.ec.europa.eu/rasff-window/backend/shared/notifications/list",
            "params": {"pageSize": str(limit)},
            "json_body": None,
        },
        {
            "name": "POST consolidated",
            "method": "POST",
            "url": "https://webgate.ec.europa.eu/rasff-window/backend/shared/notifications/search/consolidated",
            "params": None,
            "json_body": {"pageNumber": 1, "itemsPerPage": limit},
        },
    ]

    session = requests.Session()
    session.headers.update(HEADERS)

    for ep in endpoints:
        try:
            sys.stderr.write(f"[RASFF] Trying: {ep['name']} -> {ep['url']}\n")
            sys.stderr.flush()

            if ep["method"] == "GET":
                resp = session.get(ep["url"], params=ep["params"], timeout=20)
            else:
                resp = session.post(
                    ep["url"],
                    json=ep["json_body"],
                    headers={"Content-Type": "application/json"},
                    timeout=20,
                )

            sys.stderr.write(f"[RASFF] {ep['name']} status: {resp.status_code}\n")
            sys.stderr.flush()

            if resp.status_code != 200:
                continue

            # JSON parse dene
            try:
                data = resp.json()
            except Exception:
                sys.stderr.write(f"[RASFF] {ep['name']} not JSON\n")
                sys.stderr.flush()
                continue

            # Bildirimleri bul
            notifications = []
            if isinstance(data, list):
                notifications = data
            elif isinstance(data, dict):
                for key in ["notifications", "content", "results", "data", "items"]:
                    if key in data and isinstance(data[key], list):
                        notifications = data[key]
                        break

            sys.stderr.write(f"[RASFF] {ep['name']} found {len(notifications)} items\n")
            sys.stderr.flush()

            if not notifications:
                continue

            # Parse et
            results = []
            for i, notif in enumerate(notifications[:limit]):
                reference = str(
                    notif.get("reference", "")
                    or notif.get("notificationReference", "")
                    or notif.get("id", "")
                    or f"unknown-{i}"
                )
                subject = str(
                    notif.get("subject", "")
                    or notif.get("title", "")
                    or notif.get("description", "")
                    or "RASFF Notification"
                )
                notif_type = str(notif.get("notificationType", "") or "")
                category = str(notif.get("category", "") or "")

                date_raw = str(
                    notif.get("notificationDate", "")
                    or notif.get("date", "")
                    or notif.get("ecValidFromDate", "")
                    or ""
                )
                try:
                    date_str = date_raw[:10] if len(date_raw) >= 10 else datetime.utcnow().strftime("%Y-%m-%d")
                except Exception:
                    date_str = datetime.utcnow().strftime("%Y-%m-%d")

                combined_text = f"{subject} {category} {notif_type}"
                topic = detect_topic(combined_text)
                risk = detect_risk(combined_text)

                title = f"{notif_type}: {subject}".strip(": ") if notif_type else subject

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
                    "ai_summary": subject,
                    "business_impact": impact,
                    "recommended_action": action,
                    "raw_text": combined_text,
                    "url": f"https://webgate.ec.europa.eu/rasff-window/screen/notification/{reference}",
                    "notification_reference": reference,
                    "source_status": "live",
                    "fetch_method": "rasff_api",
                    "last_verified": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                })

            if results:
                sys.stderr.write(f"[RASFF] SUCCESS with {ep['name']}: {len(results)} items\n")
                sys.stderr.flush()
                return results

        except Exception as e:
            sys.stderr.write(f"[RASFF] {ep['name']} error: {e}\n")
            sys.stderr.flush()
            continue

    sys.stderr.write("[RASFF] All endpoints failed, using fallback\n")
    sys.stderr.flush()
    return fallback_rasff_examples()
