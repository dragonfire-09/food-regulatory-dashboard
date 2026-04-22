import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from io import BytesIO

import plotly.express as px
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from scrapers.efsa_rss_scraper import fetch_efsa_updates
from scrapers.rasff_scraper import fetch_rasff_updates

st.set_page_config(
    page_title="Food Regulatory Intelligence Dashboard",
    page_icon="📋",
    layout="wide",
)

DATA_DIR = Path("data")
BASE_DATA_FILE = DATA_DIR / "regulatory_data.json"
LIVE_DATA_FILE = DATA_DIR / "live_updates.json"

OPENROUTER_MODELS = [
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
]


# ---------- OPENROUTER ----------
def get_openrouter_client():
    try:
        api_key = st.secrets.get("OPENROUTER_API_KEY", None)
    except Exception:
        api_key = None

    if not api_key or OpenAI is None:
        return None

    try:
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    except Exception:
        return None


# ---------- CSS ----------
st.markdown("""
<style>
    .main {
        background-color: #f7f9fc;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1280px;
    }

    .hero-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        padding: 1.6rem 1.6rem 1.3rem 1.6rem;
        border-radius: 20px;
        color: white;
        margin-bottom: 1.3rem;
        box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
    }

    .hero-title {
        font-size: 2rem;
        font-weight: 800;
        margin-bottom: 0.25rem;
        line-height: 1.2;
    }

    .hero-subtitle {
        font-size: 1rem;
        color: #dbeafe;
        margin-bottom: 0.45rem;
        line-height: 1.5;
    }

    .small-note {
        font-size: 0.84rem;
        color: #cbd5e1;
        margin-bottom: 0;
    }

    .intro-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 14px;
        margin-bottom: 1rem;
    }

    .intro-card {
        background: white;
        border-radius: 18px;
        padding: 1rem 1.1rem;
        border: 1px solid #e5e7eb;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
    }

    .intro-title {
        font-size: 0.95rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.35rem;
    }

    .intro-text {
        font-size: 0.92rem;
        color: #334155;
        line-height: 1.55;
    }

    .metric-card {
        background: white;
        border-radius: 18px;
        padding: 1rem 1.1rem;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
        border: 1px solid #e5e7eb;
        margin-bottom: 0.8rem;
    }

    .metric-label {
        font-size: 0.88rem;
        color: #64748b;
        margin-bottom: 0.15rem;
    }

    .metric-value {
        font-size: 1.7rem;
        font-weight: 800;
        color: #0f172a;
    }

    .section-title {
        font-size: 1.15rem;
        font-weight: 800;
        color: #0f172a;
        margin-top: 1.1rem;
        margin-bottom: 0.9rem;
    }

    .update-card {
        background: white;
        border-radius: 20px;
        padding: 1.2rem 1.2rem 1rem 1.2rem;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        border: 1px solid #e5e7eb;
        margin-bottom: 1rem;
    }

    .urgent-card {
        background: white;
        border-radius: 18px;
        padding: 1rem 1rem 0.9rem 1rem;
        border: 1px solid #e5e7eb;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
        margin-bottom: 0.8rem;
    }

    .urgent-title {
        font-size: 1rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.35rem;
    }

    .urgent-meta {
        font-size: 0.85rem;
        color: #64748b;
        margin-bottom: 0.35rem;
    }

    .update-title {
        font-size: 1.18rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.5rem;
        line-height: 1.35;
    }

    .meta-row {
        font-size: 0.9rem;
        color: #64748b;
        margin-bottom: 0.85rem;
    }

    .pill {
        display: inline-block;
        padding: 0.30rem 0.70rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-right: 0.42rem;
        margin-bottom: 0.4rem;
    }

    .pill-topic {
        background: #e0f2fe;
        color: #0369a1;
    }

    .pill-source {
        background: #eef2ff;
        color: #4338ca;
    }

    .pill-risk-high {
        background: #fee2e2;
        color: #b91c1c;
    }

    .pill-risk-medium {
        background: #ffedd5;
        color: #c2410c;
    }

    .pill-risk-low {
        background: #dcfce7;
        color: #15803d;
    }

    .pill-priority-immediate {
        background: #fee2e2;
        color: #991b1b;
    }

    .pill-priority-review {
        background: #fef3c7;
        color: #92400e;
    }

    .pill-priority-monitor {
        background: #dbeafe;
        color: #1d4ed8;
    }

    .subblock-title {
        font-size: 0.92rem;
        font-weight: 800;
        color: #334155;
        margin-top: 0.85rem;
        margin-bottom: 0.2rem;
    }

    .subblock-text {
        font-size: 0.97rem;
        color: #0f172a;
        line-height: 1.58;
    }

    .high-risk {
        border-left: 6px solid #dc2626 !important;
    }

    .medium-risk {
        border-left: 6px solid #f97316 !important;
    }

    .low-risk {
        border-left: 6px solid #16a34a !important;
    }

    .report-box {
        background: #ffffff;
        border-radius: 18px;
        padding: 1rem 1.1rem;
        border: 1px solid #e5e7eb;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
        margin-bottom: 1rem;
    }

    .insight-box {
        background: #ffffff;
        border-radius: 18px;
        padding: 1rem 1.1rem;
        border: 1px solid #e5e7eb;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
        margin-bottom: 1rem;
    }

    .stButton button {
        border-radius: 12px;
        border: 1px solid #dbeafe;
        background: white;
        color: #0f172a;
        font-weight: 700;
    }

    .stDownloadButton button {
        border-radius: 12px;
        font-weight: 700;
    }

    .stSidebar {
        background-color: #f8fafc;
    }
</style>
""", unsafe_allow_html=True)


# ---------- FILE HELPERS ----------
def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json_records(path: Path):
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_json_records(path: Path, records):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def refresh_live_data():
    efsa_items = fetch_efsa_updates()
    rasff_items = fetch_rasff_updates()
    live_items = efsa_items + rasff_items
    save_json_records(LIVE_DATA_FILE, live_items)
    return live_items


def combine_data():
    base_records = load_json_records(BASE_DATA_FILE)
    live_records = load_json_records(LIVE_DATA_FILE)
    all_records = live_records + base_records

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return df.sort_values("date", ascending=False, na_position="last")


# ---------- DISPLAY HELPERS ----------
def risk_class(level: str):
    level = str(level).strip().lower()
    if level == "high":
        return "pill pill-risk-high", "High"
    if level == "medium":
        return "pill pill-risk-medium", "Medium"
    return "pill pill-risk-low", "Low"


def card_risk_class(level: str):
    level = str(level).strip().lower()
    if level == "high":
        return "high-risk"
    if level == "medium":
        return "medium-risk"
    return "low-risk"


def priority_class(priority: str):
    p = priority.lower()
    if p == "immediate":
        return "pill pill-priority-immediate"
    if p == "review":
        return "pill pill-priority-review"
    return "pill pill-priority-monitor"


def format_date(value):
    if pd.isna(value):
        return "Unknown date"
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def wrap_text(text: str, max_chars: int = 95):
    if not text:
        return [""]
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) <= max_chars:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def build_pdf_bytes(title: str, content: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4

    x = 50
    y = height - 50

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(x, y, title)
    y -= 30

    pdf.setFont("Helvetica", 10)
    for line in content.splitlines():
        for wrapped_line in wrap_text(line, 95):
            if y < 60:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = height - 50
            pdf.drawString(x, y, wrapped_line)
            y -= 14

    pdf.save()
    buffer.seek(0)
    return buffer.read()


def sanitize_filename(value: str) -> str:
    value = value.lower().strip()
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        value = value.replace(ch, "-")
    value = value.replace(" ", "_")
    return value[:80]


# ---------- CONSULTING LOGIC ----------
def calculate_impact_score(row, client_type):
    score = 0

    risk = str(row.get("risk_level", "Low")).lower()
    topic = str(row.get("topic", "")).lower()
    title = str(row.get("title", "")).lower()
    source = str(row.get("source", "")).lower()

    if risk == "high":
        score += 5
    elif risk == "medium":
        score += 3
    else:
        score += 1

    if topic in ["contaminants", "labeling", "traceability", "fraud"]:
        score += 3
    elif topic in ["novel foods", "food safety"]:
        score += 2

    if "rasff" in source:
        score += 2

    if any(word in title for word in ["recall", "salmonella", "allergen", "listeria"]):
        score += 2

    if client_type == "Exporter":
        if topic in ["labeling", "contaminants", "traceability"]:
            score += 2
    elif client_type == "Retailer":
        if topic in ["labeling", "fraud", "contaminants"]:
            score += 2
    elif client_type == "Importer":
        if topic in ["traceability", "contaminants", "fraud"]:
            score += 2
    elif client_type == "SME Food Producer":
        if topic in ["labeling", "food safety", "novel foods"]:
            score += 2
    elif client_type == "Startup":
        if topic in ["novel foods", "labeling"]:
            score += 2

    return min(score, 10)


def determine_priority(score):
    if score >= 8:
        return "Immediate"
    if score >= 5:
        return "Review"
    return "Monitor"


def why_this_matters(row, client_type):
    topic = str(row.get("topic", "Food Safety"))
    risk = str(row.get("risk_level", "Medium")).lower()

    if client_type == "Exporter":
        if topic == "Labeling":
            return "This may affect export labeling compliance, destination-market documentation, and shipment readiness."
        if topic == "Contaminants":
            return "This may affect border acceptance, product testing exposure, and supplier risk in export channels."
        if topic == "Traceability":
            return "This may affect documentation continuity across jurisdictions and importer confidence."
    elif client_type == "Retailer":
        if topic == "Labeling":
            return "This may affect on-shelf compliance, consumer information accuracy, and private-label exposure."
        if topic == "Fraud":
            return "This may affect brand integrity, product claims, and supplier verification requirements."
        if topic == "Contaminants":
            return "This may increase recall risk and require rapid coordination with suppliers and QA teams."
    elif client_type == "Importer":
        if topic == "Traceability":
            return "This may affect inbound documentation quality and product release decisions."
        if topic == "Contaminants":
            return "This may increase batch-hold, testing, and customs-related review requirements."
    elif client_type == "Startup":
        if topic == "Novel Foods":
            return "This may shape market-entry timing, product claims, and commercialization planning."
        if topic == "Labeling":
            return "This may affect packaging design and compliance assumptions in early-stage go-to-market work."
    elif client_type == "SME Food Producer":
        if topic == "Labeling":
            return "This may require packaging review, internal sign-off changes, and updated label controls."
        if topic == "Food Safety":
            return "This may affect QA workflows, specifications, and operational risk exposure."

    if risk == "high":
        return "This looks commercially material and may require immediate cross-functional review."
    if risk == "low":
        return "This is lower urgency but still useful for horizon scanning and future planning."
    return "This may affect compliance planning, supply chain review, and internal decision-making."


def client_adjusted_action(base_action, client_type, topic, priority):
    if client_type == "Exporter":
        extra = "Check destination-country implications, export documentation, and border-related exposure."
    elif client_type == "Retailer":
        extra = "Assess shelf impact, supplier exposure, and any recall or customer-facing implications."
    elif client_type == "Importer":
        extra = "Review supplier documentation, inbound controls, and traceability completeness."
    elif client_type == "Startup":
        extra = "Assess product-market fit implications, packaging assumptions, and authorization timing."
    else:
        extra = "Review internal QA, regulatory, and production implications."

    return f"{base_action} {extra}"


def build_client_alert(row, client_type, impact_score, priority, why_matters):
    title = row.get("title", "Regulatory Update")
    ai_summary = row.get("ai_summary", "No summary available.")
    impact = row.get("business_impact", "No business impact available.")
    action = row.get("recommended_action", "No recommended action available.")
    source = row.get("source", "Unknown source")
    date_str = format_date(row.get("date", None))
    topic = row.get("topic", "Unknown")

    return f"""Subject: Regulatory Update – {title}

Client Type: {client_type}
Source: {source}
Date: {date_str}
Topic: {topic}
Impact Score: {impact_score}/10
Priority: {priority}

Summary:
{ai_summary}

Why this matters:
{why_matters}

Business Impact:
{impact}

Recommended Action:
{action}
"""


# ---------- LOCAL FALLBACK ----------
def local_ai_fallback(row, client_type):
    title = str(row.get("title", "Regulatory update"))
    topic = str(row.get("topic", "Food Safety"))
    source = str(row.get("source", "Regulatory source"))
    risk = str(row.get("risk_level", "Medium")).lower()
    raw_text = str(row.get("raw_text", ""))
    existing_summary = str(row.get("ai_summary", ""))

    base_summary = existing_summary if existing_summary else f"This update relates to {topic.lower()} and may require compliance review."

    title_lower = title.lower()
    topic_lower = topic.lower()
    raw_lower = raw_text.lower()

    if "label" in title_lower or "label" in topic_lower:
        impact = "Food businesses may need to review packaging, declarations, and label approval workflows."
        action = "Review current labels, compare them against the update, and prepare packaging revisions if needed."
    elif "traceability" in title_lower or "traceability" in topic_lower:
        impact = "Operators may need stronger product tracking, recordkeeping, and data coordination across the supply chain."
        action = "Assess traceability records, supplier data quality, and system readiness for compliance checks."
    elif "contaminant" in title_lower or "salmonella" in raw_lower or "pesticide" in raw_lower:
        impact = "There may be increased recall exposure, supplier scrutiny, and regulatory risk for affected categories."
        action = "Check affected products or batches, review supplier controls, and prepare a targeted risk assessment."
    elif "fraud" in title_lower:
        impact = "Authentication, origin claims, and documentary controls may face closer regulatory scrutiny."
        action = "Review provenance records, product claims, and internal controls for documentation gaps."
    elif "novel" in title_lower or "novel" in topic_lower:
        impact = "This may create opportunities for product development, but authorization and market-entry timing should be assessed carefully."
        action = "Review eligibility, product formulation, and approval timing before commercialization planning."
    else:
        impact = "This update may affect compliance planning, internal review processes, and market-facing documentation."
        action = "Review the update internally and determine whether legal, quality, or supply chain teams need to respond."

    if risk == "high":
        impact = "This appears commercially significant and may require immediate compliance escalation, supplier review, or market action."
        action = "Prioritize immediate internal review, identify affected products or partners, and prepare a rapid response plan."
    elif risk == "low":
        impact = "This appears lower urgency but may still be relevant for horizon scanning and future compliance planning."
        action = "Log the update, monitor developments, and review relevance during the next compliance cycle."

    action = client_adjusted_action(action, client_type, topic, "Review")

    return {
        "ai_summary": f"{base_summary} Source: {source}.",
        "business_impact": impact,
        "recommended_action": action,
        "_model_used": "local fallback",
    }


# ---------- JSON EXTRACTION ----------
def extract_json_block(text: str):
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        return json.loads(candidate)

    raise ValueError("No valid JSON found")


# ---------- OPENROUTER AI ----------
def try_openrouter_model(client, model_name, prompt):
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a food regulatory intelligence analyst."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


def generate_ai_analysis(row, client_type):
    client = get_openrouter_client()

    if client is None:
        return local_ai_fallback(row, client_type)

    title = row.get("title", "")
    source = row.get("source", "")
    topic = row.get("topic", "")
    jurisdiction = row.get("jurisdiction", "")
    raw_text = row.get("raw_text", "")
    existing_summary = row.get("ai_summary", "")

    prompt = f"""
You are a food regulatory intelligence analyst.

Task:
Analyze the regulatory update below for the specified client type.

Return output as VALID JSON ONLY.

Required JSON schema:
{{
  "ai_summary": "string",
  "business_impact": "string",
  "recommended_action": "string"
}}

Rules:
- Output must be valid JSON.
- Do not add markdown.
- Do not use code fences.
- Do not add any text before or after the JSON.
- Keep each value concise, clear, and professional.
- Tailor the analysis to this client type: {client_type}.
- Focus on compliance, supply chain, commercial relevance, and practical next steps.

Update:
Title: {title}
Source: {source}
Topic: {topic}
Jurisdiction: {jurisdiction}
Existing summary: {existing_summary}
Raw text: {raw_text}
"""

    for model_name in OPENROUTER_MODELS:
        try:
            text = try_openrouter_model(client, model_name, prompt)
            parsed = extract_json_block(text)
            return {
                "ai_summary": parsed.get("ai_summary", existing_summary or "No summary available."),
                "business_impact": parsed.get("business_impact", "No business impact available."),
                "recommended_action": parsed.get("recommended_action", "No recommended action available."),
                "_model_used": model_name,
            }
        except Exception:
            continue

    return local_ai_fallback(row, client_type)


# ---------- REPORTS ----------
def generate_weekly_report(df, client_type):
    if df.empty:
        return "No updates available for the selected filters."

    report_df = df.copy().sort_values("impact_score", ascending=False)
    top_items = report_df.head(5)

    lines = []
    lines.append("WEEKLY REGULATORY INTELLIGENCE REPORT")
    lines.append("")
    lines.append(f"Client Type: {client_type}")
    lines.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append(f"Updates reviewed: {len(report_df)}")
    lines.append("")
    lines.append("EXECUTIVE SUMMARY")
    lines.append(f"- Immediate priority items: {(report_df['priority'] == 'Immediate').sum()}")
    lines.append(f"- Review items: {(report_df['priority'] == 'Review').sum()}")
    lines.append(f"- Monitor items: {(report_df['priority'] == 'Monitor').sum()}")
    lines.append("")
    lines.append("TOP PRIORITY UPDATES")

    for i, (_, row) in enumerate(top_items.iterrows(), start=1):
        lines.append(f"{i}. {row.get('title', 'Untitled')}")
        lines.append(f"   Source: {row.get('source', 'Unknown')} | Date: {format_date(row.get('date'))}")
        lines.append(f"   Topic: {row.get('topic', 'Unknown')} | Score: {row.get('impact_score', 0)}/10 | Priority: {row.get('priority', 'Monitor')}")
        lines.append(f"   Why this matters: {row.get('why_this_matters', '')}")
        lines.append(f"   Recommended action: {row.get('recommended_action', '')}")
        lines.append("")

    lines.append("CONSULTING VIEW")
    lines.append("This report translates regulatory updates into prioritized decision-support outputs tailored to client type.")
    return "\n".join(lines)


def build_full_report(df, client_type):
    if df.empty:
        return "No data available."

    df = df.sort_values("impact_score", ascending=False)

    lines = []
    lines.append("FOOD REGULATORY INTELLIGENCE REPORT")
    lines.append("")
    lines.append(f"Client Type: {client_type}")
    lines.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append(f"Total updates: {len(df)}")
    lines.append("")
    lines.append("EXECUTIVE SUMMARY")
    lines.append(f"- Immediate: {(df['priority'] == 'Immediate').sum()}")
    lines.append(f"- Review: {(df['priority'] == 'Review').sum()}")
    lines.append(f"- Monitor: {(df['priority'] == 'Monitor').sum()}")
    lines.append("")

    lines.append("TOP PRIORITY ITEMS")
    top = df.head(5)
    for i, (_, row) in enumerate(top.iterrows(), 1):
        lines.append(f"{i}. {row['title']}")
        lines.append(f"   Score: {row['impact_score']}/10 | Priority: {row['priority']}")
        lines.append(f"   Why: {row['why_this_matters']}")
        lines.append("")

    lines.append("FULL REGULATORY LIST")
    for _, row in df.iterrows():
        lines.append(f"- {row['title']}")
        lines.append(f"  Source: {row['source']} | Date: {format_date(row['date'])}")
        lines.append(f"  Priority: {row['priority']} | Score: {row['impact_score']}/10")
        lines.append(f"  Action: {row['recommended_action']}")
        lines.append("")

    return "\n".join(lines)


def generate_client_insights(df, client_type):
    if df.empty:
        return {
            "headline": "No updates available for the selected filters.",
            "key_risk": "No key risk detected.",
            "operational_focus": "No operational focus available.",
            "recommended_next_step": "Refresh data or broaden filters."
        }

    sorted_df = df.sort_values("impact_score", ascending=False)
    top_row = sorted_df.iloc[0]
    top_topic = sorted_df["topic"].mode().iloc[0] if "topic" in sorted_df.columns and not sorted_df["topic"].mode().empty else "Food Safety"

    immediate_count = (sorted_df["priority"] == "Immediate").sum()
    high_risk_count = (sorted_df["risk_level"].astype(str).str.lower() == "high").sum()

    headline = (
        f"For {client_type.lower()}s, the current regulatory picture suggests "
        f"{immediate_count} immediate-priority item(s) and {high_risk_count} high-risk update(s), "
        f"with the strongest concentration around {top_topic.lower()}."
    )

    if client_type == "Exporter":
        operational_focus = "Border-facing documentation, destination-market compliance, and supplier risk visibility should be reviewed first."
    elif client_type == "Retailer":
        operational_focus = "Shelf compliance, supplier coordination, and consumer-facing risk exposure should be reviewed first."
    elif client_type == "Importer":
        operational_focus = "Inbound controls, traceability completeness, and batch-level documentation should be reviewed first."
    elif client_type == "Startup":
        operational_focus = "Packaging assumptions, market-entry timing, and regulatory readiness should be reviewed first."
    else:
        operational_focus = "Internal QA, compliance review, and product documentation should be reviewed first."

    key_risk = f"The highest-impact update right now is: {top_row.get('title', 'Untitled')}."
    recommended_next_step = "Start with the top-priority item, align the affected team, and convert the alert into a short internal action note."

    return {
        "headline": headline,
        "key_risk": key_risk,
        "operational_focus": operational_focus,
        "recommended_next_step": recommended_next_step
    }


# ---------- ANALYTICS ----------
def build_analytics_frames(df):
    frames = {}

    if df.empty:
        return frames

    work = df.copy()

    if "date" in work.columns:
        work["date_only"] = pd.to_datetime(work["date"], errors="coerce").dt.date

    if "source" in work.columns:
        frames["source_counts"] = work["source"].value_counts().reset_index()
        frames["source_counts"].columns = ["source", "count"]

    if "topic" in work.columns:
        frames["topic_counts"] = work["topic"].value_counts().reset_index()
        frames["topic_counts"].columns = ["topic", "count"]

    if "priority" in work.columns:
        frames["priority_counts"] = work["priority"].value_counts().reset_index()
        frames["priority_counts"].columns = ["priority", "count"]

    if "risk_level" in work.columns:
        frames["risk_counts"] = work["risk_level"].astype(str).str.title().value_counts().reset_index()
        frames["risk_counts"].columns = ["risk_level", "count"]

    if "date_only" in work.columns:
        trend = work.groupby("date_only").size().reset_index(name="count")
        trend["date_only"] = pd.to_datetime(trend["date_only"])
        frames["trend"] = trend.sort_values("date_only")

    if "impact_score" in work.columns:
        frames["score_by_topic"] = work.groupby("topic", dropna=False)["impact_score"].mean().reset_index()
        frames["score_by_topic"]["impact_score"] = frames["score_by_topic"]["impact_score"].round(2)
        frames["score_by_topic"] = frames["score_by_topic"].sort_values("impact_score", ascending=False)

        frames["score_by_source"] = work.groupby("source", dropna=False)["impact_score"].mean().reset_index()
        frames["score_by_source"]["impact_score"] = frames["score_by_source"]["impact_score"].round(2)
        frames["score_by_source"] = frames["score_by_source"].sort_values("impact_score", ascending=False)

    return frames


def render_analytics_section(df):
    st.markdown('<div class="section-title">Analytics</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No analytics available.")
        return

    frames = build_analytics_frames(df)

    c1, c2 = st.columns(2)

    if "source_counts" in frames:
        fig_source = px.bar(frames["source_counts"], x="source", y="count", title="Updates by Source")
        c1.plotly_chart(fig_source, use_container_width=True)

    if "topic_counts" in frames:
        fig_topic = px.pie(frames["topic_counts"], names="topic", values="count", title="Topic Distribution")
        c2.plotly_chart(fig_topic, use_container_width=True)

    c3, c4 = st.columns(2)

    if "priority_counts" in frames:
        fig_priority = px.bar(frames["priority_counts"], x="priority", y="count", title="Priority Distribution")
        c3.plotly_chart(fig_priority, use_container_width=True)

    if "risk_counts" in frames:
        fig_risk = px.bar(frames["risk_counts"], x="risk_level", y="count", title="Risk Distribution")
        c4.plotly_chart(fig_risk, use_container_width=True)

    if "trend" in frames and not frames["trend"].empty:
        fig_trend = px.line(frames["trend"], x="date_only", y="count", markers=True, title="Update Volume Over Time")
        st.plotly_chart(fig_trend, use_container_width=True)

    c5, c6 = st.columns(2)

    if "score_by_topic" in frames:
        fig_score_topic = px.bar(frames["score_by_topic"], x="topic", y="impact_score", title="Average Impact Score by Topic")
        c5.plotly_chart(fig_score_topic, use_container_width=True)

    if "score_by_source" in frames:
        fig_score_source = px.bar(frames["score_by_source"], x="source", y="impact_score", title="Average Impact Score by Source")
        c6.plotly_chart(fig_score_source, use_container_width=True)


# ---------- SEARCH ----------
def apply_search(df, query: str):
    if not query.strip() or df.empty:
        return df

    q = query.strip().lower()

    def row_matches(row):
        values = [
            str(row.get("title", "")),
            str(row.get("topic", "")),
            str(row.get("source", "")),
            str(row.get("ai_summary", "")),
            str(row.get("business_impact", "")),
            str(row.get("recommended_action", "")),
            str(row.get("raw_text", "")),
            str(row.get("why_this_matters", "")),
        ]
        haystack = " ".join(values).lower()
        return q in haystack

    mask = df.apply(row_matches, axis=1)
    return df[mask]


# ---------- VIEW RENDERERS ----------
def render_top_urgent_items(filtered):
    st.markdown('<div class="section-title">Top 3 Urgent Items</div>', unsafe_allow_html=True)

    if filtered.empty:
        st.info("No urgent items available.")
        return

    urgent = filtered.sort_values(["impact_score"], ascending=False).head(3)

    cols = st.columns(3)
    for i, (_, row) in enumerate(urgent.iterrows()):
        with cols[i]:
            priority_css = priority_class(row.get("priority", "Monitor"))
            st.markdown(f"""
            <div class="urgent-card">
                <div class="urgent-title">{row.get('title', 'Untitled')}</div>
                <div class="urgent-meta">Source: {row.get('source', 'Unknown')} | Date: {format_date(row.get('date'))}</div>
                <span class="{priority_css}">{row.get('priority', 'Monitor')}</span>
                <span class="pill pill-topic">{row.get('topic', 'Unknown')}</span>
                <div class="subblock-title">Why this matters</div>
                <div class="subblock-text">{row.get('why_this_matters', '')}</div>
            </div>
            """, unsafe_allow_html=True)


def render_overview(filtered, client_type):
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Total Updates</div>
            <div class="metric-value">{len(filtered)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        immediate_count = (filtered["priority"] == "Immediate").sum() if not filtered.empty else 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Immediate Priority</div>
            <div class="metric-value">{immediate_count}</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        avg_score = round(filtered["impact_score"].mean(), 1) if not filtered.empty else 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Avg. Impact Score</div>
            <div class="metric-value">{avg_score}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        topic_count = filtered["topic"].nunique() if "topic" in filtered.columns and not filtered.empty else 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Topics</div>
            <div class="metric-value">{topic_count}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Client-Specific Insights</div>', unsafe_allow_html=True)
    insights = generate_client_insights(filtered, client_type)

    st.markdown('<div class="insight-box">', unsafe_allow_html=True)
    st.markdown(f"**Headline**  \n{insights['headline']}")
    st.markdown(f"**Key Risk**  \n{insights['key_risk']}")
    st.markdown(f"**Operational Focus**  \n{insights['operational_focus']}")
    st.markdown(f"**Recommended Next Step**  \n{insights['recommended_next_step']}")
    st.markdown('</div>', unsafe_allow_html=True)

    render_top_urgent_items(filtered)

    st.markdown('<div class="section-title">Executive Summary Preview</div>', unsafe_allow_html=True)

    top_preview = filtered.sort_values("impact_score", ascending=False).head(3) if not filtered.empty else pd.DataFrame()
    st.markdown('<div class="report-box">', unsafe_allow_html=True)
    if top_preview.empty:
        st.write("No updates available.")
    else:
        for _, row in top_preview.iterrows():
            st.write(
                f"- **{row.get('title', 'Untitled')}** | Score: {row.get('impact_score', 0)}/10 | Priority: {row.get('priority', 'Monitor')}"
            )
    st.markdown('</div>', unsafe_allow_html=True)


def render_reports(filtered, client_type):
    st.markdown('<div class="section-title">Weekly Report Generator</div>', unsafe_allow_html=True)

    weekly_report_text = generate_weekly_report(filtered, client_type)
    weekly_report_pdf = build_pdf_bytes("Weekly Regulatory Intelligence Report", weekly_report_text)

    report_col1, report_col2 = st.columns([1, 2])

    with report_col1:
        st.download_button(
            label="Download Weekly Report TXT",
            data=weekly_report_text,
            file_name=f"weekly_regulatory_report_{sanitize_filename(client_type)}.txt",
            mime="text/plain",
            key="weekly-txt",
        )
        st.download_button(
            label="Download Weekly Report PDF",
            data=weekly_report_pdf,
            file_name=f"weekly_regulatory_report_{sanitize_filename(client_type)}.pdf",
            mime="application/pdf",
            key="weekly-pdf",
        )

    with report_col2:
        top_preview = filtered.sort_values("impact_score", ascending=False).head(3) if not filtered.empty else pd.DataFrame()
        st.markdown('<div class="report-box">', unsafe_allow_html=True)
        st.markdown("**Executive Summary Preview**")
        if top_preview.empty:
            st.write("No updates available.")
        else:
            for _, row in top_preview.iterrows():
                st.write(
                    f"- **{row.get('title', 'Untitled')}** | Score: {row.get('impact_score', 0)}/10 | Priority: {row.get('priority', 'Monitor')}"
                )
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Full Intelligence Report</div>', unsafe_allow_html=True)

    full_report_text = build_full_report(filtered, client_type)
    full_report_pdf = build_pdf_bytes("Full Intelligence Report", full_report_text)

    full_col1, full_col2 = st.columns(2)

    with full_col1:
        st.download_button(
            label="Download FULL Report (TXT)",
            data=full_report_text,
            file_name=f"full_regulatory_report_{sanitize_filename(client_type)}.txt",
            mime="text/plain",
            key="full-txt",
        )

    with full_col2:
        st.download_button(
            label="Download FULL Report (PDF)",
            data=full_report_pdf,
            file_name=f"full_regulatory_report_{sanitize_filename(client_type)}.pdf",
            mime="application/pdf",
            key="full-pdf",
        )


def render_updates(filtered, client_type):
    st.markdown('<div class="section-title">Latest Regulatory Updates</div>', unsafe_allow_html=True)

    search_query = st.text_input(
        "Search updates",
        placeholder="Search by title, topic, source, summary, action, or raw text..."
    )

    updates_df = apply_search(filtered, search_query)

    st.caption(f"{len(updates_df)} update(s) shown")

    for idx, row in updates_df.iterrows():
        row_id = row.get("id", f"row-{idx}")

        if f"ai-{row_id}-{client_type}" in st.session_state:
            cached = st.session_state[f"ai-{row_id}-{client_type}"]
            ai_summary = cached["ai_summary"]
            business_impact = cached["business_impact"]
            recommended_action = cached["recommended_action"]
            model_used = cached.get("_model_used", "local fallback")
        else:
            ai_summary = row.get("ai_summary", "No summary available.")
            business_impact = row.get("business_impact", "No impact analysis available.")
            recommended_action = row.get("recommended_action", "No recommended action available.")
            model_used = "initial data"

        title = row.get("title", "Untitled")
        source = row.get("source", "Unknown")
        date_str = format_date(row.get("date", None))
        topic = row.get("topic", "Unknown")
        jurisdiction = row.get("jurisdiction", "Unknown")
        raw_text = row.get("raw_text", "")
        url = row.get("url", "")
        risk_css, risk_label = risk_class(row.get("risk_level", "Low"))
        extra_class = card_risk_class(row.get("risk_level", "Low"))
        score = row.get("impact_score", 0)
        priority = row.get("priority", "Monitor")
        why_matters = row.get("why_this_matters", "")
        priority_css = priority_class(priority)

        adjusted_action = client_adjusted_action(recommended_action, client_type, topic, priority)

        st.markdown(f"""
        <div class="update-card {extra_class}">
            <div class="update-title">{title}</div>
            <div class="meta-row">Source: {source} | Date: {date_str} | Jurisdiction: {jurisdiction}</div>
            <div>
                <span class="pill pill-source">{source}</span>
                <span class="pill pill-topic">{topic}</span>
                <span class="{risk_css}">{risk_label} Risk</span>
                <span class="{priority_css}">{priority}</span>
            </div>
            <div class="subblock-title">Impact Score</div>
            <div class="subblock-text">{score}/10</div>
            <div class="subblock-title">AI Summary</div>
            <div class="subblock-text">{ai_summary}</div>
            <div class="subblock-title">Why this matters</div>
            <div class="subblock-text">{why_matters}</div>
            <div class="subblock-title">Business Impact</div>
            <div class="subblock-text">{business_impact}</div>
            <div class="subblock-title">Recommended Action</div>
            <div class="subblock-text">{adjusted_action}</div>
            <div class="subblock-title">Model Used</div>
            <div class="subblock-text">{model_used}</div>
        </div>
        """, unsafe_allow_html=True)

        enriched_row = {
            **row.to_dict(),
            "ai_summary": ai_summary,
            "business_impact": business_impact,
            "recommended_action": adjusted_action,
        }

        alert_text = build_client_alert(enriched_row, client_type, score, priority, why_matters)
        safe_name = sanitize_filename(title)
        pdf_bytes = build_pdf_bytes(
            title=f"Client Alert - {title}",
            content=alert_text,
        )

        col1, col2, col3 = st.columns([1, 1, 1])

        with col1:
            if st.button("AI Re-Summarize", key=f"ai-btn-{row_id}-{client_type}"):
                with st.spinner("Generating updated analysis..."):
                    enriched = generate_ai_analysis(row, client_type)
                    st.session_state[f"ai-{row_id}-{client_type}"] = enriched
                    st.rerun()

        with col2:
            st.download_button(
                label="Download TXT",
                data=alert_text,
                file_name=f"{safe_name}_client_alert.txt",
                mime="text/plain",
                key=f"txt-{row_id}-{client_type}",
            )

        with col3:
            st.download_button(
                label="Download PDF",
                data=pdf_bytes,
                file_name=f"{safe_name}_client_alert.pdf",
                mime="application/pdf",
                key=f"pdf-{row_id}-{client_type}",
            )

        if url:
            st.markdown(f"[Open source item]({url})")

        with st.expander("Show raw text"):
            st.write(raw_text if raw_text else "No raw text available.")


# ---------- APP ----------
ensure_data_dir()
df = combine_data()

with st.sidebar:
    st.markdown("## Controls")

    client_type = st.selectbox(
        "Client Type",
        [
            "SME Food Producer",
            "Exporter",
            "Retailer",
            "Startup",
            "Importer",
        ]
    )

    view_mode = st.radio(
        "View",
        ["Overview", "Analytics", "Reports", "Updates"]
    )

    if st.button("🔄 Refresh Live Data", use_container_width=True):
        with st.spinner("Fetching live updates from EFSA and RASFF..."):
            try:
                refresh_live_data()
                st.success("Live data refreshed.")
                st.rerun()
            except Exception as e:
                st.error(f"Refresh failed: {e}")

    if LIVE_DATA_FILE.exists():
        ts = datetime.fromtimestamp(LIVE_DATA_FILE.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"Last refresh: {ts}")
    else:
        st.caption("No live refresh yet")

    try:
        openrouter_exists = bool(st.secrets.get("OPENROUTER_API_KEY", ""))
    except Exception:
        openrouter_exists = False

    if openrouter_exists:
        st.success("OpenRouter connected")
        st.caption(f"AI order: {OPENROUTER_MODELS[0]} → {OPENROUTER_MODELS[1]}")
    else:
        st.info("Using built-in local summarization mode")

    st.markdown("## Filters")

    if not df.empty:
        source_options = sorted(df["source"].dropna().astype(str).unique().tolist()) if "source" in df.columns else []
        topic_options = sorted(df["topic"].dropna().astype(str).unique().tolist()) if "topic" in df.columns else []
        risk_options = sorted(df["risk_level"].dropna().astype(str).unique().tolist()) if "risk_level" in df.columns else []

        selected_sources = st.multiselect("Source", source_options, default=source_options)
        selected_topics = st.multiselect("Topic", topic_options, default=topic_options)
        selected_risks = st.multiselect("Risk level", risk_options, default=risk_options)
    else:
        selected_sources, selected_topics, selected_risks = [], [], []

st.markdown(f"""
<div class="hero-box">
    <div class="hero-title">Food Regulatory Intelligence Dashboard</div>
    <p class="hero-subtitle">
        Decision-support layer for food law, compliance, traceability, and supply chain intelligence.
    </p>
    <p class="small-note">
        Client mode: {client_type} | View: {view_mode} | Live data sources: EFSA, RASFF | OpenRouter-ready
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="intro-grid">
    <div class="intro-card">
        <div class="intro-title">What this tool does</div>
        <div class="intro-text">
            It converts regulatory updates into structured consulting outputs by combining source monitoring,
            prioritization logic, client-specific interpretation, and downloadable briefings.
        </div>
    </div>
    <div class="intro-card">
        <div class="intro-title">Why it matters</div>
        <div class="intro-text">
            Regulatory information alone is not enough. What creates value is turning updates into action:
            what matters, for whom, how urgent, and what should happen next.
        </div>
    </div>
    <div class="intro-card">
        <div class="intro-title">Why it scales</div>
        <div class="intro-text">
            The same architecture can support newsletters, client alerts, internal horizon scanning,
            supply chain review, and future AI-assisted legal interpretation workflows.
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

if df.empty:
    st.warning("No data found. Add `data/regulatory_data.json` or refresh live data.")
    st.stop()

filtered = df.copy()

if selected_sources and "source" in filtered.columns:
    filtered = filtered[filtered["source"].isin(selected_sources)]

if selected_topics and "topic" in filtered.columns:
    filtered = filtered[filtered["topic"].isin(selected_topics)]

if selected_risks and "risk_level" in filtered.columns:
    filtered = filtered[filtered["risk_level"].isin(selected_risks)]

if not filtered.empty:
    filtered["impact_score"] = filtered.apply(lambda row: calculate_impact_score(row, client_type), axis=1)
    filtered["priority"] = filtered["impact_score"].apply(determine_priority)
    filtered["why_this_matters"] = filtered.apply(lambda row: why_this_matters(row, client_type), axis=1)

# ---------- VIEW MODE ----------
if view_mode == "Overview":
    render_overview(filtered, client_type)

elif view_mode == "Analytics":
    render_analytics_section(filtered)

elif view_mode == "Reports":
    render_reports(filtered, client_type)

elif view_mode == "Updates":
    render_updates(filtered, client_type)

st.caption("Prototype for regulatory horizon scanning, client-specific intelligence, consulting outputs, analytics, and OpenRouter-based free-model enrichment.")
