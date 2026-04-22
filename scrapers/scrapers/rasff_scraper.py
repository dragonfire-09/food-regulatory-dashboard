import requests
from bs4 import BeautifulSoup

def fetch_rasff_updates():
    url = "https://webgate.ec.europa.eu/rasff-window/screen/search"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")

    results = []

    for i in range(5):
        results.append({
            "title": f"RASFF Alert Example {i+1}",
            "source": "RASFF",
            "date": "2026-03-01",
            "topic": "Contaminants",
            "risk_level": "High",
            "ai_summary": "Example contamination alert",
            "business_impact": "Potential recall risk",
            "recommended_action": "Investigate supply chain"
        })

    return results
