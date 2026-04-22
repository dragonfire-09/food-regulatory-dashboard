import feedparser

def fetch_efsa_updates():
    url = "https://www.efsa.europa.eu/en/press/rss"
    feed = feedparser.parse(url)

    results = []

    for i, entry in enumerate(feed.entries[:10]):
        results.append({
            "title": entry.title,
            "source": "EFSA",
            "date": entry.published[:10],
            "topic": "Food Safety",
            "risk_level": "Medium",
            "ai_summary": entry.summary,
            "business_impact": "Regulatory relevance for EU food businesses",
            "recommended_action": "Review update and assess impact"
        })

    return results
