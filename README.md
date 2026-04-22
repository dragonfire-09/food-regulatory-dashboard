
# Food Regulatory Intelligence Dashboard

A Streamlit-based prototype for **food law, compliance, and supply chain intelligence**.  
The platform combines live and structured regulatory updates into a clean interface designed for:

- regulatory horizon scanning
- compliance monitoring
- food safety intelligence
- traceability and supply chain review
- client-facing alert generation

## Overview

This project was built as a prototype for an **AI-powered regulatory intelligence layer** in the food and agrifood sector.

It aggregates updates from:

- **EFSA** (European Food Safety Authority)
- **RASFF** (Rapid Alert System for Food and Feed)

and presents them in a structured dashboard with:

- filtering by source, topic, and risk
- local / optional AI-style enrichment
- downloadable client alerts in **TXT** and **PDF**
- visual risk prioritization
- live refresh functionality

## Key Features

### 1. Regulatory Monitoring Dashboard
A professional dashboard interface for reviewing regulatory updates in a structured way.

### 2. Live Feed Integration
- **EFSA** updates are pulled from live RSS
- **RASFF** uses a live-access parsing layer with controlled fallback records for prototyping continuity

### 3. Risk-Based Prioritization
Updates are categorized visually by risk level:

- **High**
- **Medium**
- **Low**

### 4. Structured Intelligence Output
Each update includes:
- AI Summary
- Business Impact
- Recommended Action

### 5. Downloadable Client Alerts
Each item can generate:
- `.txt` client alert
- `.pdf` client alert

### 6. Cost-Efficient AI Architecture
The current version supports:
- **local fallback enrichment** for no-cost prototyping
- optional **OpenAI integration** for real LLM-based summarization

## Tech Stack

- **Python**
- **Streamlit**
- **Pandas**
- **Requests**
- **BeautifulSoup**
- **Feedparser**
- **ReportLab**
- **OpenAI SDK** (optional)

## Project Structure

```text
food-regulatory-dashboard/
├── app.py
├── requirements.txt
├── README.md
├── data/
│   ├── regulatory_data.json
│   └── live_updates.json
└── scrapers/
    ├── efsa_rss_scraper.py
    └── rasff_scraper.py

Installation

Clone the repository:
python -m venv .venv
.venv\Scripts\activate
Create a virtual environment:

Windows
python -m venv .venv
.venv\Scripts\activate

macOS / Linux
python -m venv .venv
source .venv/bin/activate

Install dependencies:
pip install -r requirements.txt

Run locally:
streamlit run app.py

Optional OpenAI Integration

The app works without paid AI usage, thanks to the built-in local enrichment layer.

If you want to enable OpenAI-based re-summarization later, add this to Streamlit secrets:

OPENAI_API_KEY = "your_openai_api_key"

How the Current AI Layer Works

This prototype is designed to remain functional even without external AI API usage.

Current mode:
If OpenAI is available → real AI-based summary generation
If OpenAI is unavailable or quota is missing → local rule-based fallback enrichment

This ensures:

lower prototyping cost
stable demo behavior
no broken user experience
Example Use Cases
Regulatory intelligence support for food businesses
Client alert generation for consultants
Horizon scanning workflows
Internal compliance review
Supply chain and traceability risk monitoring
Prototype Positioning

This is not just a dashboard.
It is a prototype for a broader RegTech / food compliance intelligence platform.

Potential future extensions:

client-specific alerting
PDF briefing packs
email delivery
user authentication
jurisdiction-specific intelligence streams
database-backed regulatory memory
full LLM enrichment pipeline
Notes
EFSA integration is based on live RSS feeds
RASFF integration uses a pragmatic prototype approach with controlled fallback behavior
The project prioritizes interface continuity, clarity, and decision-support value
Author

Mehmet Cam

License

This project is for prototype and demonstration purposes.
