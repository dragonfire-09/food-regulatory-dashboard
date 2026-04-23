import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from io import BytesIO
import hashlib

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors as rl_colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from scrapers.efsa_rss_scraper import fetch_efsa_updates
from scrapers.rasff_scraper import fetch_rasff_updates

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="Food Regulatory Intelligence Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== CONSTANTS ==========
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


# ========== SESSION STATE INIT ==========
def init_session_state():
    defaults = {
        "watchlist": [],
        "user_notes": {},
        "comparison_mode": False,
        "dark_mode": False,
        "notification_queue": [],
        "last_view": "Overview",
        "search_history": [],
        "dismissed_alerts": set(),
        "ai_cache": {},
        "filter_presets": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


# ========== CSS ==========
def get_theme_css():
    return """
    <style>
        /* ===== ROOT & LAYOUT ===== */
        .main { background-color: #f8fafc; }

        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }

        /* ===== HERO ===== */
        .hero-box {
            background: linear-gradient(135deg, #0b1220 0%, #1e3a5f 40%, #1d4ed8 100%);
            padding: 1.6rem 2rem 1.3rem 2rem;
            border-radius: 20px;
            color: white;
            margin-bottom: 1rem;
            box-shadow: 0 20px 40px rgba(15, 23, 42, 0.25);
            position: relative;
            overflow: hidden;
        }

        .hero-box::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -20%;
            width: 400px;
            height: 400px;
            border-radius: 50%;
            background: rgba(255,255,255,0.03);
        }

        .hero-topline {
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #93c5fd;
            margin-bottom: 0.4rem;
        }

        .hero-title {
            font-size: 1.9rem;
            font-weight: 800;
            margin-bottom: 0.25rem;
            line-height: 1.15;
        }

        .hero-subtitle {
            font-size: 0.92rem;
            color: #dbeafe;
            margin-bottom: 0.4rem;
            line-height: 1.5;
            max-width: 800px;
        }

        .hero-stats {
            display: flex;
            gap: 24px;
            margin-top: 0.6rem;
        }

        .hero-stat {
            text-align: center;
        }

        .hero-stat-value {
            font-size: 1.5rem;
            font-weight: 800;
            color: #fff;
        }

        .hero-stat-label {
            font-size: 0.7rem;
            color: #93c5fd;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* ===== CLIENT STRIP ===== */
        .client-strip {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 0.8rem;
        }

        .client-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: white;
            border: 1.5px solid #e2e8f0;
            color: #475569;
            border-radius: 999px;
            padding: 0.45rem 0.85rem;
            font-size: 0.82rem;
            font-weight: 600;
            transition: all 0.2s ease;
            cursor: default;
        }

        .client-chip-active {
            background: linear-gradient(135deg, #dbeafe 0%, #ede9fe 100%);
            border: 1.5px solid #818cf8;
            color: #1e3a8a;
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
            font-weight: 700;
        }

        /* ===== METRIC CARDS ===== */
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 1rem;
        }

        .metric-card {
            background: white;
            border-radius: 16px;
            padding: 1rem 1.1rem;
            box-shadow: 0 2px 12px rgba(15, 23, 42, 0.06);
            border: 1px solid #e2e8f0;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }

        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.1);
        }

        .metric-label {
            font-size: 0.78rem;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.2rem;
        }

        .metric-value {
            font-size: 1.6rem;
            font-weight: 800;
            color: #0f172a;
        }

        .metric-delta {
            font-size: 0.75rem;
            font-weight: 600;
            margin-top: 0.15rem;
        }

        .metric-delta-up { color: #dc2626; }
        .metric-delta-down { color: #16a34a; }
        .metric-delta-neutral { color: #64748b; }

        /* ===== SECTION HEADERS ===== */
        .section-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 1.2rem;
            margin-bottom: 0.8rem;
        }

        .section-title {
            font-size: 1.1rem;
            font-weight: 800;
            color: #0f172a;
            margin: 0;
        }

        .section-badge {
            background: #e0f2fe;
            color: #0369a1;
            border-radius: 999px;
            padding: 0.2rem 0.6rem;
            font-size: 0.72rem;
            font-weight: 700;
        }

        /* ===== UPDATE CARDS ===== */
        .update-card {
            background: white;
            border-radius: 16px;
            padding: 1.1rem 1.2rem;
            box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
            border: 1px solid #e2e8f0;
            margin-bottom: 0.8rem;
            transition: all 0.2s ease;
            position: relative;
        }

        .update-card:hover {
            box-shadow: 0 8px 28px rgba(15, 23, 42, 0.09);
        }

        .update-card.high-risk {
            border-left: 5px solid #dc2626;
        }

        .update-card.medium-risk {
            border-left: 5px solid #f97316;
        }

        .update-card.low-risk {
            border-left: 5px solid #16a34a;
        }

        .update-card.watchlisted {
            background: linear-gradient(135deg, #fffbeb 0%, #ffffff 100%);
            border-right: 3px solid #f59e0b;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 0.5rem;
        }

        .update-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.3;
            flex: 1;
        }

        .card-score-badge {
            background: #0f172a;
            color: white;
            border-radius: 10px;
            padding: 0.3rem 0.6rem;
            font-size: 0.78rem;
            font-weight: 700;
            white-space: nowrap;
            margin-left: 12px;
        }

        .meta-row {
            font-size: 0.82rem;
            color: #64748b;
            margin-bottom: 0.4rem;
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            align-items: center;
        }

        .meta-separator {
            color: #cbd5e1;
        }

        /* ===== PILLS ===== */
        .pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 0.5rem 0;
        }

        .pill {
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 700;
        }

        .pill-topic { background: #e0f2fe; color: #0369a1; }
        .pill-source { background: #eef2ff; color: #4338ca; }
        .pill-risk-high { background: #fee2e2; color: #b91c1c; }
        .pill-risk-medium { background: #ffedd5; color: #c2410c; }
        .pill-risk-low { background: #dcfce7; color: #15803d; }
        .pill-priority-immediate { background: #fee2e2; color: #991b1b; }
        .pill-priority-review { background: #fef3c7; color: #92400e; }
        .pill-priority-monitor { background: #dbeafe; color: #1d4ed8; }
        .pill-confidence-high { background: #dcfce7; color: #166534; }
        .pill-confidence-medium { background: #fef3c7; color: #92400e; }
        .pill-confidence-low { background: #fee2e2; color: #991b1b; }
        .pill-live { background: #d1fae5; color: #065f46; }
        .pill-fallback { background: #fef3c7; color: #92400e; }
        .pill-watchlist { background: #fef3c7; color: #92400e; }

        /* ===== CONTENT BLOCKS ===== */
        .content-block {
            margin-top: 0.6rem;
            padding: 0.6rem 0.8rem;
            background: #f8fafc;
            border-radius: 10px;
            border: 1px solid #f1f5f9;
        }

        .content-block-title {
            font-size: 0.76rem;
            font-weight: 700;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.25rem;
        }

        .content-block-text {
            font-size: 0.88rem;
            color: #1e293b;
            line-height: 1.55;
        }

        /* ===== URGENT CARDS ===== */
        .urgent-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 12px;
            margin-bottom: 1rem;
        }

        .urgent-card {
            background: white;
            border-radius: 16px;
            padding: 1rem;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
            transition: transform 0.15s ease;
        }

        .urgent-card:hover {
            transform: translateY(-2px);
        }

        .urgent-card.rank-1 {
            border-top: 4px solid #dc2626;
        }

        .urgent-card.rank-2 {
            border-top: 4px solid #f97316;
        }

        .urgent-card.rank-3 {
            border-top: 4px solid #eab308;
        }

        .urgent-number {
            font-size: 2rem;
            font-weight: 800;
            color: #e2e8f0;
            float: right;
            line-height: 1;
        }

        .urgent-title {
            font-size: 0.95rem;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 0.3rem;
            line-height: 1.3;
        }

        .urgent-meta {
            font-size: 0.78rem;
            color: #64748b;
            margin-bottom: 0.4rem;
        }

        /* ===== INSIGHT BOX ===== */
        .insight-box {
            background: linear-gradient(135deg, #f0f9ff 0%, #f5f3ff 100%);
            border-radius: 16px;
            padding: 1.2rem;
            border: 1px solid #e0e7ff;
            margin-bottom: 1rem;
        }

        .insight-headline {
            font-size: 1rem;
            font-weight: 700;
            color: #1e293b;
            margin-bottom: 0.6rem;
            line-height: 1.4;
        }

        .insight-detail {
            font-size: 0.88rem;
            color: #475569;
            line-height: 1.55;
            margin-bottom: 0.4rem;
        }

        .insight-label {
            font-weight: 700;
            color: #334155;
        }

        /* ===== REPORT BOX ===== */
        .report-box {
            background: white;
            border-radius: 16px;
            padding: 1rem;
            border: 1px solid #e2e8f0;
            box-shadow: 0 2px 8px rgba(15,23,42,0.04);
            margin-bottom: 1rem;
        }

        /* ===== INTRO GRID ===== */
        .intro-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 1rem;
        }

        .intro-card {
            background: white;
            border-radius: 14px;
            padding: 0.9rem 1rem;
            border: 1px solid #e2e8f0;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
        }

        .intro-icon {
            font-size: 1.4rem;
            margin-bottom: 0.3rem;
        }

        .intro-title {
            font-size: 0.88rem;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 0.25rem;
        }

        .intro-text {
            font-size: 0.82rem;
            color: #475569;
            line-height: 1.5;
        }

        /* ===== NOTIFICATION TOAST ===== */
        .toast {
            position: fixed;
            top: 80px;
            right: 20px;
            z-index: 9999;
            background: white;
            border-radius: 12px;
            padding: 0.8rem 1.2rem;
            box-shadow: 0 12px 40px rgba(15, 23, 42, 0.15);
            border-left: 4px solid #3b82f6;
            animation: slideIn 0.3s ease-out;
            max-width: 360px;
        }

        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        /* ===== COMPARISON TABLE ===== */
        .comparison-table {
            width: 100%;
            border-collapse: collapse;
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 1rem;
        }

        .comparison-table th {
            background: #f1f5f9;
            padding: 0.6rem 0.8rem;
            text-align: left;
            font-size: 0.78rem;
            font-weight: 700;
            color: #475569;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .comparison-table td {
            padding: 0.5rem 0.8rem;
            border-bottom: 1px solid #f1f5f9;
            font-size: 0.85rem;
            color: #1e293b;
        }

        /* ===== DATA BADGES ===== */
        .data-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 0.68rem;
            font-weight: 700;
            margin-bottom: 6px;
        }

        .badge-live { background: rgba(16, 185, 129, 0.12); color: #059669; }
        .badge-fallback { background: rgba(245, 158, 11, 0.12); color: #b45309; }
        .badge-unknown { background: rgba(156, 163, 175, 0.12); color: #6b7280; }

        /* ===== WATCHLIST BUTTON ===== */
        .watchlist-indicator {
            position: absolute;
            top: 10px;
            right: 10px;
            font-size: 1.2rem;
            cursor: pointer;
        }

        /* ===== SIDEBAR ===== */
        .stSidebar { background-color: #fafbfc; }

        .sidebar-section-title {
            font-size: 0.72rem;
            font-weight: 700;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-top: 1rem;
            margin-bottom: 0.4rem;
        }

        /* ===== BUTTONS ===== */
        .stButton button {
            border-radius: 10px;
            border: 1px solid #e2e8f0;
            background: white;
            color: #0f172a;
            font-weight: 600;
            font-size: 0.82rem;
            transition: all 0.15s ease;
        }

        .stButton button:hover {
            border-color: #3b82f6;
            color: #1d4ed8;
        }

        .stDownloadButton button {
            border-radius: 10px;
            font-weight: 600;
        }

        /* ===== TAB STYLE ===== */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 8px;
            padding: 0.5rem 1rem;
            font-weight: 600;
        }

        /* ===== TIMELINE ===== */
        .timeline-item {
            display: flex;
            gap: 12px;
            margin-bottom: 0.6rem;
            padding-bottom: 0.6rem;
            border-bottom: 1px solid #f1f5f9;
        }

        .timeline-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-top: 5px;
            flex-shrink: 0;
        }

        .timeline-content {
            flex: 1;
        }

        .timeline-title {
            font-size: 0.85rem;
            font-weight: 600;
            color: #1e293b;
        }

        .timeline-meta {
            font-size: 0.75rem;
            color: #94a3b8;
        }

        /* ===== RESPONSIVE ===== */
        @media (max-width: 768px) {
            .intro-grid { grid-template-columns: 1fr; }
            .urgent-grid { grid-template-columns: 1fr; }
            .metric-grid { grid-template-columns: repeat(2, 1fr); }
            .hero-title { font-size: 1.4rem; }
            .hero-stats { flex-wrap: wrap; gap: 12px; }
        }
    </style>
    """


st.markdown(get_theme_css(), unsafe_allow_html=True)


# ========== OPENROUTER ==========
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


# ========== FILE HELPERS ==========
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
    required_defaults = {
        "source_status": "unknown",
        "fetch_method": "n/a",
        "notification_reference": "n/a",
        "last_verified": "n/a",
        "jurisdiction": "Unknown",
    }
    for field, default in required_defaults.items():
        if field not in df.columns:
            df[field] = default
    return df


@st.cache_data(ttl=300)
def combine_data():
    base_records = load_json_records(BASE_DATA_FILE)
    live_records = load_json_records(LIVE_DATA_FILE)
    all_records = live_records + base_records

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df = ensure_metadata_fields(df)

    dedupe_cols = [c for c in ["title", "source", "date"] if c in df.columns]
    if dedupe_cols:
        df = df.drop_duplicates(subset=dedupe_cols, keep="first")

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Generate stable IDs
    if "id" not in df.columns:
        df["id"] = df.apply(
            lambda r: hashlib.md5(
                f"{r.get('title', '')}{r.get('source', '')}{r.get('date', '')}".encode()
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
    now = datetime.now(timezone.utc)
    return int((now - updated).total_seconds() // 60)


def format_relative_update_time(path: Path):
    mins = minutes_since_update(path)
    if mins is None:
        return "never"
    if mins < 1:
        return "just now"
    if mins == 1:
        return "1 min ago"
    if mins < 60:
        return f"{mins} min ago"
    hours = mins // 60
    if hours == 1:
        return "1 hr ago"
    if hours < 24:
        return f"{hours} hrs ago"
    days = hours // 24
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def should_auto_refresh(path: Path, max_age_minutes: int):
    if not path.exists():
        return True
    mins = minutes_since_update(path)
    if mins is None:
        return True
    return mins >= max_age_minutes


# ========== WATCHLIST ==========
def load_watchlist():
    return load_json_records(WATCHLIST_FILE)


def save_watchlist(watchlist):
    save_json_records(WATCHLIST_FILE, watchlist)


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


# ========== USER NOTES ==========
def load_user_notes():
    return {str(k): v for k, v in (load_json_records(NOTES_FILE) if NOTES_FILE.exists() else {}).items()} if NOTES_FILE.exists() else {}


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


# ========== DISPLAY HELPERS ==========
def safe_value(val, default="n/a"):
    if val is None:
        return default
    if isinstance(val, float) and pd.isna(val):
        return default
    if str(val).lower() in ["nan", "none", ""]:
        return default
    return val


def format_date(value):
    if pd.isna(value):
        return "Unknown"
    try:
        return pd.to_datetime(value).strftime("%b %d, %Y")
    except Exception:
        return str(value)


def format_date_short(value):
    if pd.isna(value):
        return "—"
    try:
        return pd.to_datetime(value).strftime("%m/%d")
    except Exception:
        return str(value)


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
    p = str(priority).lower()
    if p == "immediate":
        return "pill pill-priority-immediate"
    if p == "review":
        return "pill pill-priority-review"
    return "pill pill-priority-monitor"


def confidence_class(score: int):
    if score >= 85:
        return "pill pill-confidence-high"
    if score >= 60:
        return "pill pill-confidence-medium"
    return "pill pill-confidence-low"


def source_status_pill(status: str):
    status = str(status).strip().lower()
    if status == "live":
        return '<span class="pill pill-live">● Live</span>'
    if status == "fallback":
        return '<span class="pill pill-fallback">● Fallback</span>'
    return '<span class="pill" style="background:#f1f5f9;color:#94a3b8;">● Unknown</span>'


def build_data_badge_html(source_status: str):
    status = str(source_status).lower()
    if status == "live":
        return '<span class="data-badge badge-live">● LIVE DATA</span>'
    if status == "fallback":
        return '<span class="data-badge badge-fallback">● FALLBACK</span>'
    return '<span class="data-badge badge-unknown">● UNKNOWN</span>'


def score_bar_html(score, max_score=10):
    pct = min(score / max_score * 100, 100)
    if score >= 8:
        color = "#dc2626"
    elif score >= 5:
        color = "#f59e0b"
    else:
        color = "#3b82f6"
    return f"""
    <div style="display:flex;align-items:center;gap:8px;">
        <div style="flex:1;background:#f1f5f9;border-radius:999px;height:6px;overflow:hidden;">
            <div style="width:{pct}%;background:{color};height:100%;border-radius:999px;"></div>
        </div>
        <span style="font-size:0.82rem;font-weight:700;color:{color};">{score}/{max_score}</span>
    </div>
    """


def sanitize_filename(value: str) -> str:
    value = value.lower().strip()
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        value = value.replace(ch, "-")
    value = value.replace(" ", "_")
    return value[:80]


# ========== PDF HELPERS ==========
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


def build_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    export_cols = [c for c in [
        "title", "source", "date", "topic", "risk_level", "jurisdiction",
        "impact_score", "priority", "confidence_score", "source_status",
        "ai_summary", "business_impact", "recommended_action",
        "why_this_matters", "notification_reference", "url",
    ] if c in df.columns]

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df[export_cols].to_excel(writer, index=False, sheet_name="Regulatory Updates")
    buffer.seek(0)
    return buffer.read()


# ========== SCORING & CONSULTING ==========
def calculate_confidence_score(row):
    status = str(safe_value(row.get("source_status"), "unknown")).lower()
    method = str(safe_value(row.get("fetch_method"), "n/a")).lower()
    reference = str(safe_value(row.get("notification_reference"), "n/a")).lower()

    if status == "live" and method == "detail_page" and reference != "n/a":
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

    client_bonus = {
        "Exporter": ["labeling", "contaminants", "traceability"],
        "Retailer": ["labeling", "fraud", "contaminants"],
        "Importer": ["traceability", "contaminants", "fraud"],
        "SME Food Producer": ["labeling", "food safety", "novel foods"],
        "Startup": ["novel foods", "labeling"],
    }

    if topic in client_bonus.get(client_type, []):
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
            "Labeling": "May affect export labeling compliance, destination-market documentation, and shipment readiness.",
            "Contaminants": "May affect border acceptance, product testing exposure, and supplier risk in export channels.",
            "Traceability": "May affect documentation continuity across jurisdictions and importer confidence.",
        },
        "Retailer": {
            "Labeling": "May affect on-shelf compliance, consumer information accuracy, and private-label exposure.",
            "Fraud": "May affect brand integrity, product claims, and supplier verification requirements.",
            "Contaminants": "May increase recall risk and require rapid coordination with suppliers and QA teams.",
        },
        "Importer": {
            "Traceability": "May affect inbound documentation quality and product release decisions.",
            "Contaminants": "May increase batch-hold, testing, and customs-related review requirements.",
        },
        "Startup": {
            "Novel Foods": "May shape market-entry timing, product claims, and commercialization planning.",
            "Labeling": "May affect packaging design and compliance assumptions in early-stage go-to-market.",
        },
        "SME Food Producer": {
            "Labeling": "May require packaging review, internal sign-off changes, and updated label controls.",
            "Food Safety": "May affect QA workflows, specifications, and operational risk exposure.",
        },
    }

    client_reasons = reasons.get(client_type, {})
    if topic in client_reasons:
        return client_reasons[topic]

    if risk == "high":
        return "Commercially material — may require immediate cross-functional review."
    if risk == "low":
        return "Lower urgency — useful for horizon scanning and future planning."
    return "May affect compliance planning, supply chain review, and internal decisions."


def client_adjusted_action(base_action, client_type, topic, priority):
    extras = {
        "Exporter": "Check destination-country implications, export documentation, and border exposure.",
        "Retailer": "Assess shelf impact, supplier exposure, and any recall or customer-facing implications.",
        "Importer": "Review supplier documentation, inbound controls, and traceability completeness.",
        "Startup": "Assess product-market fit implications, packaging assumptions, and authorization timing.",
    }
    extra = extras.get(client_type, "Review internal QA, regulatory, and production implications.")
    return f"{base_action} {extra}"


# ========== AI ANALYSIS ==========
def local_ai_fallback(row, client_type):
    title = str(row.get("title", "Regulatory update"))
    topic = str(row.get("topic", "Food Safety"))
    source = str(row.get("source", "Regulatory source"))
    risk = str(row.get("risk_level", "Medium")).lower()
    existing_summary = str(row.get("ai_summary", ""))

    base_summary = existing_summary if existing_summary else f"This update relates to {topic.lower()} and may require compliance review."

    title_lower = title.lower()
    topic_lower = topic.lower()

    analysis_map = {
        "label": {
            "impact": "Food businesses may need to review packaging, declarations, and label approval workflows.",
            "action": "Review current labels, compare against the update, and prepare packaging revisions if needed.",
        },
        "traceability": {
            "impact": "Operators may need stronger product tracking, recordkeeping, and data coordination.",
            "action": "Assess traceability records, supplier data quality, and system readiness.",
        },
        "contaminant": {
            "impact": "There may be increased recall exposure, supplier scrutiny, and regulatory risk.",
            "action": "Check affected products or batches, review supplier controls, and prepare risk assessment.",
        },
        "fraud": {
            "impact": "Authentication, origin claims, and documentary controls may face closer scrutiny.",
            "action": "Review provenance records, product claims, and internal documentation controls.",
        },
        "novel": {
            "impact": "May create product development opportunities, but authorization timing must be assessed.",
            "action": "Review eligibility, product formulation, and approval timing.",
        },
    }

    impact = "This update may affect compliance planning, review processes, and documentation."
    action = "Review internally and determine whether legal, quality, or supply chain teams need to respond."

    for keyword, content in analysis_map.items():
        if keyword in title_lower or keyword in topic_lower:
            impact = content["impact"]
            action = content["action"]
            break

    if risk == "high":
        impact = "Commercially significant — may require immediate compliance escalation and market action."
        action = "Prioritize immediate internal review, identify affected products, and prepare rapid response."
    elif risk == "low":
        impact = "Lower urgency — relevant for horizon scanning and future compliance planning."
        action = "Log the update, monitor developments, and review in the next compliance cycle."

    action = client_adjusted_action(action, client_type, topic, "Review")

    return {
        "ai_summary": f"{base_summary} Source: {source}.",
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
        prompt = f"""
You are a food regulatory intelligence analyst.
Return VALID JSON ONLY with keys: ai_summary, business_impact, recommended_action.
Client type: {client_type}.

Update:
Title: {safe_value(row.get('title'))}
Source: {safe_value(row.get('source'))}
Topic: {safe_value(row.get('topic'))}
Jurisdiction: {safe_value(row.get('jurisdiction'))}
Summary: {safe_value(row.get('ai_summary'))}
Raw: {safe_value(row.get('raw_text'))}
"""
        result = None
        for model_name in OPENROUTER_MODELS:
            try:
                text = try_openrouter_model(client, model_name, prompt)
                parsed = extract_json_block(text)
                result = {
                    "ai_summary": parsed.get("ai_summary", "No summary available."),
                    "business_impact": parsed.get("business_impact", "No impact available."),
                    "recommended_action": parsed.get("recommended_action", "No action available."),
                    "_model_used": model_name,
                }
                break
            except Exception:
                continue

        if result is None:
            result = local_ai_fallback(row, client_type)

    st.session_state.setdefault("ai_cache", {})[cache_key] = result
    return result


# ========== REPORTS ==========
def generate_weekly_report(df, client_type):
    if df.empty:
        return "No updates available."

    report_df = df.sort_values("impact_score", ascending=False)
    top_items = report_df.head(5)

    lines = [
        "═" * 60,
        "  WEEKLY REGULATORY INTELLIGENCE REPORT",
        "═" * 60,
        "",
        f"  Client Type: {client_type}",
        f"  Generated:   {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"  Updates:     {len(report_df)}",
        "",
        "─" * 60,
        "  EXECUTIVE SUMMARY",
        "─" * 60,
        f"  • Immediate priority: {(report_df['priority'] == 'Immediate').sum()}",
        f"  • Review items:       {(report_df['priority'] == 'Review').sum()}",
        f"  • Monitor items:      {(report_df['priority'] == 'Monitor').sum()}",
        "",
        "─" * 60,
        "  TOP PRIORITY UPDATES",
        "─" * 60,
    ]

    for i, (_, row) in enumerate(top_items.iterrows(), 1):
        lines.append(f"\n  {i}. {row.get('title', 'Untitled')}")
        lines.append(f"     Source: {row.get('source', 'Unknown')} | Date: {format_date(row.get('date'))}")
        lines.append(f"     Score: {row.get('impact_score', 0)}/10 | Priority: {row.get('priority', 'Monitor')}")
        lines.append(f"     Why: {row.get('why_this_matters', '')}")
        lines.append(f"     Action: {row.get('recommended_action', '')}")

    lines.extend(["", "═" * 60])
    return "\n".join(lines)


def build_full_report(df, client_type):
    if df.empty:
        return "No data available."

    df = df.sort_values("impact_score", ascending=False)

    lines = [
        "═" * 60,
        "  FULL REGULATORY INTELLIGENCE REPORT",
        "═" * 60,
        "",
        f"  Client Type: {client_type}",
        f"  Generated:   {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"  Total:       {len(df)}",
        "",
    ]

    for _, row in df.iterrows():
        lines.append(f"  ▸ {row.get('title', 'Untitled')}")
        lines.append(f"    Source: {row.get('source', 'Unknown')} | {format_date(row.get('date'))}")
        lines.append(f"    Priority: {row.get('priority', 'Monitor')} | Score: {row.get('impact_score', 0)}/10")
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

    sorted_df = df.sort_values("impact_score", ascending=False)
    top_row = sorted_df.iloc[0]
    top_topic = sorted_df["topic"].mode().iloc[0] if not sorted_df["topic"].mode().empty else "Food Safety"

    immediate_count = (sorted_df["priority"] == "Immediate").sum()
    high_risk_count = (sorted_df["risk_level"].astype(str).str.lower() == "high").sum()

    headline = (
        f"For {client_type.lower()}s: {immediate_count} immediate-priority item(s), "
        f"{high_risk_count} high-risk update(s), concentrated around {top_topic.lower()}."
    )

    focus_map = {
        "Exporter": "Border-facing documentation, destination-market compliance, and supplier risk visibility.",
        "Retailer": "Shelf compliance, supplier coordination, and consumer-facing risk exposure.",
        "Importer": "Inbound controls, traceability completeness, and batch-level documentation.",
        "Startup": "Packaging assumptions, market-entry timing, and regulatory readiness.",
    }
    operational_focus = focus_map.get(client_type, "Internal QA, compliance review, and product documentation.")

    return {
        "headline": headline,
        "key_risk": f"Highest-impact: {top_row.get('title', 'Untitled')}",
        "operational_focus": operational_focus,
        "recommended_next_step": "Start with top-priority item, align the affected team, convert to an internal action note.",
        "trend_direction": "up" if immediate_count > 2 else ("stable" if immediate_count > 0 else "down"),
    }


def build_client_alert(row, client_type, impact_score, priority, why_matters):
    return f"""Subject: Regulatory Update – {row.get('title', 'Update')}

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


# ========== ANALYTICS ==========
def build_analytics_frames(df):
    frames = {}
    if df.empty:
        return frames

    work = df.copy()
    if "date" in work.columns:
        work["date_only"] = pd.to_datetime(work["date"], errors="coerce").dt.date

    col_pairs = [
        ("source", "source_counts"),
        ("topic", "topic_counts"),
        ("priority", "priority_counts"),
        ("risk_level", "risk_counts"),
        ("source_status", "status_counts"),
    ]
    for col, key in col_pairs:
        if col in work.columns:
            vc = work[col].astype(str).str.title().value_counts().reset_index()
            vc.columns = [col, "count"]
            frames[key] = vc

    if "date_only" in work.columns:
        trend = work.groupby("date_only").size().reset_index(name="count")
        trend["date_only"] = pd.to_datetime(trend["date_only"])
        frames["trend"] = trend.sort_values("date_only")

    if "impact_score" in work.columns and "topic" in work.columns:
        score_topic = work.groupby("topic", dropna=False)["impact_score"].mean().round(2).reset_index()
        frames["score_by_topic"] = score_topic.sort_values("impact_score", ascending=False)

    if "confidence_score" in work.columns and "source" in work.columns:
        conf_src = work.groupby("source", dropna=False)["confidence_score"].mean().round(2).reset_index()
        frames["confidence_by_source"] = conf_src.sort_values("confidence_score", ascending=False)

    if "impact_score" in work.columns and "confidence_score" in work.columns:
        frames["scatter_data"] = work[["title", "impact_score", "confidence_score", "risk_level", "topic", "source"]].copy()

    if "topic" in work.columns and "risk_level" in work.columns:
        heatmap = work.groupby(["topic", "risk_level"]).size().reset_index(name="count")
        frames["heatmap_data"] = heatmap

    if "jurisdiction" in work.columns:
        jur = work["jurisdiction"].astype(str).value_counts().reset_index()
        jur.columns = ["jurisdiction", "count"]
        frames["jurisdiction_counts"] = jur[jur["jurisdiction"] != "Unknown"].head(15)

    return frames


def render_analytics_section(filtered):
    if filtered.empty:
        st.info("No data available for analytics.")
        return

    frames = build_analytics_frames(filtered)

    # KPI row
    st.markdown('<div class="section-header"><div class="section-title">📊 Analytics Dashboard</div></div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Distribution", "🔥 Heatmap & Scatter", "📅 Trends", "🌍 Geography"])

    with tab1:
        c1, c2 = st.columns(2)

        if "source_counts" in frames:
            fig = px.bar(
                frames["source_counts"], x="source", y="count",
                title="Updates by Source",
                color="count", color_continuous_scale="Blues",
            )
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c1.plotly_chart(fig, use_container_width=True)

        if "topic_counts" in frames:
            fig = px.pie(
                frames["topic_counts"], names="topic", values="count",
                title="Topic Distribution", hole=0.4,
            )
            fig.update_layout(margin=dict(t=40, b=20))
            c2.plotly_chart(fig, use_container_width=True)

        c3, c4 = st.columns(2)

        if "priority_counts" in frames:
            df_p = frames["priority_counts"]
            fig = px.bar(
                df_p, x="priority", y="count", title="Priority Distribution",
                color="priority",
                color_discrete_map={"Immediate": "#dc2626", "Review": "#f59e0b", "Monitor": "#3b82f6"},
            )
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c3.plotly_chart(fig, use_container_width=True)

        if "risk_counts" in frames:
            df_r = frames["risk_counts"]
            fig = px.bar(
                df_r, x="risk_level", y="count", title="Risk Distribution",
                color="risk_level",
                color_discrete_map={"High": "#dc2626", "Medium": "#f59e0b", "Low": "#16a34a"},
            )
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c4.plotly_chart(fig, use_container_width=True)

        c5, c6 = st.columns(2)

        if "score_by_topic" in frames:
            fig = px.bar(
                frames["score_by_topic"], x="topic", y="impact_score",
                title="Avg. Impact Score by Topic",
                color="impact_score", color_continuous_scale="OrRd",
            )
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c5.plotly_chart(fig, use_container_width=True)

        if "confidence_by_source" in frames:
            fig = px.bar(
                frames["confidence_by_source"], x="source", y="confidence_score",
                title="Avg. Confidence by Source",
                color="confidence_score", color_continuous_scale="Greens",
            )
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c6.plotly_chart(fig, use_container_width=True)

    with tab2:
        if "heatmap_data" in frames:
            hm = frames["heatmap_data"]
            hm_pivot = hm.pivot_table(index="topic", columns="risk_level", values="count", fill_value=0)
            fig = px.imshow(
                hm_pivot, text_auto=True, aspect="auto",
                title="Topic × Risk Level Heatmap",
                color_continuous_scale="YlOrRd",
            )
            fig.update_layout(margin=dict(t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)

        if "scatter_data" in frames:
            sdf = frames["scatter_data"]
            fig = px.scatter(
                sdf, x="impact_score", y="confidence_score",
                color="risk_level", hover_data=["title", "source", "topic"],
                title="Impact vs. Confidence Scatter",
                color_discrete_map={"High": "#dc2626", "Medium": "#f59e0b", "Low": "#16a34a"},
                size_max=12,
            )
            fig.update_layout(margin=dict(t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        if "trend" in frames and not frames["trend"].empty:
            fig = px.area(
                frames["trend"], x="date_only", y="count",
                title="Update Volume Over Time",
                markers=True,
            )
            fig.update_layout(margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No time-series data available.")

        if "status_counts" in frames:
            fig = px.pie(
                frames["status_counts"], names="source_status", values="count",
                title="Data Source Status", hole=0.4,
                color_discrete_map={"Live": "#10b981", "Fallback": "#f59e0b", "Unknown": "#94a3b8"},
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab4:
        if "jurisdiction_counts" in frames and not frames["jurisdiction_counts"].empty:
            fig = px.bar(
                frames["jurisdiction_counts"], x="jurisdiction", y="count",
                title="Updates by Jurisdiction",
                color="count", color_continuous_scale="Viridis",
            )
            fig.update_layout(margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No jurisdiction data available.")


# ========== SEARCH ==========
def apply_search(df, query: str):
    if not query.strip() or df.empty:
        return df

    q = query.strip().lower()

    search_fields = [
        "title", "topic", "source", "ai_summary", "business_impact",
        "recommended_action", "raw_text", "why_this_matters",
        "notification_reference", "jurisdiction",
    ]

    def row_matches(row):
        haystack = " ".join(str(row.get(f, "")) for f in search_fields).lower()
        return q in haystack

    return df[df.apply(row_matches, axis=1)]


# ========== CLIENT STRIP ==========
def render_client_strip(client_type):
    chips = []
    for label in CLIENT_TYPES:
        icon = CLIENT_ICONS.get(label, "📋")
        css = "client-chip client-chip-active" if label == client_type else "client-chip"
        chips.append(f'<div class="{css}">{icon} {label}</div>')
    st.markdown('<div class="client-strip">' + "".join(chips) + '</div>', unsafe_allow_html=True)


# ========== HERO (devam) ==========
def render_hero(client_type, view_mode, last_updated, df):
    immediate = (df["priority"] == "Immediate").sum() if not df.empty and "priority" in df.columns else 0
    total = len(df)
    avg_score = round(df["impact_score"].mean(), 1) if not df.empty and "impact_score" in df.columns else 0
    live_pct = 0
    if not df.empty and "source_status" in df.columns:
        live_count = (df["source_status"].astype(str).str.lower() == "live").sum()
        live_pct = int(live_count / total * 100) if total > 0 else 0

    st.markdown(f"""
    <div class="hero-box">
        <div class="hero-topline">Regulatory Intelligence Platform · {client_type}</div>
        <div class="hero-title">🛡️ Food Regulatory Intelligence Dashboard</div>
        <p class="hero-subtitle">
            Decision-support layer for food law, compliance, traceability, and supply chain intelligence.
            Converts regulatory updates into client-facing consulting outputs.
        </p>
        <div class="hero-stats">
            <div class="hero-stat">
                <div class="hero-stat-value">{total}</div>
                <div class="hero-stat-label">Total Updates</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-value">{immediate}</div>
                <div class="hero-stat-label">Immediate</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-value">{avg_score}</div>
                <div class="hero-stat-label">Avg Impact</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-value">{live_pct}%</div>
                <div class="hero-stat-label">Live Data</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-value">{last_updated}</div>
                <div class="hero-stat-label">Last Refresh</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ========== INTRO CARDS ==========
def render_intro_cards():
    st.markdown("""
    <div class="intro-grid">
        <div class="intro-card">
            <div class="intro-icon">🔍</div>
            <div class="intro-title">What this tool does</div>
            <div class="intro-text">
                Converts regulatory updates into structured consulting outputs — source monitoring,
                prioritization, client-specific interpretation, and downloadable briefings.
            </div>
        </div>
        <div class="intro-card">
            <div class="intro-icon">⚡</div>
            <div class="intro-title">Why it matters</div>
            <div class="intro-text">
                Regulatory information alone isn't enough. Value comes from turning updates into action:
                what matters, for whom, how urgent, and what should happen next.
            </div>
        </div>
        <div class="intro-card">
            <div class="intro-icon">📈</div>
            <div class="intro-title">Why it scales</div>
            <div class="intro-text">
                Same architecture supports newsletters, client alerts, horizon scanning,
                supply chain review, and AI-assisted legal interpretation workflows.
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ========== METRIC CARDS ==========
def render_metric_cards(filtered, client_type):
    if filtered is None or filtered.empty:
        total = immediate = review = avg_score = avg_conf = high_risk = topics = watchlist_count = 0
    else:
        total = len(filtered)
        immediate = (filtered["priority"] == "Immediate").sum() if "priority" in filtered.columns else 0
        review = (filtered["priority"] == "Review").sum() if "priority" in filtered.columns else 0
        avg_score = round(filtered["impact_score"].mean(), 1) if "impact_score" in filtered.columns else 0
        avg_conf = round(filtered["confidence_score"].mean(), 1) if "confidence_score" in filtered.columns else 0
        high_risk = (
            filtered["risk_level"].astype(str).str.lower() == "high"
        ).sum() if "risk_level" in filtered.columns else 0
        topics = filtered["topic"].nunique() if "topic" in filtered.columns else 0
        watchlist_count = sum(
            1 for _, r in filtered.iterrows() if is_watchlisted(r.get("id", ""))
        )

    cards = [
        ("📋 Total Updates", total, None),
        ("🔴 Immediate", immediate, "▲ attention" if immediate > 0 else "—"),
        ("🟡 Review", review, None),
        ("⚠️ High Risk", high_risk, "▲ attention" if high_risk > 2 else "—"),
        ("📊 Avg Impact", avg_score, None),
        ("🎯 Avg Confidence", avg_conf, None),
        ("🏷️ Topics", topics, None),
        ("⭐ Watchlist", watchlist_count, None),
    ]

    cols = st.columns(4)

    for i, (label, value, delta) in enumerate(cards):
        with cols[i % 4]:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    {f'<div class="metric-delta metric-delta-up">{delta}</div>' if delta and 'attention' in delta else ''}
                    {f'<div class="metric-delta metric-delta-neutral">{delta}</div>' if delta == '—' else ''}
                </div>
                """,
                unsafe_allow_html=True
            )
    # --- CARD DEFINITIONS ---
    cards = [
        ("Total Updates", total, None, "📋"),
        ("Immediate", immediate, "metric-delta-up" if immediate > 0 else "metric-delta-neutral", "🔴"),
        ("Review", review, None, "🟡"),
        ("High Risk", high_risk, "metric-delta-up" if high_risk > 2 else "metric-delta-neutral", "⚠️"),
        ("Avg Impact", avg_score, None, "📊"),
        ("Avg Confidence", avg_conf, None, "🎯"),
        ("Topics", topics, None, "🏷️"),
        ("Watchlist", watchlist_count, None, "⭐"),
    ]

    # --- BUILD HTML ---
    html_cards = ""

    for label, value, delta_class, icon in cards:
        delta_html = ""
        if delta_class:
            symbol = "▲ attention" if "up" in delta_class else "—"
            delta_html = f'<div class="metric-delta {delta_class}">{symbol}</div>'

        html_cards += f"""
        <div class="metric-card">
            <div class="metric-label">{icon} {label}</div>
            <div class="metric-value">{value}</div>
            {delta_html}
        </div>
        """

    # --- FINAL RENDER (KRİTİK KISIM) ---
    st.markdown(
        f'<div class="metric-grid">{html_cards}</div>',
        unsafe_allow_html=True
    )
# ========== TOP URGENT ITEMS ==========
def render_top_urgent_items(filtered, n=3):
    st.markdown(f"""
    <div class="section-header">
        <div class="section-title">🚨 Top {n} Urgent Items</div>
        <div class="section-badge">{min(n, len(filtered))} shown</div>
    </div>
    """, unsafe_allow_html=True)

    if filtered.empty:
        st.info("No urgent items available.")
        return

    urgent = filtered.sort_values(["impact_score", "confidence_score"], ascending=False).head(n)

    cols = st.columns(n)
    for i, (_, row) in enumerate(urgent.iterrows()):
        with cols[i]:
            p_css = priority_class(row.get("priority", "Monitor"))
            c_css = confidence_class(int(row.get("confidence_score", 0)))
            rank_class = f"rank-{i+1}"
            wl_icon = "⭐" if is_watchlisted(row.get("id", "")) else ""

            st.markdown(f"""
            <div class="urgent-card {rank_class}">
                <div class="urgent-number">#{i+1}</div>
                <div class="urgent-title">{wl_icon} {row.get('title', 'Untitled')}</div>
                <div class="urgent-meta">
                    {row.get('source', 'Unknown')} · {format_date(row.get('date'))}
                </div>
                <div class="pill-row">
                    <span class="{p_css}">{row.get('priority', 'Monitor')}</span>
                    <span class="pill pill-topic">{row.get('topic', 'Unknown')}</span>
                    <span class="{c_css}">Conf. {int(row.get('confidence_score', 0))}</span>
                </div>
                {score_bar_html(row.get('impact_score', 0))}
                <div class="content-block">
                    <div class="content-block-title">Why this matters</div>
                    <div class="content-block-text">{row.get('why_this_matters', 'N/A')}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ========== TIMELINE VIEW ==========
def render_timeline(filtered, max_items=10):
    st.markdown("""
    <div class="section-header">
        <div class="section-title">📅 Recent Timeline</div>
    </div>
    """, unsafe_allow_html=True)

    if filtered.empty:
        st.info("No timeline data.")
        return

    recent = filtered.sort_values("date", ascending=False).head(max_items)

    timeline_html = ""
    for _, row in recent.iterrows():
        risk = str(row.get("risk_level", "Low")).lower()
        dot_color = RISK_COLORS.get(risk, "#94a3b8")
        wl = "⭐ " if is_watchlisted(row.get("id", "")) else ""

        timeline_html += f"""
        <div class="timeline-item">
            <div class="timeline-dot" style="background:{dot_color};"></div>
            <div class="timeline-content">
                <div class="timeline-title">{wl}{row.get('title', 'Untitled')}</div>
                <div class="timeline-meta">
                    {row.get('source', 'Unknown')} · {format_date(row.get('date'))} ·
                    Score {row.get('impact_score', 0)}/10 · {row.get('priority', 'Monitor')}
                </div>
            </div>
        </div>
        """

    st.markdown(f'<div class="report-box">{timeline_html}</div>', unsafe_allow_html=True)


# ========== VIEW: OVERVIEW ==========
def render_overview(filtered, client_type):
    render_metric_cards(filtered, client_type)

    # Client insights
    st.markdown("""
    <div class="section-header">
        <div class="section-title">💡 Client-Specific Insights</div>
    </div>
    """, unsafe_allow_html=True)

    insights = generate_client_insights(filtered, client_type)
    trend_icon = {"up": "📈", "down": "📉", "stable": "➡️"}.get(insights.get("trend_direction", "stable"), "➡️")

    st.markdown(f"""
    <div class="insight-box">
        <div class="insight-headline">{trend_icon} {insights['headline']}</div>
        <div class="insight-detail"><span class="insight-label">Key Risk:</span> {insights['key_risk']}</div>
        <div class="insight-detail"><span class="insight-label">Operational Focus:</span> {insights['operational_focus']}</div>
        <div class="insight-detail"><span class="insight-label">Next Step:</span> {insights['recommended_next_step']}</div>
    </div>
    """, unsafe_allow_html=True)

    render_top_urgent_items(filtered)
    render_timeline(filtered)

    # Quick analytics preview
    st.markdown("""
    <div class="section-header">
        <div class="section-title">📊 Quick Analytics</div>
    </div>
    """, unsafe_allow_html=True)

    if not filtered.empty:
        c1, c2 = st.columns(2)
        frames = build_analytics_frames(filtered)

        if "topic_counts" in frames:
            fig = px.pie(frames["topic_counts"], names="topic", values="count", hole=0.45)
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=280, showlegend=True)
            c1.plotly_chart(fig, use_container_width=True)

        if "priority_counts" in frames:
            fig = px.bar(
                frames["priority_counts"], x="priority", y="count",
                color="priority",
                color_discrete_map={"Immediate": "#dc2626", "Review": "#f59e0b", "Monitor": "#3b82f6"},
            )
            fig.update_layout(margin=dict(t=10, b=10), height=280, showlegend=False)
            c2.plotly_chart(fig, use_container_width=True)


# ========== VIEW: WATCHLIST ==========
def render_watchlist_view(filtered, client_type):
    st.markdown("""
    <div class="section-header">
        <div class="section-title">⭐ Watchlist</div>
    </div>
    """, unsafe_allow_html=True)

    wl_ids = st.session_state.get("watchlist", [])

    if not wl_ids:
        st.info("Your watchlist is empty. Add items from the Updates view by clicking the ⭐ button.")
        return

    wl_df = filtered[filtered["id"].isin(wl_ids)] if "id" in filtered.columns else pd.DataFrame()

    if wl_df.empty:
        st.warning("Watchlisted items not found in current filtered data. Try broadening your filters.")
        return

    st.caption(f"{len(wl_df)} watchlisted item(s)")

    for _, row in wl_df.iterrows():
        risk_css, risk_label = risk_class(row.get("risk_level", "Low"))
        extra_class = card_risk_class(row.get("risk_level", "Low"))
        p_css = priority_class(row.get("priority", "Monitor"))
        c_css = confidence_class(int(row.get("confidence_score", 0)))

        st.markdown(f"""
        <div class="update-card {extra_class} watchlisted">
            <div class="card-header">
                <div class="update-title">⭐ {row.get('title', 'Untitled')}</div>
                <div class="card-score-badge">{row.get('impact_score', 0)}/10</div>
            </div>
            <div class="meta-row">
                {row.get('source', 'Unknown')}
                <span class="meta-separator">·</span>
                {format_date(row.get('date'))}
                <span class="meta-separator">·</span>
                {safe_value(row.get('jurisdiction'), 'Unknown')}
            </div>
            <div class="pill-row">
                <span class="{risk_css}">{risk_label} Risk</span>
                <span class="{p_css}">{row.get('priority', 'Monitor')}</span>
                <span class="pill pill-topic">{row.get('topic', 'Unknown')}</span>
                <span class="{c_css}">Conf. {int(row.get('confidence_score', 0))}</span>
            </div>
            <div class="content-block">
                <div class="content-block-title">Why This Matters</div>
                <div class="content-block-text">{row.get('why_this_matters', 'N/A')}</div>
            </div>
            <div class="content-block">
                <div class="content-block-title">Recommended Action</div>
                <div class="content-block-text">{row.get('recommended_action', 'N/A')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Note & remove
        c1, c2 = st.columns([3, 1])
        with c1:
            note_key = f"note-{row.get('id', '')}"
            existing_note = get_user_note(row.get("id", ""))
            new_note = st.text_input(
                "Add note", value=existing_note, key=note_key,
                placeholder="Add a personal note...",
                label_visibility="collapsed",
            )
            if new_note != existing_note:
                save_user_note(row.get("id", ""), new_note)
        with c2:
            if st.button("Remove ⭐", key=f"rm-wl-{row.get('id', '')}"):
                toggle_watchlist(row.get("id", ""))
                st.rerun()


# ========== VIEW: REPORTS ==========
def render_reports(filtered, client_type):
    st.markdown("""
    <div class="section-header">
        <div class="section-title">📄 Report Generator</div>
    </div>
    """, unsafe_allow_html=True)

    report_type = st.radio(
        "Report Type",
        ["Weekly Summary", "Full Intelligence Report", "Executive Brief"],
        horizontal=True,
    )

    if report_type == "Weekly Summary":
        report_text = generate_weekly_report(filtered, client_type)
    elif report_type == "Full Intelligence Report":
        report_text = build_full_report(filtered, client_type)
    else:
        insights = generate_client_insights(filtered, client_type)
        report_text = f"""EXECUTIVE BRIEF
{'═' * 50}
Client Type: {client_type}
Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

HEADLINE
{insights['headline']}

KEY RISK
{insights['key_risk']}

OPERATIONAL FOCUS
{insights['operational_focus']}

RECOMMENDED NEXT STEP
{insights['recommended_next_step']}
{'═' * 50}
"""

    # Preview
    st.markdown('<div class="report-box">', unsafe_allow_html=True)
    st.markdown("**Report Preview**")

    preview_lines = report_text.split("\n")[:20]
    st.code("\n".join(preview_lines) + ("\n..." if len(report_text.split("\n")) > 20 else ""), language=None)
    st.markdown('</div>', unsafe_allow_html=True)

    # Downloads
    report_pdf = build_pdf_bytes(report_type, report_text)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.download_button(
            label="📥 Download TXT",
            data=report_text,
            file_name=f"{sanitize_filename(report_type)}_{sanitize_filename(client_type)}.txt",
            mime="text/plain",
            key="report-txt",
        )

    with c2:
        st.download_button(
            label="📥 Download PDF",
            data=report_pdf,
            file_name=f"{sanitize_filename(report_type)}_{sanitize_filename(client_type)}.pdf",
            mime="application/pdf",
            key="report-pdf",
        )

    with c3:
        if not filtered.empty:
            excel_bytes = build_excel_bytes(filtered)
            st.download_button(
                label="📥 Download Excel",
                data=excel_bytes,
                file_name=f"regulatory_data_{sanitize_filename(client_type)}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="report-excel",
            )

    with c4:
        if not filtered.empty:
            csv_text = filtered.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv_text,
                file_name=f"regulatory_data_{sanitize_filename(client_type)}.csv",
                mime="text/csv",
                key="report-csv",
            )

    # Summary stats in report view
    st.markdown("""
    <div class="section-header">
        <div class="section-title">📊 Report Statistics</div>
    </div>
    """, unsafe_allow_html=True)

    if not filtered.empty:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Immediate Priority", (filtered["priority"] == "Immediate").sum())
        with c2:
            st.metric("Review Priority", (filtered["priority"] == "Review").sum())
        with c3:
            st.metric("Monitor Priority", (filtered["priority"] == "Monitor").sum())

        top_topics = filtered["topic"].value_counts().head(5)
        fig = px.bar(top_topics, orientation="h", title="Top 5 Topics in Report")
        fig.update_layout(showlegend=False, yaxis_title="", xaxis_title="Count", margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)


# ========== VIEW: UPDATES ==========
def render_updates(filtered, client_type):
    st.markdown("""
    <div class="section-header">
        <div class="section-title">📰 Regulatory Updates</div>
    </div>
    """, unsafe_allow_html=True)

    # Search & sort controls
    sc1, sc2, sc3 = st.columns([3, 1, 1])

    with sc1:
        search_query = st.text_input(
            "🔍 Search",
            placeholder="Search by title, topic, source, summary, reference...",
            label_visibility="collapsed",
        )

    with sc2:
        sort_by = st.selectbox(
            "Sort by",
            ["Impact Score", "Date", "Confidence", "Priority"],
            label_visibility="collapsed",
        )

    with sc3:
        sort_order = st.selectbox(
            "Order",
            ["Descending", "Ascending"],
            label_visibility="collapsed",
        )

    updates_df = apply_search(filtered, search_query)

    # Apply sort
    ascending = sort_order == "Ascending"
    sort_col_map = {
        "Impact Score": "impact_score",
        "Date": "date",
        "Confidence": "confidence_score",
        "Priority": "impact_score",
    }
    sort_col = sort_col_map.get(sort_by, "impact_score")
    if sort_col in updates_df.columns:
        updates_df = updates_df.sort_values(sort_col, ascending=ascending)

    st.caption(f"Showing {len(updates_df)} of {len(filtered)} update(s)")

    # Pagination
    items_per_page = st.select_slider("Items per page", options=[5, 10, 15, 25, 50], value=10)
    total_pages = max(1, (len(updates_df) + items_per_page - 1) // items_per_page)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_df = updates_df.iloc[start_idx:end_idx]

    st.caption(f"Page {page} of {total_pages}")

    for idx, row in page_df.iterrows():
        row_id = row.get("id", f"row-{idx}")
        watchlisted = is_watchlisted(row_id)

        # Check AI cache
        ai_key = f"ai-{row_id}-{client_type}"
        if ai_key in st.session_state:
            cached = st.session_state[ai_key]
            ai_summary = cached["ai_summary"]
            business_impact = cached["business_impact"]
            recommended_action = cached["recommended_action"]
            model_used = cached.get("_model_used", "local fallback")
        else:
            ai_summary = safe_value(row.get("ai_summary"), "No summary available.")
            business_impact = safe_value(row.get("business_impact"), "No impact analysis available.")
            recommended_action = safe_value(row.get("recommended_action"), "No recommended action available.")
            model_used = "initial data"

        title = safe_value(row.get("title"), "Untitled")
        source = safe_value(row.get("source"), "Unknown")
        date_str = format_date(row.get("date"))
        topic = safe_value(row.get("topic"), "Unknown")
        jurisdiction = safe_value(row.get("jurisdiction"), "Unknown")
        url = safe_value(row.get("url"), "")

        risk_css, risk_label = risk_class(row.get("risk_level", "Low"))
        extra_class = card_risk_class(row.get("risk_level", "Low"))
        score = row.get("impact_score", 0)
        priority = safe_value(row.get("priority"), "Monitor")
        why_matters = safe_value(row.get("why_this_matters"), "")
        p_css = priority_class(priority)

        source_status = safe_value(row.get("source_status"), "unknown")
        fetch_method = safe_value(row.get("fetch_method"), "n/a")
        notification_ref = safe_value(row.get("notification_reference"), "n/a")
        confidence_score = int(row.get("confidence_score", 0))
        c_css = confidence_class(confidence_score)
        status_pill = source_status_pill(source_status)
        badge_html = build_data_badge_html(source_status)

        wl_class = " watchlisted" if watchlisted else ""
        wl_icon = "⭐" if watchlisted else ""

        adjusted_action = client_adjusted_action(recommended_action, client_type, topic, priority)

        st.markdown(f"""
        <div class="update-card {extra_class}{wl_class}">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div>{badge_html}</div>
            </div>
            <div class="card-header">
                <div class="update-title">{wl_icon} {title}</div>
                <div class="card-score-badge">{score}/10</div>
            </div>
            <div class="meta-row">
                {source} <span class="meta-separator">·</span>
                {date_str} <span class="meta-separator">·</span>
                {jurisdiction} <span class="meta-separator">·</span>
                {status_pill}
            </div>
            <div class="meta-row" style="font-size:0.75rem;">
                Fetch: {fetch_method} <span class="meta-separator">·</span>
                Ref: {notification_ref} <span class="meta-separator">·</span>
                Model: {model_used}
            </div>
            <div class="pill-row">
                <span class="pill pill-source">{source}</span>
                <span class="pill pill-topic">{topic}</span>
                <span class="{risk_css}">{risk_label} Risk</span>
                <span class="{p_css}">{priority}</span>
                <span class="{c_css}">Confidence {confidence_score}</span>
            </div>

            {score_bar_html(score)}

            <div class="content-block">
                <div class="content-block-title">AI Summary</div>
                <div class="content-block-text">{ai_summary}</div>
            </div>
            <div class="content-block">
                <div class="content-block-title">Why This Matters</div>
                <div class="content-block-text">{why_matters}</div>
            </div>
            <div class="content-block">
                <div class="content-block-title">Business Impact</div>
                <div class="content-block-text">{business_impact}</div>
            </div>
            <div class="content-block">
                <div class="content-block-title">Recommended Action</div>
                <div class="content-block-text">{adjusted_action}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Action buttons row
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
            wl_label = "Remove ⭐" if watchlisted else "Add ⭐"
            if st.button(wl_label, key=f"wl-{row_id}"):
                toggle_watchlist(row_id)
                st.rerun()

        with btn_cols[1]:
            if st.button("🤖 AI Analyze", key=f"ai-btn-{row_id}-{client_type}"):
                with st.spinner("Generating AI analysis..."):
                    enriched = generate_ai_analysis(row, client_type)
                    st.session_state[ai_key] = enriched
                    st.rerun()

        with btn_cols[2]:
            st.download_button(
                label="📥 TXT",
                data=alert_text,
                file_name=f"{safe_name}_alert.txt",
                mime="text/plain",
                key=f"txt-{row_id}-{client_type}",
            )

        with btn_cols[3]:
            st.download_button(
                label="📥 PDF",
                data=pdf_bytes,
                file_name=f"{safe_name}_alert.pdf",
                mime="application/pdf",
                key=f"pdf-{row_id}-{client_type}",
            )

        with btn_cols[4]:
            if url:
                st.markdown(f"[🔗 Source]({url})")

        # Expandable sections
        with st.expander("📝 Notes & Raw Text"):
            note_val = get_user_note(row_id)
            new_note = st.text_area(
                "Your note",
                value=note_val,
                key=f"note-upd-{row_id}",
                placeholder="Add a personal note about this update...",
                height=80,
            )
            if new_note != note_val:
                save_user_note(row_id, new_note)
                st.success("Note saved.")

            raw_text = safe_value(row.get("raw_text"), "No raw text available.")
            st.text_area("Raw text", value=raw_text, height=120, disabled=True, key=f"raw-{row_id}")

        st.markdown("---")


# ========== VIEW: COMPARISON ==========
def render_comparison_view(filtered, client_type):
    st.markdown("""
    <div class="section-header">
        <div class="section-title">🔄 Comparison View</div>
    </div>
    """, unsafe_allow_html=True)

    if filtered.empty or "date" not in filtered.columns:
        st.info("Not enough data for comparison.")
        return

    # Compare two time periods
    st.subheader("Period Comparison")

    dates = filtered["date"].dropna()
    if dates.empty:
        st.info("No date data available.")
        return

    min_date = dates.min().date()
    max_date = dates.max().date()
    mid_date = min_date + (max_date - min_date) / 2

    c1, c2 = st.columns(2)
    with c1:
        period1_start = st.date_input("Period 1 Start", value=min_date, key="p1s")
        period1_end = st.date_input("Period 1 End", value=mid_date, key="p1e")
    with c2:
        period2_start = st.date_input("Period 2 Start", value=mid_date + timedelta(days=1), key="p2s")
        period2_end = st.date_input("Period 2 End", value=max_date, key="p2e")

    p1 = filtered[(filtered["date"].dt.date >= period1_start) & (filtered["date"].dt.date <= period1_end)]
    p2 = filtered[(filtered["date"].dt.date >= period2_start) & (filtered["date"].dt.date <= period2_end)]

    # Comparison metrics
    metrics = {
        "Total Updates": (len(p1), len(p2)),
        "Immediate Priority": (
            (p1["priority"] == "Immediate").sum() if not p1.empty else 0,
            (p2["priority"] == "Immediate").sum() if not p2.empty else 0,
        ),
        "Avg Impact Score": (
            round(p1["impact_score"].mean(), 1) if not p1.empty else 0,
            round(p2["impact_score"].mean(), 1) if not p2.empty else 0,
        ),
        "High Risk Items": (
            (p1["risk_level"].astype(str).str.lower() == "high").sum() if not p1.empty else 0,
            (p2["risk_level"].astype(str).str.lower() == "high").sum() if not p2.empty else 0,
        ),
        "Avg Confidence": (
            round(p1["confidence_score"].mean(), 1) if not p1.empty else 0,
            round(p2["confidence_score"].mean(), 1) if not p2.empty else 0,
        ),
    }

    comp_html = """
    <table class="comparison-table">
        <tr>
            <th>Metric</th>
            <th>Period 1</th>
            <th>Period 2</th>
            <th>Change</th>
        </tr>
    """

    for metric_name, (v1, v2) in metrics.items():
        diff = v2 - v1
        if diff > 0:
            change = f'<span style="color:#dc2626;font-weight:700;">▲ +{diff}</span>'
        elif diff < 0:
            change = f'<span style="color:#16a34a;font-weight:700;">▼ {diff}</span>'
        else:
            change = '<span style="color:#94a3b8;">— 0</span>'

        comp_html += f"""
        <tr>
            <td><strong>{metric_name}</strong></td>
            <td>{v1}</td>
            <td>{v2}</td>
            <td>{change}</td>
        </tr>
        """

    comp_html += "</table>"
    st.markdown(f'<div class="report-box">{comp_html}</div>', unsafe_allow_html=True)

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
        fig.update_layout(barmode="group", title="Topic Distribution: Period 1 vs Period 2", margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    # Client type comparison
    st.subheader("Client Type Comparison")
    selected_clients = st.multiselect(
        "Compare client types",
        CLIENT_TYPES,
        default=[client_type],
    )

    if selected_clients and not filtered.empty:
        comparison_data = []
        for ct in selected_clients:
            temp = filtered.copy()
            temp["_impact"] = temp.apply(lambda r: calculate_impact_score(r, ct), axis=1)
            temp["_priority"] = temp["_impact"].apply(determine_priority)
            comparison_data.append({
                "Client Type": ct,
                "Avg Impact": round(temp["_impact"].mean(), 1),
                "Immediate": (temp["_priority"] == "Immediate").sum(),
                "Review": (temp["_priority"] == "Review").sum(),
                "Monitor": (temp["_priority"] == "Monitor").sum(),
            })

        comp_df = pd.DataFrame(comparison_data)
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

        fig = px.bar(
            comp_df.melt(id_vars="Client Type", value_vars=["Immediate", "Review", "Monitor"]),
            x="Client Type", y="value", color="variable",
            barmode="group", title="Priority Distribution by Client Type",
            color_discrete_map={"Immediate": "#dc2626", "Review": "#f59e0b", "Monitor": "#3b82f6"},
        )
        fig.update_layout(margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)


# ========== SIDEBAR ==========
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

# Load & initialize watchlist
if WATCHLIST_FILE.exists():
    st.session_state["watchlist"] = load_watchlist()

if NOTES_FILE.exists():
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            st.session_state["user_notes"] = json.load(f)
    except Exception:
        pass

# Load data
combine_data.clear()
df = combine_data()

if not df.empty:
    df["confidence_score"] = df.apply(calculate_confidence_score, axis=1)

# Sidebar
with st.sidebar:
    st.markdown("### 🛡️ Controls")

    client_type = st.selectbox(
        "Client Type",
        CLIENT_TYPES,
        format_func=lambda x: f"{CLIENT_ICONS.get(x, '📋')} {x}",
    )

    view_mode = st.radio(
        "View",
        ["Overview", "Updates", "Analytics", "Reports", "Watchlist", "Comparison"],
        format_func=lambda x: {
            "Overview": "📋 Overview",
            "Updates": "📰 Updates",
            "Analytics": "📊 Analytics",
            "Reports": "📄 Reports",
            "Watchlist": "⭐ Watchlist",
            "Comparison": "🔄 Comparison",
        }.get(x, x),
    )

    st.markdown("---")

    if st.button("🔄 Refresh Live Data", use_container_width=True):
        with st.spinner("Fetching live data from EFSA & RASFF..."):
            try:
                refresh_live_data()
                combine_data.clear()
                st.success("✅ Live data refreshed.")
                st.rerun()
            except Exception as e:
                st.error(f"Refresh failed: {e}")

    last_updated_relative = format_relative_update_time(LIVE_DATA_FILE)
    st.caption(f"🕐 Last updated: {last_updated_relative}")

    # AI status
    try:
        openrouter_exists = bool(st.secrets.get("OPENROUTER_API_KEY", ""))
    except Exception:
        openrouter_exists = False

    if openrouter_exists:
        st.success("🟢 OpenRouter connected")
    else:
        st.info("🔵 Local AI mode")

    st.markdown('<div class="sidebar-section-title">FILTERS</div>', unsafe_allow_html=True)

    # Filter preset save/load
    preset_name = st.text_input("Save filter preset as:", placeholder="e.g. 'High Risk Only'", key="preset_name")

    selected_sources = []
    selected_topics = []
    selected_risks = []
    selected_priorities = []
    data_mode = "All"
    min_confidence = 0
    date_range = None

    if not df.empty:
        source_options = sorted(df["source"].dropna().astype(str).unique().tolist()) if "source" in df.columns else []
        topic_options = sorted(df["topic"].dropna().astype(str).unique().tolist()) if "topic" in df.columns else []
        risk_options = sorted(df["risk_level"].dropna().astype(str).unique().tolist()) if "risk_level" in df.columns else []

        selected_sources = st.multiselect("Source", source_options, default=source_options)
        selected_topics = st.multiselect("Topic", topic_options, default=topic_options)
        selected_risks = st.multiselect("Risk Level", risk_options, default=risk_options)

        data_mode = st.radio("Data Mode", ["All", "Live Only", "Fallback Only"], horizontal=True)

        min_confidence = st.slider("Min Confidence", 0, 100, 0, 5)

        # Date range filter
        if "date" in df.columns:
            dates = df["date"].dropna()
            if not dates.empty:
                min_d = dates.min().date()
                max_d = dates.max().date()
                date_range = st.date_input(
                    "Date Range",
                    value=(min_d, max_d),
                    min_value=min_d,
                    max_value=max_d,
                )

        # Save preset
        if preset_name and st.button("💾 Save Preset"):
            st.session_state.setdefault("filter_presets", {})[preset_name] = {
                "sources": selected_sources,
                "topics": selected_topics,
                "risks": selected_risks,
                "data_mode": data_mode,
                "min_confidence": min_confidence,
            }
            st.success(f"Preset '{preset_name}' saved.")

    # Watchlist count
    wl_count = len(st.session_state.get("watchlist", []))
    if wl_count:
        st.markdown(f"⭐ **Watchlist:** {wl_count} item(s)")


# ========== MAIN AREA ==========
last_updated_str = format_relative_update_time(LIVE_DATA_FILE) or "unknown"

render_hero(client_type, view_mode, last_updated_str, df)

if auto_refresh_message:
    if auto_refresh_triggered:
        st.success(auto_refresh_message)
    else:
        st.warning(auto_refresh_message)

render_client_strip(client_type)
render_intro_cards()

if df.empty:
    st.warning("⚠️ No data found. Click **Refresh Live Data** in the sidebar.")
    st.stop()

# Apply filters
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

# Date range filter
if date_range and len(date_range) == 2 and "date" in filtered.columns:
    start_d, end_d = date_range
    mask = filtered["date"].dt.date.between(start_d, end_d)
    filtered = filtered[mask.fillna(False)]

# Calculate consulting fields
if not filtered.empty:
    filtered["impact_score"] = filtered.apply(lambda row: calculate_impact_score(row, client_type), axis=1)
    filtered["priority"] = filtered["impact_score"].apply(determine_priority)
    filtered["why_this_matters"] = filtered.apply(lambda row: why_this_matters(row, client_type), axis=1)

    # Priority filter (after calculation)
    priority_options = sorted(filtered["priority"].dropna().unique().tolist())
    # Apply saved priority if exists
    if selected_priorities:
        filtered = filtered[filtered["priority"].isin(selected_priorities)]

# Route to view
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

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align:center; padding:1rem 0; color:#94a3b8; font-size:0.78rem;">
    🛡️ Food Regulatory Intelligence Dashboard · Prototype v2.0<br>
    Regulatory horizon scanning · Client intelligence · Consulting outputs · Analytics
</div>
""", unsafe_allow_html=True)
