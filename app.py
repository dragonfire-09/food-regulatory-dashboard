import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from io import BytesIO
import hashlib

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from scrapers.efsa_rss_scraper import fetch_efsa_updates
from scrapers.rasff_scraper import fetch_rasff_updates

# ================================================================
# PAGE CONFIG
# ================================================================
st.set_page_config(
    page_title="Food Regulatory Intelligence Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ================================================================
# CONSTANTS
# ================================================================
DATA_DIR = Path("data")
BASE_DATA_FILE = DATA_DIR / "regulatory_data.json"
LIVE_DATA_FILE = DATA_DIR / "live_updates.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
NOTES_FILE = DATA_DIR / "user_notes.json"

OPENROUTER_MODELS = [
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
]

AUTO_REFRESH_MINUTES = 60

CLIENT_TYPES = [
    "SME Food Producer",
    "Exporter",
    "Retailer",
    "Startup",
    "Importer",
]

CLIENT_ICONS = {
    "SME Food Producer": "🏭",
    "Exporter": "🌍",
    "Retailer": "🛒",
    "Startup": "🚀",
    "Importer": "📦",
}

RISK_COLORS = {
    "high": "#dc2626",
    "medium": "#f97316",
    "low": "#16a34a",
}

PRIORITY_COLORS = {
    "Immediate": "#dc2626",
    "Review": "#f59e0b",
    "Monitor": "#3b82f6",
}

# ================================================================
# SESSION STATE
# ================================================================
def init_session_state():
    defaults = {
        "watchlist": [],
        "user_notes": {},
        "ai_cache": {},
        "filter_presets": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()

# ================================================================
# MINIMAL CSS — sadece genel layout icin, kart icerikleri inline
# ================================================================
st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }
    .stSidebar { background-color: #fafbfc; }
    .stButton button {
        border-radius: 10px;
        font-weight: 600;
        font-size: 0.82rem;
    }
    .stDownloadButton button {
        border-radius: 10px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ================================================================
# OPENROUTER CLIENT
# ================================================================
def get_openrouter_client():
    try:
        api_key = st.secrets.get("OPENROUTER_API_KEY", None)
    except Exception:
        api_key = None
    if not api_key or OpenAI is None:
        return None
    try:
        return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    except Exception:
        return None


# ================================================================
# FILE HELPERS
# ================================================================
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


def ensure_metadata_fields(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "source_status": "unknown",
        "fetch_method": "n/a",
        "notification_reference": "n/a",
        "last_verified": "n/a",
        "jurisdiction": "Unknown",
    }
    for field, default in required.items():
        if field not in df.columns:
            df[field] = default
    return df


@st.cache_data(ttl=300)
def combine_data():
    base = load_json_records(BASE_DATA_FILE)
    live = load_json_records(LIVE_DATA_FILE)
    all_records = live + base

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df = ensure_metadata_fields(df)

    dedupe_cols = [c for c in ["title", "source", "date"] if c in df.columns]
    if dedupe_cols:
        df = df.drop_duplicates(subset=dedupe_cols, keep="first")

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if "id" not in df.columns:
        df["id"] = df.apply(
            lambda r: hashlib.md5(
                f"{r.get('title','')}{r.get('source','')}{r.get('date','')}".encode()
            ).hexdigest()[:12],
            axis=1,
        )

    return df.sort_values("date", ascending=False, na_position="last").reset_index(drop=True)


def file_last_updated(path: Path):
    if not path.exists():
        return None
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return None


def minutes_since_update(path: Path):
    updated = file_last_updated(path)
    if updated is None:
        return None
    return int((datetime.now(timezone.utc) - updated).total_seconds() // 60)


def format_relative_update_time(path: Path):
    mins = minutes_since_update(path)
    if mins is None:
        return "never"
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours} hr ago"
    days = hours // 24
    return f"{days} day(s) ago"


def should_auto_refresh(path: Path, max_age_minutes: int):
    if not path.exists():
        return True
    mins = minutes_since_update(path)
    return mins is None or mins >= max_age_minutes


# ================================================================
# WATCHLIST
# ================================================================
def load_watchlist():
    return load_json_records(WATCHLIST_FILE)


def save_watchlist(wl):
    save_json_records(WATCHLIST_FILE, wl)


def toggle_watchlist(item_id):
    wl = st.session_state.get("watchlist", [])
    if item_id in wl:
        wl.remove(item_id)
    else:
        wl.append(item_id)
    st.session_state["watchlist"] = wl
    save_watchlist(wl)


def is_watchlisted(item_id):
    return item_id in st.session_state.get("watchlist", [])


# ================================================================
# USER NOTES
# ================================================================
def load_user_notes():
    if not NOTES_FILE.exists():
        return {}
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_user_note(item_id, note):
    notes = st.session_state.get("user_notes", {})
    notes[str(item_id)] = note
    st.session_state["user_notes"] = notes
    try:
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_user_note(item_id):
    return st.session_state.get("user_notes", {}).get(str(item_id), "")


# ================================================================
# DISPLAY HELPERS
# ================================================================
def safe_value(val, default="n/a"):
    if val is None:
        return default
    if isinstance(val, float) and pd.isna(val):
        return default
    s = str(val).strip()
    if s.lower() in ["nan", "none", ""]:
        return default
    return val


def format_date(value):
    if pd.isna(value):
        return "Unknown"
    try:
        return pd.to_datetime(value).strftime("%b %d, %Y")
    except Exception:
        return str(value)


def sanitize_filename(value: str) -> str:
    value = value.lower().strip()
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        value = value.replace(ch, "-")
    return value.replace(" ", "_")[:80]


# ================================================================
# PDF HELPERS
# ================================================================
def wrap_text(text: str, max_chars: int = 95):
    if not text:
        return [""]
    words = text.split()
    lines, current = [], ""
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
    x, y = 50, height - 50

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(x, y, title)
    y -= 24
    pdf.setFont("Helvetica", 8)
    pdf.setFillColorRGB(0.5, 0.5, 0.5)
    pdf.drawString(x, y, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    y -= 20
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica", 10)

    for line in content.splitlines():
        for wl in wrap_text(line, 95):
            if y < 60:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = height - 50
            pdf.drawString(x, y, wl)
            y -= 14

    pdf.save()
    buffer.seek(0)
    return buffer.read()


def build_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    export_cols = [c for c in [
        "title", "source", "date", "topic", "risk_level", "jurisdiction",
        "impact_score", "priority", "confidence_score", "source_status",
        "ai_summary", "business_impact", "recommended_action",
        "why_this_matters", "notification_reference", "url",
    ] if c in df.columns]
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df[export_cols].to_excel(writer, index=False, sheet_name="Updates")
    buffer.seek(0)
    return buffer.read()


# ================================================================
# SCORING & CONSULTING
# ================================================================
def calculate_confidence_score(row):
    status = str(safe_value(row.get("source_status"), "unknown")).lower()
    method = str(safe_value(row.get("fetch_method"), "n/a")).lower()
    ref = str(safe_value(row.get("notification_reference"), "n/a")).lower()
    if status == "live" and method == "detail_page" and ref != "n/a":
        return 95
    if status == "live" and method == "rss_feed":
        return 85
    if status == "live":
        return 75
    if status == "fallback":
        return 45
    return 55


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

    if any(w in title for w in ["recall", "salmonella", "allergen", "listeria", "aflatoxin"]):
        score += 2

    bonuses = {
        "Exporter": ["labeling", "contaminants", "traceability"],
        "Retailer": ["labeling", "fraud", "contaminants"],
        "Importer": ["traceability", "contaminants", "fraud"],
        "SME Food Producer": ["labeling", "food safety", "novel foods"],
        "Startup": ["novel foods", "labeling"],
    }
    if topic in bonuses.get(client_type, []):
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

    reasons = {
        "Exporter": {
            "Labeling": "May affect export labeling compliance and destination-market documentation.",
            "Contaminants": "May affect border acceptance and supplier risk in export channels.",
            "Traceability": "May affect documentation continuity across jurisdictions.",
        },
        "Retailer": {
            "Labeling": "May affect on-shelf compliance and private-label exposure.",
            "Fraud": "May affect brand integrity and supplier verification.",
            "Contaminants": "May increase recall risk and supplier coordination needs.",
        },
        "Importer": {
            "Traceability": "May affect inbound documentation and product release decisions.",
            "Contaminants": "May increase batch-hold and customs review requirements.",
        },
        "Startup": {
            "Novel Foods": "May shape market-entry timing and commercialization planning.",
            "Labeling": "May affect packaging design and compliance assumptions.",
        },
        "SME Food Producer": {
            "Labeling": "May require packaging review and updated label controls.",
            "Food Safety": "May affect QA workflows and operational risk exposure.",
        },
    }

    client_reasons = reasons.get(client_type, {})
    if topic in client_reasons:
        return client_reasons[topic]

    if risk == "high":
        return "Commercially material - may require immediate cross-functional review."
    if risk == "low":
        return "Lower urgency - useful for horizon scanning and future planning."
    return "May affect compliance planning, supply chain review, and internal decisions."


def client_adjusted_action(base_action, client_type, topic, priority):
    extras = {
        "Exporter": "Check destination-country implications and border exposure.",
        "Retailer": "Assess shelf impact and supplier exposure.",
        "Importer": "Review supplier documentation and inbound controls.",
        "Startup": "Assess product-market fit and authorization timing.",
    }
    extra = extras.get(client_type, "Review internal QA and production implications.")
    return f"{base_action} {extra}"


# ================================================================
# AI ANALYSIS
# ================================================================
def local_ai_fallback(row, client_type):
    title = str(row.get("title", "Regulatory update"))
    topic = str(row.get("topic", "Food Safety"))
    source = str(row.get("source", "Regulatory source"))
    risk = str(row.get("risk_level", "Medium")).lower()
    existing = str(row.get("ai_summary", ""))

    base = existing if existing else f"This update relates to {topic.lower()} and may require compliance review."

    tl = title.lower()
    analysis = {
        "label": ("May need to review packaging and label approval workflows.",
                   "Review current labels and prepare packaging revisions if needed."),
        "traceability": ("May need stronger product tracking and recordkeeping.",
                         "Assess traceability records and system readiness."),
        "contaminant": ("Increased recall exposure and supplier scrutiny possible.",
                        "Check affected products and review supplier controls."),
        "fraud": ("Authentication and documentary controls may face scrutiny.",
                  "Review provenance records and internal documentation controls."),
        "novel": ("Authorization timing and market-entry planning required.",
                  "Review eligibility, formulation, and approval timing."),
    }

    impact = "May affect compliance planning and documentation."
    action = "Review internally and determine team response."

    for kw, (imp, act) in analysis.items():
        if kw in tl or kw in topic.lower():
            impact, action = imp, act
            break

    if risk == "high":
        impact = "Commercially significant - may require immediate compliance escalation."
        action = "Prioritize immediate review and prepare rapid response plan."
    elif risk == "low":
        impact = "Lower urgency - relevant for horizon scanning."
        action = "Log the update and review in the next compliance cycle."

    action = client_adjusted_action(action, client_type, topic, "Review")

    return {
        "ai_summary": f"{base} Source: {source}.",
        "business_impact": impact,
        "recommended_action": action,
        "_model_used": "local fallback",
    }


def extract_json_block(text: str):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("No valid JSON found")


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
    cache_key = f"{row.get('id', '')}-{client_type}"
    if cache_key in st.session_state.get("ai_cache", {}):
        return st.session_state["ai_cache"][cache_key]

    client = get_openrouter_client()
    if client is None:
        result = local_ai_fallback(row, client_type)
    else:
        prompt = f"""You are a food regulatory intelligence analyst.
Return VALID JSON ONLY with keys: ai_summary, business_impact, recommended_action.
Client type: {client_type}.

Update:
Title: {safe_value(row.get('title'))}
Source: {safe_value(row.get('source'))}
Topic: {safe_value(row.get('topic'))}
Jurisdiction: {safe_value(row.get('jurisdiction'))}
Summary: {safe_value(row.get('ai_summary'))}
Raw: {safe_value(row.get('raw_text'))}"""

        result = None
        for model in OPENROUTER_MODELS:
            try:
                text = try_openrouter_model(client, model, prompt)
                parsed = extract_json_block(text)
                result = {
                    "ai_summary": parsed.get("ai_summary", "No summary."),
                    "business_impact": parsed.get("business_impact", "No impact."),
                    "recommended_action": parsed.get("recommended_action", "No action."),
                    "_model_used": model,
                }
                break
            except Exception:
                continue

        if result is None:
            result = local_ai_fallback(row, client_type)

    st.session_state.setdefault("ai_cache", {})[cache_key] = result
    return result


# ================================================================
# REPORT GENERATORS
# ================================================================
def generate_weekly_report(df, client_type):
    if df.empty:
        return "No updates available."

    rdf = df.sort_values("impact_score", ascending=False)
    top = rdf.head(5)

    lines = [
        "=" * 60,
        "  WEEKLY REGULATORY INTELLIGENCE REPORT",
        "=" * 60, "",
        f"  Client Type: {client_type}",
        f"  Generated:   {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"  Updates:     {len(rdf)}", "",
        "-" * 60,
        "  EXECUTIVE SUMMARY",
        "-" * 60,
        f"  Immediate: {(rdf['priority'] == 'Immediate').sum()}",
        f"  Review:    {(rdf['priority'] == 'Review').sum()}",
        f"  Monitor:   {(rdf['priority'] == 'Monitor').sum()}", "",
        "-" * 60,
        "  TOP PRIORITY UPDATES",
        "-" * 60,
    ]

    for i, (_, row) in enumerate(top.iterrows(), 1):
        lines.append(f"\n  {i}. {row.get('title', 'Untitled')}")
        lines.append(f"     Source: {row.get('source', '?')} | {format_date(row.get('date'))}")
        lines.append(f"     Score: {row.get('impact_score', 0)}/10 | Priority: {row.get('priority', '?')}")
        lines.append(f"     Why: {row.get('why_this_matters', '')}")
        lines.append(f"     Action: {row.get('recommended_action', '')}")

    lines.extend(["", "=" * 60])
    return "\n".join(lines)


def build_full_report(df, client_type):
    if df.empty:
        return "No data available."
    df = df.sort_values("impact_score", ascending=False)
    lines = [
        "=" * 60,
        "  FULL REGULATORY INTELLIGENCE REPORT",
        "=" * 60, "",
        f"  Client Type: {client_type}",
        f"  Generated:   {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"  Total:       {len(df)}", "",
    ]
    for _, row in df.iterrows():
        lines.append(f"  > {row.get('title', 'Untitled')}")
        lines.append(f"    {row.get('source', '?')} | {format_date(row.get('date'))}")
        lines.append(f"    Priority: {row.get('priority', '?')} | Score: {row.get('impact_score', 0)}/10")
        lines.append(f"    Action: {row.get('recommended_action', '')}")
        lines.append("")
    return "\n".join(lines)


def generate_client_insights(df, client_type):
    if df.empty:
        return {
            "headline": "No updates available.",
            "key_risk": "No key risk detected.",
            "operational_focus": "Refresh data or broaden filters.",
            "recommended_next_step": "N/A",
            "trend_direction": "stable",
        }

    sdf = df.sort_values("impact_score", ascending=False)
    top_row = sdf.iloc[0]
    top_topic = sdf["topic"].mode().iloc[0] if not sdf["topic"].mode().empty else "Food Safety"
    imm = int((sdf["priority"] == "Immediate").sum())
    high = int((sdf["risk_level"].astype(str).str.lower() == "high").sum())

    headline = (
        f"For {client_type.lower()}s: {imm} immediate-priority, "
        f"{high} high-risk update(s), concentrated around {top_topic.lower()}."
    )

    focus_map = {
        "Exporter": "Border-facing documentation and destination-market compliance.",
        "Retailer": "Shelf compliance, supplier coordination, consumer-facing risk.",
        "Importer": "Inbound controls, traceability, batch-level documentation.",
        "Startup": "Packaging assumptions, market-entry timing, regulatory readiness.",
    }
    focus = focus_map.get(client_type, "Internal QA, compliance review, product documentation.")

    return {
        "headline": headline,
        "key_risk": f"Highest-impact: {top_row.get('title', 'Untitled')}",
        "operational_focus": focus,
        "recommended_next_step": "Start with top-priority item, align affected team, convert to action note.",
        "trend_direction": "up" if imm > 2 else ("stable" if imm > 0 else "down"),
    }


def build_client_alert(row, client_type, impact_score, priority, why_matters):
    return f"""Subject: Regulatory Update - {row.get('title', 'Update')}

Client Type: {client_type}
Source: {row.get('source', 'Unknown')}
Date: {format_date(row.get('date'))}
Topic: {row.get('topic', 'Unknown')}
Impact Score: {impact_score}/10
Priority: {priority}

Summary:
{row.get('ai_summary', 'No summary.')}

Why this matters:
{why_matters}

Business Impact:
{row.get('business_impact', 'No impact analysis.')}

Recommended Action:
{row.get('recommended_action', 'No action.')}
"""


# ================================================================
# ANALYTICS FRAMES
# ================================================================
def build_analytics_frames(df):
    frames = {}
    if df.empty:
        return frames

    work = df.copy()
    if "date" in work.columns:
        work["date_only"] = pd.to_datetime(work["date"], errors="coerce").dt.date

    for col, key in [
        ("source", "source_counts"),
        ("topic", "topic_counts"),
        ("priority", "priority_counts"),
        ("risk_level", "risk_counts"),
        ("source_status", "status_counts"),
    ]:
        if col in work.columns:
            vc = work[col].astype(str).str.title().value_counts().reset_index()
            vc.columns = [col, "count"]
            frames[key] = vc

    if "date_only" in work.columns:
        trend = work.groupby("date_only").size().reset_index(name="count")
        trend["date_only"] = pd.to_datetime(trend["date_only"])
        frames["trend"] = trend.sort_values("date_only")

    if "impact_score" in work.columns and "topic" in work.columns:
        st_df = work.groupby("topic", dropna=False)["impact_score"].mean().round(2).reset_index()
        frames["score_by_topic"] = st_df.sort_values("impact_score", ascending=False)

    if "confidence_score" in work.columns and "source" in work.columns:
        cs = work.groupby("source", dropna=False)["confidence_score"].mean().round(2).reset_index()
        frames["confidence_by_source"] = cs.sort_values("confidence_score", ascending=False)

    if "impact_score" in work.columns and "confidence_score" in work.columns:
        frames["scatter_data"] = work[
            ["title", "impact_score", "confidence_score", "risk_level", "topic", "source"]
        ].copy()

    if "topic" in work.columns and "risk_level" in work.columns:
        hm = work.groupby(["topic", "risk_level"]).size().reset_index(name="count")
        frames["heatmap_data"] = hm

    if "jurisdiction" in work.columns:
        jur = work["jurisdiction"].astype(str).value_counts().reset_index()
        jur.columns = ["jurisdiction", "count"]
        frames["jurisdiction_counts"] = jur[jur["jurisdiction"] != "Unknown"].head(15)

    return frames


# ================================================================
# SEARCH
# ================================================================
def apply_search(df, query: str):
    if not query.strip() or df.empty:
        return df
    q = query.strip().lower()
    fields = [
        "title", "topic", "source", "ai_summary", "business_impact",
        "recommended_action", "raw_text", "why_this_matters",
        "notification_reference", "jurisdiction",
    ]

    def match(row):
        haystack = " ".join(str(row.get(f, "")) for f in fields).lower()
        return q in haystack

    return df[df.apply(match, axis=1)]


# ================================================================
# HERO RENDERER
# ================================================================
def render_hero(client_type, view_mode, last_updated, df):
    total = len(df)
    immediate = int((df["priority"] == "Immediate").sum()) if not df.empty and "priority" in df.columns else 0
    avg_score = round(df["impact_score"].mean(), 1) if not df.empty and "impact_score" in df.columns else 0
    live_pct = 0
    if not df.empty and "source_status" in df.columns:
        lc = (df["source_status"].astype(str).str.lower() == "live").sum()
        live_pct = int(lc / total * 100) if total > 0 else 0

    # Hero box - tek parca, emoji yok
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#0b1220 0%,#1e3a5f 40%,#1d4ed8 100%);'
        f'padding:1.6rem 2rem 1.3rem;border-radius:20px;color:white;margin-bottom:1rem;'
        f'box-shadow:0 20px 40px rgba(15,23,42,0.25);">'
        f'<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.12em;'
        f'text-transform:uppercase;color:#93c5fd;margin-bottom:0.4rem;">'
        f'Regulatory Intelligence Platform - {client_type}</div>'
        f'<div style="font-size:1.9rem;font-weight:800;margin-bottom:0.25rem;line-height:1.15;">'
        f'Food Regulatory Intelligence Dashboard</div>'
        f'<p style="font-size:0.92rem;color:#dbeafe;margin-bottom:0.4rem;line-height:1.5;max-width:800px;">'
        f'Decision-support layer for food law, compliance, traceability, and supply chain intelligence.</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Stats - native Streamlit metrics
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("Total Updates", total)
    sc2.metric("Immediate", immediate)
    sc3.metric("Avg Impact", avg_score)
    sc4.metric("Live Data", f"{live_pct}%")
    sc5.metric("Last Refresh", last_updated)


# ================================================================
# CLIENT STRIP
# ================================================================
def render_client_strip(client_type):
    chips = []
    for label in CLIENT_TYPES:
        icon = CLIENT_ICONS.get(label, "")
        if label == client_type:
            style = (
                "display:inline-flex;align-items:center;gap:6px;background:linear-gradient(135deg,#dbeafe,#ede9fe);"
                "border:1.5px solid #818cf8;color:#1e3a8a;border-radius:999px;padding:0.45rem 0.85rem;"
                "font-size:0.82rem;font-weight:700;box-shadow:0 2px 8px rgba(99,102,241,0.15);"
            )
        else:
            style = (
                "display:inline-flex;align-items:center;gap:6px;background:white;"
                "border:1.5px solid #e2e8f0;color:#475569;border-radius:999px;padding:0.45rem 0.85rem;"
                "font-size:0.82rem;font-weight:600;"
            )
        chips.append(f'<span style="{style}">{icon} {label}</span>')

    st.markdown(
        '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:0.8rem;">'
        + "".join(chips)
        + "</div>",
        unsafe_allow_html=True,
    )


# ================================================================
# INTRO CARDS
# ================================================================
def render_intro_cards():
    data = [
        ("What this tool does",
         "Converts regulatory updates into structured consulting outputs - "
         "source monitoring, prioritization, client-specific interpretation, and downloadable briefings."),
        ("Why it matters",
         "Regulatory information alone is not enough. Value comes from turning updates into action: "
         "what matters, for whom, how urgent, and what should happen next."),
        ("Why it scales",
         "Same architecture supports newsletters, client alerts, horizon scanning, "
         "supply chain review, and AI-assisted legal interpretation workflows."),
    ]
    cols = st.columns(3)
    for i, (title, text) in enumerate(data):
        with cols[i]:
            st.markdown(
                f'<div style="background:white;border-radius:14px;padding:0.9rem 1rem;'
                f'border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(15,23,42,0.04);min-height:140px;">'
                f'<div style="font-size:0.88rem;font-weight:700;color:#0f172a;margin-bottom:0.25rem;">'
                f'{title}</div>'
                f'<div style="font-size:0.82rem;color:#475569;line-height:1.5;">{text}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ================================================================
# METRIC CARDS (Native Streamlit)
# ================================================================
def render_metric_cards(filtered, client_type):
    total = len(filtered)
    immediate = int((filtered["priority"] == "Immediate").sum()) if not filtered.empty else 0
    review = int((filtered["priority"] == "Review").sum()) if not filtered.empty else 0
    high_risk = int((filtered["risk_level"].astype(str).str.lower() == "high").sum()) if not filtered.empty else 0
    avg_score = round(filtered["impact_score"].mean(), 1) if not filtered.empty else 0
    avg_conf = round(filtered["confidence_score"].mean(), 1) if not filtered.empty else 0
    topics = int(filtered["topic"].nunique()) if "topic" in filtered.columns and not filtered.empty else 0
    wl_count = sum(1 for _, r in filtered.iterrows() if is_watchlisted(r.get("id", "")))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Updates", total)
    c2.metric("Immediate", immediate, delta=f"{immediate} need attention" if immediate else None, delta_color="inverse")
    c3.metric("Review", review)
    c4.metric("High Risk", high_risk, delta=f"{high_risk} flagged" if high_risk else None, delta_color="inverse")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Avg Impact", f"{avg_score}/10")
    c6.metric("Avg Confidence", f"{avg_conf}%")
    c7.metric("Topics", topics)
    c8.metric("Watchlist", wl_count)


# ================================================================
# TOP URGENT ITEMS
# ================================================================
def render_top_urgent_items(filtered, n=3):
    st.subheader(f"Top {n} Urgent Items")

    if filtered.empty:
        st.info("No urgent items available.")
        return

    urgent = filtered.sort_values(["impact_score", "confidence_score"], ascending=False).head(n)
    cols = st.columns(n)

    for i, (_, row) in enumerate(urgent.iterrows()):
        with cols[i]:
            risk_val = str(row.get("risk_level", "Low")).lower()
            border_color = RISK_COLORS.get(risk_val, "#94a3b8")
            score = row.get("impact_score", 0)
            conf = int(row.get("confidence_score", 0))
            priority = row.get("priority", "Monitor")
            title = row.get("title", "Untitled")
            source = row.get("source", "Unknown")
            date_str = format_date(row.get("date"))
            topic = row.get("topic", "Unknown")
            why = row.get("why_this_matters", "N/A")

            # Kart header
            st.markdown(
                f'<div style="border-left:4px solid {border_color};border-radius:12px;'
                f'padding:1rem;background:white;box-shadow:0 2px 8px rgba(0,0,0,0.06);">'
                f'<div style="font-size:1.8rem;color:#e2e8f0;font-weight:800;float:right;">#{i + 1}</div>'
                f'<div style="font-size:0.92rem;font-weight:700;color:#0f172a;line-height:1.3;">{title}</div>'
                f'<div style="font-size:0.78rem;color:#64748b;margin-top:0.3rem;">'
                f'{source} | {date_str}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Score bar
            pct = min(score / 10 * 100, 100)
            bar_color = "#dc2626" if score >= 8 else ("#f59e0b" if score >= 5 else "#3b82f6")
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin:0.4rem 0;">'
                f'<div style="flex:1;background:#f1f5f9;border-radius:999px;height:6px;overflow:hidden;">'
                f'<div style="width:{pct}%;background:{bar_color};height:100%;border-radius:999px;"></div>'
                f'</div>'
                f'<span style="font-size:0.82rem;font-weight:700;color:{bar_color};">{score}/10</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Mini-metrikler
            mc1, mc2, mc3 = st.columns(3)
            mc1.caption(f"**{priority}**")
            mc2.caption(f"**{topic}**")
            mc3.caption(f"Conf: **{conf}**")

            # Why matters
            st.markdown(
                f'<div style="background:#f8fafc;border-radius:8px;padding:0.5rem 0.7rem;'
                f'font-size:0.82rem;color:#334155;border:1px solid #f1f5f9;margin-top:0.3rem;">'
                f'<strong>Why this matters:</strong><br>{why}</div>',
                unsafe_allow_html=True,
            )


# ================================================================
# TIMELINE
# ================================================================
def render_timeline(filtered, max_items=8):
    st.subheader("Recent Timeline")

    if filtered.empty:
        st.info("No timeline data.")
        return

    recent = filtered.sort_values("date", ascending=False).head(max_items)

    for _, row in recent.iterrows():
        risk = str(row.get("risk_level", "Low")).lower()
        dot_color = RISK_COLORS.get(risk, "#94a3b8")
        title = row.get("title", "Untitled")
        source = row.get("source", "Unknown")
        date_str = format_date(row.get("date"))
        score = row.get("impact_score", 0)
        priority = row.get("priority", "Monitor")
        wl = " [Watchlisted]" if is_watchlisted(row.get("id", "")) else ""

        st.markdown(
            f'<div style="display:flex;gap:12px;margin-bottom:0.5rem;padding-bottom:0.5rem;'
            f'border-bottom:1px solid #f1f5f9;">'
            f'<div style="width:10px;height:10px;border-radius:50%;background:{dot_color};'
            f'margin-top:5px;flex-shrink:0;"></div>'
            f'<div style="flex:1;">'
            f'<div style="font-size:0.85rem;font-weight:600;color:#1e293b;">{title}{wl}</div>'
            f'<div style="font-size:0.75rem;color:#94a3b8;">'
            f'{source} | {date_str} | Score {score}/10 | {priority}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )


# ================================================================
# VIEW: OVERVIEW
# ================================================================
def render_overview(filtered, client_type):
    render_metric_cards(filtered, client_type)

    # Client insights
    st.subheader("Client-Specific Insights")
    insights = generate_client_insights(filtered, client_type)
    trend_label = {"up": "Trending Up", "down": "Trending Down", "stable": "Stable"}.get(
        insights.get("trend_direction", "stable"), "Stable"
    )

    st.markdown(
        f'<div style="background:linear-gradient(135deg,#f0f9ff 0%,#f5f3ff 100%);'
        f'border-radius:14px;padding:1.1rem;border:1px solid #e0e7ff;margin-bottom:0.5rem;">'
        f'<div style="font-size:0.98rem;font-weight:700;color:#1e293b;margin-bottom:0.5rem;">'
        f'[{trend_label}] {insights["headline"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    for label, text in [
        ("Key Risk", insights["key_risk"]),
        ("Operational Focus", insights["operational_focus"]),
        ("Next Step", insights["recommended_next_step"]),
    ]:
        st.markdown(
            f'<div style="font-size:0.86rem;color:#475569;line-height:1.5;margin-bottom:0.3rem;">'
            f'<strong style="color:#334155;">{label}:</strong> {text}</div>',
            unsafe_allow_html=True,
        )

    render_top_urgent_items(filtered)
    render_timeline(filtered)

    # Quick analytics
    st.subheader("Quick Analytics")
    if not filtered.empty:
        frames = build_analytics_frames(filtered)
        c1, c2 = st.columns(2)
        if "topic_counts" in frames:
            fig = px.pie(frames["topic_counts"], names="topic", values="count", hole=0.45)
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=280)
            c1.plotly_chart(fig, use_container_width=True)
        if "priority_counts" in frames:
            fig = px.bar(
                frames["priority_counts"], x="priority", y="count",
                color="priority", color_discrete_map=PRIORITY_COLORS,
            )
            fig.update_layout(margin=dict(t=10, b=10), height=280, showlegend=False)
            c2.plotly_chart(fig, use_container_width=True)


# ================================================================
# VIEW: ANALYTICS
# ================================================================
def render_analytics_section(filtered):
    st.subheader("Analytics Dashboard")

    if filtered.empty:
        st.info("No data for analytics.")
        return

    frames = build_analytics_frames(filtered)

    tab1, tab2, tab3, tab4 = st.tabs(["Distribution", "Heatmap & Scatter", "Trends", "Geography"])

    with tab1:
        c1, c2 = st.columns(2)
        if "source_counts" in frames:
            fig = px.bar(frames["source_counts"], x="source", y="count", title="By Source",
                         color="count", color_continuous_scale="Blues")
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c1.plotly_chart(fig, use_container_width=True)
        if "topic_counts" in frames:
            fig = px.pie(frames["topic_counts"], names="topic", values="count", title="Topics", hole=0.4)
            fig.update_layout(margin=dict(t=40, b=20))
            c2.plotly_chart(fig, use_container_width=True)

        c3, c4 = st.columns(2)
        if "priority_counts" in frames:
            fig = px.bar(frames["priority_counts"], x="priority", y="count", title="Priority",
                         color="priority", color_discrete_map=PRIORITY_COLORS)
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c3.plotly_chart(fig, use_container_width=True)
        if "risk_counts" in frames:
            fig = px.bar(frames["risk_counts"], x="risk_level", y="count", title="Risk",
                         color="risk_level",
                         color_discrete_map={"High": "#dc2626", "Medium": "#f59e0b", "Low": "#16a34a"})
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c4.plotly_chart(fig, use_container_width=True)

        c5, c6 = st.columns(2)
        if "score_by_topic" in frames:
            fig = px.bar(frames["score_by_topic"], x="topic", y="impact_score",
                         title="Avg Impact by Topic", color="impact_score", color_continuous_scale="OrRd")
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c5.plotly_chart(fig, use_container_width=True)
        if "confidence_by_source" in frames:
            fig = px.bar(frames["confidence_by_source"], x="source", y="confidence_score",
                         title="Avg Confidence by Source", color="confidence_score", color_continuous_scale="Greens")
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c6.plotly_chart(fig, use_container_width=True)

    with tab2:
        if "heatmap_data" in frames:
            hm = frames["heatmap_data"]
            pivot = hm.pivot_table(index="topic", columns="risk_level", values="count", fill_value=0)
            fig = px.imshow(pivot, text_auto=True, aspect="auto", title="Topic x Risk Heatmap",
                            color_continuous_scale="YlOrRd")
            fig.update_layout(margin=dict(t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)

        if "scatter_data" in frames:
            sdf = frames["scatter_data"]
            fig = px.scatter(sdf, x="impact_score", y="confidence_score", color="risk_level",
                             hover_data=["title", "source", "topic"],
                             title="Impact vs Confidence",
                             color_discrete_map={"High": "#dc2626", "Medium": "#f59e0b", "Low": "#16a34a"})
            fig.update_layout(margin=dict(t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        if "trend" in frames and not frames["trend"].empty:
            fig = px.area(frames["trend"], x="date_only", y="count", title="Volume Over Time", markers=True)
            fig.update_layout(margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No time-series data.")

        if "status_counts" in frames:
            fig = px.pie(frames["status_counts"], names="source_status", values="count",
                         title="Data Status", hole=0.4,
                         color_discrete_map={"Live": "#10b981", "Fallback": "#f59e0b", "Unknown": "#94a3b8"})
            st.plotly_chart(fig, use_container_width=True)

    with tab4:
        if "jurisdiction_counts" in frames and not frames["jurisdiction_counts"].empty:
            fig = px.bar(frames["jurisdiction_counts"], x="jurisdiction", y="count",
                         title="By Jurisdiction", color="count", color_continuous_scale="Viridis")
            fig.update_layout(margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No jurisdiction data.")


# ================================================================
# VIEW: REPORTS
# ================================================================
def render_reports(filtered, client_type):
    st.subheader("Report Generator")

    report_type = st.radio("Report Type",
                           ["Weekly Summary", "Full Intelligence Report", "Executive Brief"],
                           horizontal=True)

    if report_type == "Weekly Summary":
        report_text = generate_weekly_report(filtered, client_type)
    elif report_type == "Full Intelligence Report":
        report_text = build_full_report(filtered, client_type)
    else:
        ins = generate_client_insights(filtered, client_type)
        report_text = (
            f"EXECUTIVE BRIEF\n{'=' * 50}\n"
            f"Client Type: {client_type}\n"
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"HEADLINE\n{ins['headline']}\n\n"
            f"KEY RISK\n{ins['key_risk']}\n\n"
            f"OPERATIONAL FOCUS\n{ins['operational_focus']}\n\n"
            f"NEXT STEP\n{ins['recommended_next_step']}\n"
            f"{'=' * 50}"
        )

    # Preview
    preview = report_text.split("\n")[:20]
    suffix = "\n..." if len(report_text.split("\n")) > 20 else ""
    st.code("\n".join(preview) + suffix, language=None)

    # Downloads
    pdf_bytes = build_pdf_bytes(report_type, report_text)

    dc1, dc2, dc3, dc4 = st.columns(4)
    with dc1:
        st.download_button("Download TXT", report_text,
                           f"{sanitize_filename(report_type)}_{sanitize_filename(client_type)}.txt",
                           "text/plain", key="rpt-txt")
    with dc2:
        st.download_button("Download PDF", pdf_bytes,
                           f"{sanitize_filename(report_type)}_{sanitize_filename(client_type)}.pdf",
                           "application/pdf", key="rpt-pdf")
    with dc3:
        if not filtered.empty:
            st.download_button("Download Excel", build_excel_bytes(filtered),
                               f"data_{sanitize_filename(client_type)}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rpt-xl")
    with dc4:
        if not filtered.empty:
            st.download_button("Download CSV", filtered.to_csv(index=False),
                               f"data_{sanitize_filename(client_type)}.csv",
                               "text/csv", key="rpt-csv")

    # Stats
    st.subheader("Report Statistics")
    if not filtered.empty:
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Immediate", (filtered["priority"] == "Immediate").sum())
        sc2.metric("Review", (filtered["priority"] == "Review").sum())
        sc3.metric("Monitor", (filtered["priority"] == "Monitor").sum())

        top_t = filtered["topic"].value_counts().head(5)
        fig = px.bar(top_t, orientation="h", title="Top 5 Topics")
        fig.update_layout(showlegend=False, yaxis_title="", xaxis_title="Count", margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)


# ================================================================
# SINGLE UPDATE CARD RENDERER
# ================================================================
def render_single_update_card(row, idx, client_type):
    row_id = row.get("id", f"row-{idx}")
    watchlisted = is_watchlisted(row_id)
    ai_key = f"ai-{row_id}-{client_type}"

    if ai_key in st.session_state:
        cached = st.session_state[ai_key]
        ai_summary = cached["ai_summary"]
        business_impact = cached["business_impact"]
        recommended_action = cached["recommended_action"]
        model_used = cached.get("_model_used", "local fallback")
    else:
        ai_summary = safe_value(row.get("ai_summary"), "No summary available.")
        business_impact = safe_value(row.get("business_impact"), "No impact analysis.")
        recommended_action = safe_value(row.get("recommended_action"), "No action available.")
        model_used = "initial data"

    title = safe_value(row.get("title"), "Untitled")
    source = safe_value(row.get("source"), "Unknown")
    date_str = format_date(row.get("date"))
    topic = safe_value(row.get("topic"), "Unknown")
    jurisdiction = safe_value(row.get("jurisdiction"), "Unknown")
    url = safe_value(row.get("url"), "")
    risk_val = str(row.get("risk_level", "Low")).lower()
    border_color = RISK_COLORS.get(risk_val, "#94a3b8")
    score = row.get("impact_score", 0)
    priority = safe_value(row.get("priority"), "Monitor")
    why_matters = safe_value(row.get("why_this_matters"), "")
    source_status = safe_value(row.get("source_status"), "unknown")
    confidence_score = int(row.get("confidence_score", 0))
    fetch_method = safe_value(row.get("fetch_method"), "n/a")
    notification_ref = safe_value(row.get("notification_reference"), "n/a")
    adjusted_action = client_adjusted_action(recommended_action, client_type, topic, priority)
    wl_marker = "[Watchlisted] " if watchlisted else ""

    # Status badge color
    status_color = {"live": "#059669", "fallback": "#d97706"}.get(source_status.lower(), "#9ca3af")
    status_label = source_status.upper()

    # Risk pill colors
    risk_bg = {"high": "#fee2e2", "medium": "#ffedd5", "low": "#dcfce7"}.get(risk_val, "#f1f5f9")
    risk_fg = {"high": "#b91c1c", "medium": "#c2410c", "low": "#15803d"}.get(risk_val, "#64748b")
    risk_label = risk_val.title()

    # Priority pill colors
    pri_bg = {"Immediate": "#fee2e2", "Review": "#fef3c7", "Monitor": "#dbeafe"}.get(priority, "#f1f5f9")
    pri_fg = {"Immediate": "#991b1b", "Review": "#92400e", "Monitor": "#1d4ed8"}.get(priority, "#64748b")

    # Confidence pill colors
    conf_bg = "#dcfce7" if confidence_score >= 85 else ("#fef3c7" if confidence_score >= 60 else "#fee2e2")
    conf_fg = "#166534" if confidence_score >= 85 else ("#92400e" if confidence_score >= 60 else "#991b1b")

    # --- CARD HEADER ---
    st.markdown(
        f'<div style="border-left:5px solid {border_color};border-radius:14px;'
        f'padding:1rem 1.2rem;background:white;box-shadow:0 4px 16px rgba(0,0,0,0.05);'
        f'border:1px solid #e2e8f0;">'
        f'<span style="display:inline-block;padding:3px 8px;border-radius:999px;'
        f'font-size:0.68rem;font-weight:700;background:rgba(0,0,0,0.06);'
        f'color:{status_color};margin-bottom:6px;">{status_label}</span>'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<div style="font-size:1.05rem;font-weight:700;color:#0f172a;line-height:1.3;flex:1;">'
        f'{wl_marker}{title}</div>'
        f'<div style="background:#0f172a;color:white;border-radius:10px;padding:0.3rem 0.6rem;'
        f'font-size:0.78rem;font-weight:700;margin-left:12px;white-space:nowrap;">{score}/10</div>'
        f'</div>'
        f'<div style="font-size:0.82rem;color:#64748b;margin-top:0.3rem;">'
        f'{source} &middot; {date_str} &middot; {jurisdiction}</div>'
        f'<div style="font-size:0.72rem;color:#94a3b8;margin-top:0.15rem;">'
        f'Fetch: {fetch_method} &middot; Ref: {notification_ref} &middot; Model: {model_used}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # --- PILLS ---
    pill_style = "display:inline-block;padding:0.25rem 0.6rem;border-radius:999px;font-size:0.72rem;font-weight:700;"
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin:0.4rem 0;">'
        f'<span style="{pill_style}background:#eef2ff;color:#4338ca;">{source}</span>'
        f'<span style="{pill_style}background:#e0f2fe;color:#0369a1;">{topic}</span>'
        f'<span style="{pill_style}background:{risk_bg};color:{risk_fg};">{risk_label} Risk</span>'
        f'<span style="{pill_style}background:{pri_bg};color:{pri_fg};">{priority}</span>'
        f'<span style="{pill_style}background:{conf_bg};color:{conf_fg};">Conf. {confidence_score}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # --- SCORE BAR ---
    pct = min(score / 10 * 100, 100)
    bar_color = "#dc2626" if score >= 8 else ("#f59e0b" if score >= 5 else "#3b82f6")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin:0.3rem 0;">'
        f'<div style="flex:1;background:#f1f5f9;border-radius:999px;height:6px;overflow:hidden;">'
        f'<div style="width:{pct}%;background:{bar_color};height:100%;border-radius:999px;"></div>'
        f'</div>'
        f'<span style="font-size:0.82rem;font-weight:700;color:{bar_color};">{score}/10</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

       # --- CONTENT BLOCKS  
    block_style = (
        "margin-top:0.4rem;padding:0.5rem 0.7rem;background:#f8fafc;"
        "border-radius:8px;border:1px solid #f1f5f9;"
    )
    title_style = (
        "font-size:0.72rem;font-weight:700;color:#64748b;"
        "text-transform:uppercase;letter-spacing:0.04em;margin-bottom:0.2rem;"
    )
    text_style = "font-size:0.86rem;color:#1e293b;line-height:1.55;"

    for block_title, block_text in [
        ("AI Summary", ai_summary),
        ("Why This Matters", why_matters),
        ("Business Impact", business_impact),
        ("Recommended Action", adjusted_action),
    ]:
        st.markdown(
            f'<div style="{block_style}">'
            f'<div style="{title_style}">{block_title}</div>'
            f'<div style="{text_style}">{block_text}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # --- ACTION BUTTONS ---
    enriched_row = {
        **row.to_dict(),
        "ai_summary": ai_summary,
        "business_impact": business_impact,
        "recommended_action": adjusted_action,
    }
    alert_text = build_client_alert(enriched_row, client_type, score, priority, why_matters)
    safe_name = sanitize_filename(title)
    pdf_bytes = build_pdf_bytes(f"Client Alert - {title}", alert_text)

    btn_cols = st.columns([1, 1, 1, 1, 1])

    with btn_cols[0]:
        wl_label = "Remove from Watchlist" if watchlisted else "Add to Watchlist"
        if st.button(wl_label, key=f"wl-{row_id}"):
            toggle_watchlist(row_id)
            st.rerun()

    with btn_cols[1]:
        if st.button("AI Analyze", key=f"ai-{row_id}-{client_type}"):
            with st.spinner("Analyzing..."):
                enriched = generate_ai_analysis(row, client_type)
                st.session_state[ai_key] = enriched
                st.rerun()

    with btn_cols[2]:
        st.download_button(
            "Download TXT", alert_text,
            f"{safe_name}_alert.txt", "text/plain",
            key=f"txt-{row_id}-{client_type}",
        )

    with btn_cols[3]:
        st.download_button(
            "Download PDF", pdf_bytes,
            f"{safe_name}_alert.pdf", "application/pdf",
            key=f"pdf-{row_id}-{client_type}",
        )

    with btn_cols[4]:
        if url:
            st.link_button("Open Source", url)

    # --- EXPANDABLE: NOTES & RAW TEXT ---
    with st.expander("Notes & Raw Text"):
        note_val = get_user_note(row_id)
        new_note = st.text_area(
            "Your note", value=note_val,
            key=f"note-{row_id}",
            placeholder="Add a personal note...",
            height=80,
        )
        if new_note != note_val:
            save_user_note(row_id, new_note)
            st.success("Note saved.")

        raw_text = safe_value(row.get("raw_text"), "No raw text available.")
        st.text_area("Raw text", value=raw_text, height=100, disabled=True, key=f"raw-{row_id}")

    st.divider()


# ================================================================
# VIEW: UPDATES
# ================================================================
def render_updates(filtered, client_type):
    st.subheader("Regulatory Updates")

    # Search & sort
    sc1, sc2, sc3 = st.columns([3, 1, 1])
    with sc1:
        search_query = st.text_input(
            "Search", placeholder="Search by title, topic, source, summary...",
            label_visibility="collapsed",
        )
    with sc2:
        sort_by = st.selectbox(
            "Sort by", ["Impact Score", "Date", "Confidence"],
            label_visibility="collapsed",
        )
    with sc3:
        sort_order = st.selectbox(
            "Order", ["Descending", "Ascending"],
            label_visibility="collapsed",
        )

    updates_df = apply_search(filtered, search_query)

    ascending = sort_order == "Ascending"
    sort_col = {
        "Impact Score": "impact_score",
        "Date": "date",
        "Confidence": "confidence_score",
    }.get(sort_by, "impact_score")
    if sort_col in updates_df.columns:
        updates_df = updates_df.sort_values(sort_col, ascending=ascending)

    st.caption(f"Showing {len(updates_df)} of {len(filtered)} update(s)")

    # Pagination
    items_per_page = st.select_slider("Items per page", options=[5, 10, 15, 25], value=10)
    total_pages = max(1, (len(updates_df) + items_per_page - 1) // items_per_page)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_df = updates_df.iloc[start_idx:end_idx]

    st.caption(f"Page {page} of {total_pages}")

    for idx_val, row in page_df.iterrows():
        render_single_update_card(row, idx_val, client_type)


# ================================================================
# VIEW: WATCHLIST
# ================================================================
def render_watchlist_view(filtered, client_type):
    st.subheader("Watchlist")

    wl_ids = st.session_state.get("watchlist", [])

    if not wl_ids:
        st.info("Your watchlist is empty. Add items from the Updates view.")
        return

    wl_df = filtered[filtered["id"].isin(wl_ids)] if "id" in filtered.columns else pd.DataFrame()

    if wl_df.empty:
        st.warning("Watchlisted items not found in current filters. Try broadening your filters.")
        return

    st.caption(f"{len(wl_df)} watchlisted item(s)")

    for idx_val, row in wl_df.iterrows():
        row_id = row.get("id", "")
        risk_val = str(row.get("risk_level", "Low")).lower()
        border_color = RISK_COLORS.get(risk_val, "#94a3b8")
        score = row.get("impact_score", 0)
        priority = safe_value(row.get("priority"), "Monitor")
        conf = int(row.get("confidence_score", 0))
        title = safe_value(row.get("title"), "Untitled")
        source = safe_value(row.get("source"), "Unknown")
        date_str = format_date(row.get("date"))
        topic = safe_value(row.get("topic"), "Unknown")
        why = safe_value(row.get("why_this_matters"), "N/A")
        action = safe_value(row.get("recommended_action"), "N/A")

        # Card
        st.markdown(
            f'<div style="border-left:5px solid {border_color};border-radius:14px;'
            f'padding:1rem 1.2rem;background:linear-gradient(135deg,#fffbeb 0%,#ffffff 100%);'
            f'box-shadow:0 4px 16px rgba(0,0,0,0.05);border:1px solid #e2e8f0;'
            f'border-right:3px solid #f59e0b;">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
            f'<div style="font-size:1.05rem;font-weight:700;color:#0f172a;line-height:1.3;flex:1;">'
            f'[Watchlisted] {title}</div>'
            f'<div style="background:#0f172a;color:white;border-radius:10px;padding:0.3rem 0.6rem;'
            f'font-size:0.78rem;font-weight:700;margin-left:12px;">{score}/10</div>'
            f'</div>'
            f'<div style="font-size:0.82rem;color:#64748b;margin-top:0.3rem;">'
            f'{source} &middot; {date_str} &middot; {topic}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Compact info
        mc1, mc2, mc3 = st.columns(3)
        mc1.caption(f"Priority: **{priority}**")
        mc2.caption(f"Confidence: **{conf}**")
        mc3.caption(f"Risk: **{risk_val.title()}**")

        # Why matters & action
        for block_label, block_text in [("Why This Matters", why), ("Recommended Action", action)]:
            st.markdown(
                f'<div style="margin-top:0.3rem;padding:0.5rem 0.7rem;background:#f8fafc;'
                f'border-radius:8px;border:1px solid #f1f5f9;">'
                f'<div style="font-size:0.72rem;font-weight:700;color:#64748b;'
                f'text-transform:uppercase;letter-spacing:0.04em;margin-bottom:0.15rem;">'
                f'{block_label}</div>'
                f'<div style="font-size:0.86rem;color:#1e293b;line-height:1.55;">{block_text}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Note & remove
        nc1, nc2 = st.columns([3, 1])
        with nc1:
            existing_note = get_user_note(row_id)
            new_note = st.text_input(
                "Note", value=existing_note,
                key=f"wl-note-{row_id}",
                placeholder="Add a note...",
                label_visibility="collapsed",
            )
            if new_note != existing_note:
                save_user_note(row_id, new_note)
        with nc2:
            if st.button("Remove from Watchlist", key=f"rm-wl-{row_id}"):
                toggle_watchlist(row_id)
                st.rerun()

        st.divider()


# ================================================================
# VIEW: COMPARISON
# ================================================================
def render_comparison_view(filtered, client_type):
    st.subheader("Comparison View")

    if filtered.empty or "date" not in filtered.columns:
        st.info("Not enough data for comparison.")
        return

    dates = filtered["date"].dropna()
    if dates.empty:
        st.info("No date data available.")
        return

    min_date = dates.min().date()
    max_date = dates.max().date()
    mid_date = min_date + (max_date - min_date) / 2

    st.markdown("**Period Comparison**")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("*Period 1*")
        p1_start = st.date_input("Start", value=min_date, key="p1s")
        p1_end = st.date_input("End", value=mid_date, key="p1e")
    with c2:
        st.markdown("*Period 2*")
        p2_start = st.date_input("Start", value=mid_date + timedelta(days=1), key="p2s")
        p2_end = st.date_input("End", value=max_date, key="p2e")

    p1 = filtered[(filtered["date"].dt.date >= p1_start) & (filtered["date"].dt.date <= p1_end)]
    p2 = filtered[(filtered["date"].dt.date >= p2_start) & (filtered["date"].dt.date <= p2_end)]

    # Metrics comparison
    metrics = {
        "Total Updates": (len(p1), len(p2)),
        "Immediate": (
            int((p1["priority"] == "Immediate").sum()) if not p1.empty else 0,
            int((p2["priority"] == "Immediate").sum()) if not p2.empty else 0,
        ),
        "Avg Impact": (
            round(p1["impact_score"].mean(), 1) if not p1.empty else 0,
            round(p2["impact_score"].mean(), 1) if not p2.empty else 0,
        ),
        "High Risk": (
            int((p1["risk_level"].astype(str).str.lower() == "high").sum()) if not p1.empty else 0,
            int((p2["risk_level"].astype(str).str.lower() == "high").sum()) if not p2.empty else 0,
        ),
        "Avg Confidence": (
            round(p1["confidence_score"].mean(), 1) if not p1.empty else 0,
            round(p2["confidence_score"].mean(), 1) if not p2.empty else 0,
        ),
    }

    # Table using native Streamlit
    comp_data = []
    for name, (v1, v2) in metrics.items():
        diff = v2 - v1
        if diff > 0:
            change_str = f"+{diff}"
        elif diff < 0:
            change_str = f"{diff}"
        else:
            change_str = "0"
        comp_data.append({"Metric": name, "Period 1": v1, "Period 2": v2, "Change": change_str})

    st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)

    # Topic comparison chart
    if not p1.empty and not p2.empty and "topic" in filtered.columns:
        t1 = p1["topic"].value_counts().reset_index()
        t1.columns = ["topic", "Period 1"]
        t2 = p2["topic"].value_counts().reset_index()
        t2.columns = ["topic", "Period 2"]
        merged = t1.merge(t2, on="topic", how="outer").fillna(0)

        fig = go.Figure()
        fig.add_trace(go.Bar(name="Period 1", x=merged["topic"], y=merged["Period 1"], marker_color="#3b82f6"))
        fig.add_trace(go.Bar(name="Period 2", x=merged["topic"], y=merged["Period 2"], marker_color="#f59e0b"))
        fig.update_layout(barmode="group", title="Topic Distribution: Period 1 vs 2", margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    # Client type comparison
    st.markdown("**Client Type Comparison**")
    selected_clients = st.multiselect("Compare client types", CLIENT_TYPES, default=[client_type])

    if selected_clients and not filtered.empty:
        comp_rows = []
        for ct in selected_clients:
            temp = filtered.copy()
            temp["_impact"] = temp.apply(lambda r: calculate_impact_score(r, ct), axis=1)
            temp["_priority"] = temp["_impact"].apply(determine_priority)
            comp_rows.append({
                "Client Type": ct,
                "Avg Impact": round(temp["_impact"].mean(), 1),
                "Immediate": int((temp["_priority"] == "Immediate").sum()),
                "Review": int((temp["_priority"] == "Review").sum()),
                "Monitor": int((temp["_priority"] == "Monitor").sum()),
            })

        comp_df = pd.DataFrame(comp_rows)
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

        melted = comp_df.melt(
            id_vars="Client Type",
            value_vars=["Immediate", "Review", "Monitor"],
        )
        fig = px.bar(
            melted, x="Client Type", y="value", color="variable",
            barmode="group", title="Priority by Client Type",
            color_discrete_map=PRIORITY_COLORS,
        )
        fig.update_layout(margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)


# ================================================================
# APP INITIALIZATION
# ================================================================
ensure_data_dir()

# Auto refresh
auto_refresh_triggered = False
auto_refresh_message = None

if should_auto_refresh(LIVE_DATA_FILE, AUTO_REFRESH_MINUTES):
    try:
        refresh_live_data()
        auto_refresh_triggered = True
        auto_refresh_message = f"Auto-refresh completed (policy: every {AUTO_REFRESH_MINUTES} min)."
    except Exception:
        auto_refresh_message = "Auto-refresh failed. Showing existing data."

# Load watchlist & notes
if WATCHLIST_FILE.exists():
    st.session_state["watchlist"] = load_watchlist()
if NOTES_FILE.exists():
    st.session_state["user_notes"] = load_user_notes()

# Load data
combine_data.clear()
df = combine_data()

if not df.empty:
    df["confidence_score"] = df.apply(calculate_confidence_score, axis=1)


# ================================================================
# SIDEBAR
# ================================================================
with st.sidebar:
    st.markdown("### Controls")

    client_type = st.selectbox(
        "Client Type", CLIENT_TYPES,
        format_func=lambda x: f"{CLIENT_ICONS.get(x, '')} {x}",
    )

    view_mode = st.radio(
        "View",
        ["Overview", "Updates", "Analytics", "Reports", "Watchlist", "Comparison"],
    )

    st.divider()

    if st.button("Refresh Live Data", use_container_width=True):
        with st.spinner("Fetching from EFSA & RASFF..."):
            try:
                refresh_live_data()
                combine_data.clear()
                st.success("Live data refreshed.")
                st.rerun()
            except Exception as e:
                st.error(f"Refresh failed: {e}")

    last_updated_str = format_relative_update_time(LIVE_DATA_FILE)
    st.caption(f"Last updated: {last_updated_str}")

    # AI status
    try:
        has_openrouter = bool(st.secrets.get("OPENROUTER_API_KEY", ""))
    except Exception:
        has_openrouter = False

    if has_openrouter:
        st.success("OpenRouter connected")
    else:
        st.info("Local AI mode")

    st.divider()
    st.markdown("**Filters**")

    # Filter defaults
    selected_sources = []
    selected_topics = []
    selected_risks = []
    data_mode = "All"
    min_confidence = 0
    date_range = None

    if not df.empty:
        src_opts = sorted(df["source"].dropna().astype(str).unique().tolist()) if "source" in df.columns else []
        topic_opts = sorted(df["topic"].dropna().astype(str).unique().tolist()) if "topic" in df.columns else []
        risk_opts = sorted(df["risk_level"].dropna().astype(str).unique().tolist()) if "risk_level" in df.columns else []

        selected_sources = st.multiselect("Source", src_opts, default=src_opts)
        selected_topics = st.multiselect("Topic", topic_opts, default=topic_opts)
        selected_risks = st.multiselect("Risk Level", risk_opts, default=risk_opts)
        data_mode = st.radio("Data Mode", ["All", "Live Only", "Fallback Only"], horizontal=True)
        min_confidence = st.slider("Min Confidence", 0, 100, 0, 5)

        if "date" in df.columns:
            valid_dates = df["date"].dropna()
            if not valid_dates.empty:
                min_d = valid_dates.min().date()
                max_d = valid_dates.max().date()
                date_range = st.date_input("Date Range", value=(min_d, max_d), min_value=min_d, max_value=max_d)

    wl_count = len(st.session_state.get("watchlist", []))
    if wl_count:
        st.caption(f"Watchlist: {wl_count} item(s)")


# ================================================================
# MAIN AREA
# ================================================================
render_hero(client_type, view_mode, last_updated_str, df)

if auto_refresh_message:
    if auto_refresh_triggered:
        st.success(auto_refresh_message)
    else:
        st.warning(auto_refresh_message)

render_client_strip(client_type)
render_intro_cards()

if df.empty:
    st.warning("No data found. Click Refresh Live Data in the sidebar.")
    st.stop()

# ================================================================
# APPLY FILTERS
# ================================================================
filtered = df.copy()

if selected_sources and "source" in filtered.columns:
    filtered = filtered[filtered["source"].isin(selected_sources)]

if selected_topics and "topic" in filtered.columns:
    filtered = filtered[filtered["topic"].isin(selected_topics)]

if selected_risks and "risk_level" in filtered.columns:
    filtered = filtered[filtered["risk_level"].isin(selected_risks)]

if data_mode == "Live Only" and "source_status" in filtered.columns:
    filtered = filtered[filtered["source_status"].astype(str).str.lower() == "live"]
elif data_mode == "Fallback Only" and "source_status" in filtered.columns:
    filtered = filtered[filtered["source_status"].astype(str).str.lower() == "fallback"]

if "confidence_score" in filtered.columns:
    filtered = filtered[filtered["confidence_score"] >= min_confidence]

if date_range and len(date_range) == 2 and "date" in filtered.columns:
    start_d, end_d = date_range
    date_mask = filtered["date"].dt.date.between(start_d, end_d)
    filtered = filtered[date_mask.fillna(False)]

# Calculate consulting fields
if not filtered.empty:
    filtered = filtered.copy()
    filtered["impact_score"] = filtered.apply(lambda r: calculate_impact_score(r, client_type), axis=1)
    filtered["priority"] = filtered["impact_score"].apply(determine_priority)
    filtered["why_this_matters"] = filtered.apply(lambda r: why_this_matters(r, client_type), axis=1)

# ================================================================
# ROUTE TO VIEW
# ================================================================
if view_mode == "Overview":
    render_overview(filtered, client_type)
elif view_mode == "Updates":
    render_updates(filtered, client_type)
elif view_mode == "Analytics":
    render_analytics_section(filtered)
elif view_mode == "Reports":
    render_reports(filtered, client_type)
elif view_mode == "Watchlist":
    render_watchlist_view(filtered, client_type)
elif view_mode == "Comparison":
    render_comparison_view(filtered, client_type)

# ================================================================
# FOOTER
# ================================================================
st.divider()
st.caption(
    "Food Regulatory Intelligence Dashboard v2.0 | "
    "Regulatory horizon scanning, client intelligence, consulting outputs, analytics"
)
    
