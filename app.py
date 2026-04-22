import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Optional OpenAI import
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


# ---------- OPTIONAL OPENAI ----------
def get_openai_client():
    try:
        api_key = st.secrets.get("OPENAI_API_KEY", None)
    except Exception:
        api_key = None

    if not api_key or OpenAI is None:
        return None

    try:
        return OpenAI(api_key=api_key)
    except Exception:
        return None


# ---------- CUSTOM CSS ----------
st.markdown("""
<style>
    .main {
        background-color: #f7f9fc;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
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


# ---------- HELPERS ----------
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


def format_date(value):
    if pd.isna(value):
        return "Unknown date"
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def build_client_alert(row):
    title = row.get("title", "Regulatory Update")
    ai_summary = row.get("ai_summary", "No summary available.")
    impact = row.get("business_impact", "No business impact available.")
    action = row.get("recommended_action", "No recommended action available.")
    source = row.get("source", "Unknown source")
    date_str = format_date(row.get("date", None))

    return f"""Subject: Regulatory Update – {title}

Source: {source}
Date: {date_str}

Summary:
{ai_summary}

Business Impact:
{impact}

Recommended Action:
{action}
"""


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
    width, height = A4

    x = 50
    y = height - 50

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(x, y, title)
    y -= 30

    pdf.setFont("Helvetica", 10)
    for line in content.splitlines():
        wrapped_lines = wrap_text(line, 95)
        for wrapped_line in wrapped_lines:
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


# ---------- LOCAL FALLBACK ----------
def local_ai_fallback(row):
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

    return {
        "ai_summary": f"{base_summary} Source: {source}.",
        "business_impact": impact,
        "recommended_action": action,
    }


# ---------- AI GENERATION ----------
def generate_ai_analysis(row):
    client = get_openai_client()

    if client is None:
        return local_ai_fallback(row)

    try:
        title = row.get("title", "")
        source = row.get("source", "")
        topic = row.get("topic", "")
        jurisdiction = row.get("jurisdiction", "")
        raw_text = row.get("raw_text", "")
        existing_summary = row.get("ai_summary", "")

        prompt = f"""
You are a food regulatory intelligence analyst.

Analyze this update and return STRICT JSON with these keys:
- ai_summary
- business_impact
- recommended_action

Rules:
- Keep each field concise and professional.
- Focus on compliance, supply chain, and commercial implications.
- Do not include markdown.
- Output JSON only.

Update data:
Title: {title}
Source: {source}
Topic: {topic}
Jurisdiction: {jurisdiction}
Existing summary: {existing_summary}
Raw text: {raw_text}
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )

        text = response.output_text.strip()
        parsed = json.loads(text)

        return {
            "ai_summary": parsed.get("ai_summary", existing_summary or "No summary available."),
            "business_impact": parsed.get("business_impact", "No business impact available."),
            "recommended_action": parsed.get("recommended_action", "No recommended action available."),
        }

    except Exception:
        return local_ai_fallback(row)


# ---------- APP ----------
ensure_data_dir()
df = combine_data()

with st.sidebar:
    st.markdown("## Filters")

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

    api_key_exists = False
    try:
        api_key_exists = bool(st.secrets.get("OPENAI_API_KEY", ""))
    except Exception:
        api_key_exists = False

    if api_key_exists:
        st.success("OpenAI connected")
    else:
        st.info("Using built-in local summarization mode")

    if not df.empty:
        source_options = sorted(df["source"].dropna().astype(str).unique().tolist()) if "source" in df.columns else []
        topic_options = sorted(df["topic"].dropna().astype(str).unique().tolist()) if "topic" in df.columns else []
        risk_options = sorted(df["risk_level"].dropna().astype(str).unique().tolist()) if "risk_level" in df.columns else []

        selected_sources = st.multiselect("Source", source_options, default=source_options)
        selected_topics = st.multiselect("Topic", topic_options, default=topic_options)
        selected_risks = st.multiselect("Risk level", risk_options, default=risk_options)
    else:
        selected_sources, selected_topics, selected_risks = [], [], []

st.markdown("""
<div class="hero-box">
    <div class="hero-title">Food Regulatory Intelligence Dashboard</div>
    <p class="hero-subtitle">
        AI-powered regulatory monitoring for food law, compliance, and supply chain intelligence.
    </p>
    <p class="small-note">
        Live data sources: EFSA, RASFF | Prototype with downloads and fallback AI enrichment
    </p>
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

# ---------- METRICS ----------
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Total Updates</div>
        <div class="metric-value">{len(filtered)}</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    high_count = 0
    if "risk_level" in filtered.columns:
        high_count = (filtered["risk_level"].astype(str).str.lower() == "high").sum()
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">High Risk Items</div>
        <div class="metric-value">{high_count}</div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    source_count = filtered["source"].nunique() if "source" in filtered.columns else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Sources</div>
        <div class="metric-value">{source_count}</div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    topic_count = filtered["topic"].nunique() if "topic" in filtered.columns else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Topics</div>
        <div class="metric-value">{topic_count}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="section-title">Latest Regulatory Updates</div>', unsafe_allow_html=True)

for idx, row in filtered.iterrows():
    row_id = row.get("id", f"row-{idx}")

    # session cache
    if f"ai-{row_id}" in st.session_state:
        cached = st.session_state[f"ai-{row_id}"]
        ai_summary = cached["ai_summary"]
        business_impact = cached["business_impact"]
        recommended_action = cached["recommended_action"]
    else:
        ai_summary = row.get("ai_summary", "No summary available.")
        business_impact = row.get("business_impact", "No impact analysis available.")
        recommended_action = row.get("recommended_action", "No recommended action available.")

    title = row.get("title", "Untitled")
    source = row.get("source", "Unknown")
    date_str = format_date(row.get("date", None))
    topic = row.get("topic", "Unknown")
    jurisdiction = row.get("jurisdiction", "Unknown")
    raw_text = row.get("raw_text", "")
    url = row.get("url", "")
    risk_css, risk_label = risk_class(row.get("risk_level", "Low"))
    extra_class = card_risk_class(row.get("risk_level", "Low"))

    st.markdown(f"""
    <div class="update-card {extra_class}">
        <div class="update-title">{title}</div>
        <div class="meta-row">Source: {source} | Date: {date_str} | Jurisdiction: {jurisdiction}</div>
        <div>
            <span class="pill pill-source">{source}</span>
            <span class="pill pill-topic">{topic}</span>
            <span class="{risk_css}">{risk_label} Risk</span>
        </div>
        <div class="subblock-title">AI Summary</div>
        <div class="subblock-text">{ai_summary}</div>
        <div class="subblock-title">Business Impact</div>
        <div class="subblock-text">{business_impact}</div>
        <div class="subblock-title">Recommended Action</div>
        <div class="subblock-text">{recommended_action}</div>
    </div>
    """, unsafe_allow_html=True)

    # Enriched row for exports
    enriched_row = {
        **row.to_dict(),
        "ai_summary": ai_summary,
        "business_impact": business_impact,
        "recommended_action": recommended_action,
    }

    alert_text = build_client_alert(enriched_row)
    safe_name = sanitize_filename(title)
    pdf_bytes = build_pdf_bytes(
        title=f"Client Alert - {title}",
        content=alert_text,
    )

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if st.button("AI Re-Summarize", key=f"ai-btn-{row_id}"):
            with st.spinner("Generating updated analysis..."):
                enriched = generate_ai_analysis(row)
                st.session_state[f"ai-{row_id}"] = enriched
                st.rerun()

    with col2:
        st.download_button(
            label="Download TXT",
            data=alert_text,
            file_name=f"{safe_name}_client_alert.txt",
            mime="text/plain",
            key=f"txt-{row_id}",
        )

    with col3:
        st.download_button(
            label="Download PDF",
            data=pdf_bytes,
            file_name=f"{safe_name}_client_alert.pdf",
            mime="application/pdf",
            key=f"pdf-{row_id}",
        )

    if url:
        st.markdown(f"[Open source item]({url})")

    with st.expander("Show raw text"):
        st.write(raw_text if raw_text else "No raw text available.")

st.caption("Prototype for regulatory horizon scanning, compliance monitoring, downloadable client alerts, and fallback AI enrichment.")
