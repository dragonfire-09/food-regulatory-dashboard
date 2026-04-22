import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

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


# ---------- STYLES ----------
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
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        padding: 1.5rem 1.5rem 1.2rem 1.5rem;
        border-radius: 18px;
        color: white;
        margin-bottom: 1.2rem;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.15);
    }

    .hero-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .hero-subtitle {
        font-size: 1rem;
        color: #cbd5e1;
        margin-bottom: 0;
    }

    .metric-card {
        background: white;
        border-radius: 16px;
        padding: 1rem 1.1rem;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
        border: 1px solid #e5e7eb;
        margin-bottom: 0.8rem;
    }

    .metric-label {
        font-size: 0.85rem;
        color: #64748b;
        margin-bottom: 0.15rem;
    }

    .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0f172a;
    }

    .section-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #0f172a;
        margin-top: 1.2rem;
        margin-bottom: 0.8rem;
    }

    .update-card {
        background: white;
        border-radius: 18px;
        padding: 1.2rem 1.2rem 1rem 1.2rem;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        border: 1px solid #e5e7eb;
        margin-bottom: 1rem;
    }

    .update-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.45rem;
    }

    .meta-row {
        font-size: 0.88rem;
        color: #64748b;
        margin-bottom: 0.8rem;
    }

    .pill {
        display: inline-block;
        padding: 0.28rem 0.65rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 0.4rem;
        margin-bottom: 0.35rem;
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
        font-size: 0.9rem;
        font-weight: 700;
        color: #334155;
        margin-top: 0.75rem;
        margin-bottom: 0.2rem;
    }

    .subblock-text {
        font-size: 0.95rem;
        color: #0f172a;
        line-height: 1.55;
    }

    .small-note {
        font-size: 0.82rem;
        color: #64748b;
    }

    .stButton button {
        border-radius: 12px;
        border: 1px solid #dbeafe;
        background: white;
        color: #0f172a;
        font-weight: 600;
    }

    .stSidebar {
        background-color: #f8fafc;
    }
</style>
""", unsafe_allow_html=True)


# ---------- DATA HELPERS ----------
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
    efsa = fetch_efsa_updates()
    rasff = fetch_rasff_updates()
    live = efsa + rasff
    save_json_records(LIVE_DATA_FILE, live)
    return live


def combine_data():
    base = load_json_records(BASE_DATA_FILE)
    live = load_json_records(LIVE_DATA_FILE)
    all_records = live + base

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


def format_date(value):
    if pd.isna(value):
        return "Unknown date"
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


# ---------- APP ----------
ensure_data_dir()

df = combine_data()

with st.sidebar:
    st.markdown("## Filters")

    if st.button("🔄 Refresh Live Data", use_container_width=True):
        with st.spinner("Fetching live updates..."):
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
        Live regulatory monitoring prototype combining EFSA, RASFF, and structured intelligence outputs.
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

for _, row in filtered.iterrows():
    title = row.get("title", "Untitled")
    source = row.get("source", "Unknown")
    date_str = format_date(row.get("date", None))
    topic = row.get("topic", "Unknown")
    jurisdiction = row.get("jurisdiction", "Unknown")
    ai_summary = row.get("ai_summary", "No summary available.")
    business_impact = row.get("business_impact", "No impact analysis available.")
    recommended_action = row.get("recommended_action", "No recommended action available.")
    raw_text = row.get("raw_text", "")
    url = row.get("url", "")
    risk_css, risk_label = risk_class(row.get("risk_level", "Low"))

    st.markdown(f"""
    <div class="update-card">
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

    with st.expander("Show raw text"):
        st.write(raw_text if raw_text else "No raw text available.")

    if url:
        st.markdown(f"[Open source item]({url})")

st.caption("Prototype for regulatory horizon scanning, compliance monitoring, and structured client intelligence.")
