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
import json
import os

ANALYTICS_FILE = "data/analytics.json"

def load_analytics():
    if not os.path.exists(ANALYTICS_FILE):
        return {"visits": 0, "actions": 0}
    with open(ANALYTICS_FILE, "r") as f:
        return json.load(f)

def save_analytics(data):
    with open(ANALYTICS_FILE, "w") as f:
        json.dump(data, f)

TASKS_FILE = "data/tasks.json"
WATCHLIST_FILE = "data/watchlist.json"
WORK_ITEMS_FILE = "data/work_items.json"

def load_json_file(path, default):
    if not os.path.exists("data"):
        os.makedirs("data")

    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_tasks():
    return load_json_file(TASKS_FILE, [])

def save_tasks(tasks):
    save_json_file(TASKS_FILE, tasks)

def load_watchlist():
    return load_json_file(WATCHLIST_FILE, [])

def save_watchlist(items):
    save_json_file(WATCHLIST_FILE, items)

def add_task(task):
    tasks = load_tasks()
    tasks.append(task)
    save_tasks(tasks)

def load_work_items():
    return load_json_file(WORK_ITEMS_FILE, [])

def save_work_items(items):
    save_json_file(WORK_ITEMS_FILE, items)

def add_work_item(item):
    items = load_work_items()
    item_id = str(item.get("id", ""))
    item_type = str(item.get("type", ""))

    exists = any(
        str(x.get("id", "")) == item_id and str(x.get("type", "")) == item_type
        for x in items
    )
    if exists:
        return False

    items.append(item)
    save_work_items(items)
    return True

def remove_work_item(item_id, item_type):
    items = load_work_items()
    items = [
        x for x in items
        if not (
            str(x.get("id", "")) == str(item_id) and
            str(x.get("type", "")) == str(item_type)
        )
    ]
    save_work_items(items)

def add_to_watchlist(item):
    work_items = load_work_items()

    item_id = str(item.get("id", ""))

    exists = any(
        str(x.get("id", "")) == item_id and str(x.get("type", "")) == "watchlist"
        for x in work_items
    )

    if exists:
        return False

    item["type"] = "watchlist"
    item["status"] = "open"

    work_items.append(item)
    save_work_items(work_items)

    return True

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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()

# ================================================================
# CSS - sadece genel layout
# ================================================================
st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    .block-container {
        padding-top: 0.5rem;
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
# OPENROUTER
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
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_json_records(path: Path, records):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def refresh_live_data():
    efsa = fetch_efsa_updates()
    rasff = fetch_rasff_updates()
    items = efsa + rasff
    save_json_records(LIVE_DATA_FILE, items)
    return items


def ensure_metadata_fields(df):
    defaults = {
        "source_status": "unknown",
        "fetch_method": "n/a",
        "notification_reference": "n/a",
        "last_verified": "n/a",
        "jurisdiction": "Unknown",
    }
    for field, val in defaults.items():
        if field not in df.columns:
            df[field] = val
    return df


@st.cache_data(ttl=300)
def combine_data():
    base = load_json_records(BASE_DATA_FILE)
    live = load_json_records(LIVE_DATA_FILE)
    all_rec = live + base
    if not all_rec:
        return pd.DataFrame()
    df = pd.DataFrame(all_rec)
    df = ensure_metadata_fields(df)
    dedupe = [c for c in ["title", "source", "date"] if c in df.columns]
    if dedupe:
        df = df.drop_duplicates(subset=dedupe, keep="first")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "id" not in df.columns:
        df["id"] = df.apply(
            lambda r: hashlib.md5(
                f"{r.get('title','')}{r.get('source','')}{r.get('date','')}".encode()
            ).hexdigest()[:12], axis=1,
        )
    return df.sort_values("date", ascending=False, na_position="last").reset_index(drop=True)


def minutes_since_update(path):
    if not path.exists():
        return None
    try:
        t = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return int((datetime.now(timezone.utc) - t).total_seconds() // 60)
    except Exception:
        return None


def format_relative_time(path):
    m = minutes_since_update(path)
    if m is None:
        return "never"
    if m < 1:
        return "just now"
    if m < 60:
        return f"{m} min ago"
    h = m // 60
    if h < 24:
        return f"{h} hr ago"
    return f"{h // 24} day(s) ago"


def should_auto_refresh(path, max_min):
    if not path.exists():
        return True
    m = minutes_since_update(path)
    return m is None or m >= max_min


# ================================================================
# WATCHLIST & NOTES
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


def load_user_notes():
    if not NOTES_FILE.exists():
        return {}
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
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
# SAFE HELPERS
# ================================================================
def safe_val(val, default="n/a"):
    if val is None:
        return default
    if isinstance(val, float) and pd.isna(val):
        return default
    s = str(val).strip()
    if s.lower() in ["nan", "none", ""]:
        return default
    return val


def fmt_date(value):
    if value is None:
        return "Unknown"
    try:
        if pd.isna(value):
            return "Unknown"
    except (TypeError, ValueError):
        pass
    try:
        return pd.to_datetime(value).strftime("%b %d, %Y")
    except Exception:
        return str(value)


def sanitize_fn(value):
    value = value.lower().strip()
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        value = value.replace(ch, "-")
    return value.replace(" ", "_")[:80]


# ================================================================
# PDF & EXPORT
# ================================================================
def wrap_text(text, mx=95):
    if not text:
        return [""]
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) <= mx:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build_pdf(title, content):
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    _, h = A4
    x, y = 50, h - 50
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
                y = h - 50
            pdf.drawString(x, y, wl)
            y -= 14
    pdf.save()
    buf.seek(0)
    return buf.read()


def build_csv(df):
    cols = [c for c in [
        "title", "source", "date", "topic", "risk_level", "jurisdiction",
        "impact_score", "priority", "confidence_score", "source_status",
        "ai_summary", "business_impact", "recommended_action",
        "why_this_matters", "notification_reference", "url",
    ] if c in df.columns]
    return df[cols].to_csv(index=False)


def build_excel(df):
    buf = BytesIO()
    cols = [c for c in [
        "title", "source", "date", "topic", "risk_level", "jurisdiction",
        "impact_score", "priority", "confidence_score", "source_status",
        "ai_summary", "business_impact", "recommended_action",
        "why_this_matters", "notification_reference", "url",
    ] if c in df.columns]
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df[cols].to_excel(w, index=False, sheet_name="Updates")
    buf.seek(0)
    return buf.read()


# ================================================================
# SCORING
# ================================================================
def calc_confidence(row):
    st_val = str(safe_val(row.get("source_status"), "unknown")).lower()
    method = str(safe_val(row.get("fetch_method"), "n/a")).lower()
    ref = str(safe_val(row.get("notification_reference"), "n/a")).lower()
    if st_val == "live" and method == "detail_page" and ref != "n/a":
        return 95
    if st_val == "live" and method == "rss_feed":
        return 85
    if st_val == "live":
        return 75
    if st_val == "fallback":
        return 45
    return 55


def calc_impact(row, ct):
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
    if topic in bonuses.get(ct, []):
        score += 2
    return min(score, 10)


def det_priority(score):
    if score >= 8:
        return "Immediate"
    if score >= 5:
        return "Review"
    return "Monitor"


def get_why(row, ct):
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
    cr = reasons.get(ct, {})
    if topic in cr:
        return cr[topic]
    if risk == "high":
        return "Commercially material - may require immediate cross-functional review."
    if risk == "low":
        return "Lower urgency - useful for horizon scanning."
    return "May affect compliance planning, supply chain review, and internal decisions."


def adjust_action(base, ct, topic, priority):
    extras = {
        "Exporter": "Check destination-country implications and border exposure.",
        "Retailer": "Assess shelf impact and supplier exposure.",
        "Importer": "Review supplier documentation and inbound controls.",
        "Startup": "Assess product-market fit and authorization timing.",
    }
    return f"{base} {extras.get(ct, 'Review internal QA and production implications.')}"


# ================================================================
# AI ANALYSIS
# ================================================================
def local_fallback(row, ct):
    title = str(row.get("title", "Update"))
    topic = str(row.get("topic", "Food Safety"))
    source = str(row.get("source", "Source"))
    risk = str(row.get("risk_level", "Medium")).lower()
    existing = str(safe_val(row.get("ai_summary"), ""))
    base = existing if existing and existing != "n/a" else f"Update relates to {topic.lower()} - may require compliance review."
    tl = title.lower()
    mapping = {
        "label": ("Review packaging and label workflows.", "Review labels and prepare revisions."),
        "traceability": ("Stronger product tracking may be needed.", "Assess traceability records."),
        "contaminant": ("Increased recall exposure possible.", "Check affected products."),
        "fraud": ("Documentary controls may face scrutiny.", "Review provenance records."),
        "novel": ("Authorization timing must be assessed.", "Review eligibility and timing."),
    }
    impact = "May affect compliance planning and documentation."
    action = "Review internally and determine team response."
    for kw, (imp, act) in mapping.items():
        if kw in tl or kw in topic.lower():
            impact, action = imp, act
            break
    if risk == "high":
        impact = "Commercially significant - immediate compliance escalation needed."
        action = "Prioritize immediate review and rapid response plan."
    elif risk == "low":
        impact = "Lower urgency - relevant for horizon scanning."
        action = "Log and review in next compliance cycle."
    action = adjust_action(action, ct, topic, "Review")
    return {
        "ai_summary": f"{base} Source: {source}.",
        "business_impact": impact,
        "recommended_action": action,
        "_model_used": "local fallback",
    }


def extract_json(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e > s:
        return json.loads(text[s:e + 1])
    raise ValueError("No JSON")


def call_model(client, model, prompt):
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a food regulatory intelligence analyst."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2, max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


def ai_analyze(row, ct):
    rid = str(safe_val(row.get("id"), "unknown"))
    cache_key = f"{rid}-{ct}"
    cache = st.session_state.get("ai_cache", {})
    if isinstance(cache, dict):
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and "ai_summary" in cached:
            return cached

    client = get_openrouter_client()
    if client is None:
        result = local_fallback(row, ct)
    else:
        prompt = f"""You are a food regulatory intelligence analyst.
Return VALID JSON ONLY: {{"ai_summary":"...","business_impact":"...","recommended_action":"..."}}
Client type: {ct}.
Title: {safe_val(row.get('title'))}
Source: {safe_val(row.get('source'))}
Topic: {safe_val(row.get('topic'))}
Jurisdiction: {safe_val(row.get('jurisdiction'))}
Summary: {safe_val(row.get('ai_summary'))}
Raw: {safe_val(row.get('raw_text'))}"""

        result = None
        for model in OPENROUTER_MODELS:
            try:
                text = call_model(client, model, prompt)
                parsed = extract_json(text)
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
            result = local_fallback(row, ct)

    if "ai_cache" not in st.session_state:
        st.session_state["ai_cache"] = {}
    st.session_state["ai_cache"][cache_key] = result
    return result


# ================================================================
# REPORTS
# ================================================================
def weekly_report(df, ct):
    if df.empty:
        return "No updates available."
    rdf = df.sort_values("impact_score", ascending=False)
    top = rdf.head(5)
    lines = [
        "=" * 60, "  WEEKLY REGULATORY INTELLIGENCE REPORT", "=" * 60, "",
        f"  Client: {ct}", f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"  Updates: {len(rdf)}", "",
        "-" * 60, "  SUMMARY", "-" * 60,
        f"  Immediate: {int((rdf['priority'] == 'Immediate').sum())}",
        f"  Review:    {int((rdf['priority'] == 'Review').sum())}",
        f"  Monitor:   {int((rdf['priority'] == 'Monitor').sum())}", "",
        "-" * 60, "  TOP PRIORITIES", "-" * 60,
    ]
    for i, (_, r) in enumerate(top.iterrows(), 1):
        lines.append(f"\n  {i}. {r.get('title', 'Untitled')}")
        lines.append(f"     {r.get('source', '?')} | {fmt_date(r.get('date'))}")
        lines.append(f"     Score: {r.get('impact_score', 0)}/10 | {r.get('priority', '?')}")
        lines.append(f"     Action: {r.get('recommended_action', '')}")
    lines.extend(["", "=" * 60])
    return "\n".join(lines)


def full_report(df, ct):
    if df.empty:
        return "No data."
    df = df.sort_values("impact_score", ascending=False)
    lines = [
        "=" * 60, "  FULL INTELLIGENCE REPORT", "=" * 60, "",
        f"  Client: {ct}", f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"  Total: {len(df)}", "",
    ]
    for _, r in df.iterrows():
        lines.extend([
            f"  > {r.get('title', 'Untitled')}",
            f"    {r.get('source', '?')} | {fmt_date(r.get('date'))}",
            f"    Priority: {r.get('priority', '?')} | Score: {r.get('impact_score', 0)}/10",
            f"    Action: {r.get('recommended_action', '')}", "",
        ])
    return "\n".join(lines)


def client_insights(df, ct):
    if df.empty:
        return {"headline": "No data.", "key_risk": "N/A", "focus": "N/A", "next_step": "N/A", "trend": "stable"}
    sdf = df.sort_values("impact_score", ascending=False)
    top = sdf.iloc[0]
    top_topic = sdf["topic"].mode().iloc[0] if not sdf["topic"].mode().empty else "Food Safety"
    imm = int((sdf["priority"] == "Immediate").sum())
    high = int((sdf["risk_level"].astype(str).str.lower() == "high").sum())
    focus_map = {
        "Exporter": "Border documentation and destination-market compliance.",
        "Retailer": "Shelf compliance, supplier coordination, consumer risk.",
        "Importer": "Inbound controls, traceability, batch documentation.",
        "Startup": "Packaging, market-entry timing, regulatory readiness.",
    }
    return {
        "headline": f"{imm} immediate, {high} high-risk, focused on {top_topic.lower()}.",
        "key_risk": f"Top: {top.get('title', 'Untitled')}",
        "focus": focus_map.get(ct, "Internal QA, compliance, product documentation."),
        "next_step": "Start with top-priority item and convert to action note.",
        "trend": "up" if imm > 2 else ("stable" if imm > 0 else "down"),
    }


def build_alert(row, ct, score, priority, why):
    return (
        f"Regulatory Update - {row.get('title', 'Update')}\n\n"
        f"Client: {ct} | Source: {row.get('source', '?')} | {fmt_date(row.get('date'))}\n"
        f"Topic: {row.get('topic', '?')} | Score: {score}/10 | Priority: {priority}\n\n"
        f"Summary: {row.get('ai_summary', 'N/A')}\n\n"
        f"Why: {why}\n\nImpact: {row.get('business_impact', 'N/A')}\n\n"
        f"Action: {row.get('recommended_action', 'N/A')}\n"
    )


# ================================================================
# ANALYTICS
# ================================================================
def get_frames(df):
    frames = {}
    if df.empty:
        return frames
    w = df.copy()
    if "date" in w.columns:
        w["date_only"] = pd.to_datetime(w["date"], errors="coerce").dt.date
    for col, key in [("source", "src"), ("topic", "topic"), ("priority", "pri"),
                     ("risk_level", "risk"), ("source_status", "status")]:
        if col in w.columns:
            vc = w[col].astype(str).str.title().value_counts().reset_index()
            vc.columns = [col, "count"]
            frames[key] = vc
    if "date_only" in w.columns:
        t = w.groupby("date_only").size().reset_index(name="count")
        t["date_only"] = pd.to_datetime(t["date_only"])
        frames["trend"] = t.sort_values("date_only")
    if "impact_score" in w.columns and "topic" in w.columns:
        s = w.groupby("topic", dropna=False)["impact_score"].mean().round(2).reset_index()
        frames["score_topic"] = s.sort_values("impact_score", ascending=False)
    if "confidence_score" in w.columns and "source" in w.columns:
        c = w.groupby("source", dropna=False)["confidence_score"].mean().round(2).reset_index()
        frames["conf_src"] = c.sort_values("confidence_score", ascending=False)
    if "impact_score" in w.columns and "confidence_score" in w.columns:
        frames["scatter"] = w[["title", "impact_score", "confidence_score", "risk_level", "topic", "source"]].copy()
    if "topic" in w.columns and "risk_level" in w.columns:
        frames["heatmap"] = w.groupby(["topic", "risk_level"]).size().reset_index(name="count")
    if "jurisdiction" in w.columns:
        j = w["jurisdiction"].astype(str).value_counts().reset_index()
        j.columns = ["jurisdiction", "count"]
        frames["jur"] = j[j["jurisdiction"] != "Unknown"].head(15)
    return frames


# ================================================================
# SEARCH
# ================================================================
def search(df, q):
    if not q.strip() or df.empty:
        return df
    q = q.strip().lower()
    fields = ["title", "topic", "source", "ai_summary", "business_impact",
              "recommended_action", "raw_text", "why_this_matters",
              "notification_reference", "jurisdiction"]
    return df[df.apply(lambda r: q in " ".join(str(r.get(f, "")) for f in fields).lower(), axis=1)]


# ================================================================
# HERO - buyuk, etkileyici
# ================================================================
def render_hero(ct, updated, total, imm, avg, live_pct):
    st.markdown(
        f'<div style="'
        f'background:linear-gradient(135deg,#0b1220 0%,#132b63 40%,#1d4ed8 100%);'
        f'padding:2.5rem 3rem 2rem;border-radius:24px;color:white;margin-bottom:1.2rem;'
        f'box-shadow:0 24px 60px rgba(15,23,42,0.35);position:relative;overflow:hidden;'
        f'">'
        #
        # decorative circle
        f'<div style="position:absolute;top:-80px;right:-60px;width:300px;height:300px;'
        f'border-radius:50%;background:rgba(255,255,255,0.03);"></div>'
        #
        # top line
        f'<div style="font-size:0.76rem;font-weight:700;letter-spacing:0.14em;'
        f'text-transform:uppercase;color:#93c5fd;margin-bottom:0.6rem;">'
        f'Regulatory Intelligence Platform</div>'
        #
        # title
        f'<div style="font-size:2.4rem;font-weight:800;margin-bottom:0.5rem;line-height:1.12;">'
        f'Food Regulatory Intelligence Dashboard</div>'
        #
        # subtitle
        f'<p style="font-size:1.05rem;color:#dbeafe;margin-bottom:1.2rem;line-height:1.55;max-width:800px;">'
        f'Decision-support layer for food law, compliance, traceability, and supply chain intelligence. '
        f'Converts regulatory updates into client-facing consulting outputs.</p>'
        #
        # stats row
        f'<div style="display:flex;gap:40px;flex-wrap:wrap;">'
        f'<div style="text-align:center;">'
        f'<div style="font-size:1.8rem;font-weight:800;">{total}</div>'
        f'<div style="font-size:0.7rem;color:#93c5fd;text-transform:uppercase;letter-spacing:0.06em;">Total Updates</div></div>'
        f'<div style="text-align:center;">'
        f'<div style="font-size:1.8rem;font-weight:800;">{imm}</div>'
        f'<div style="font-size:0.7rem;color:#93c5fd;text-transform:uppercase;letter-spacing:0.06em;">Immediate</div></div>'
        f'<div style="text-align:center;">'
        f'<div style="font-size:1.8rem;font-weight:800;">{avg}</div>'
        f'<div style="font-size:0.7rem;color:#93c5fd;text-transform:uppercase;letter-spacing:0.06em;">Avg Impact</div></div>'
        f'<div style="text-align:center;">'
        f'<div style="font-size:1.8rem;font-weight:800;">{live_pct}%</div>'
        f'<div style="font-size:0.7rem;color:#93c5fd;text-transform:uppercase;letter-spacing:0.06em;">Live Data</div></div>'
        f'<div style="text-align:center;">'
        f'<div style="font-size:1.8rem;font-weight:800;">{updated}</div>'
        f'<div style="font-size:0.7rem;color:#93c5fd;text-transform:uppercase;letter-spacing:0.06em;">Last Refresh</div></div>'
        f'</div>'
        #
        # client mode tag
        f'<div style="font-size:0.8rem;color:#93c5fd;margin-top:1rem;padding-top:0.6rem;'
        f'border-top:1px solid rgba(255,255,255,0.1);">'
        f'Client Mode: {CLIENT_ICONS.get(ct, "")} {ct}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ================================================================
# CLIENT STRIP
# ================================================================
def render_strip(ct):
    chips = []
    for label in CLIENT_TYPES:
        icon = CLIENT_ICONS.get(label, "")
        if label == ct:
            s = ("display:inline-flex;align-items:center;gap:6px;"
                 "background:linear-gradient(135deg,#dbeafe,#ede9fe);"
                 "border:1.5px solid #818cf8;color:#1e3a8a;border-radius:999px;"
                 "padding:0.45rem 0.85rem;font-size:0.82rem;font-weight:700;"
                 "box-shadow:0 2px 8px rgba(99,102,241,0.15);")
        else:
            s = ("display:inline-flex;align-items:center;gap:6px;background:white;"
                 "border:1.5px solid #e2e8f0;color:#475569;border-radius:999px;"
                 "padding:0.45rem 0.85rem;font-size:0.82rem;font-weight:600;")
        chips.append(f'<span style="{s}">{icon} {label}</span>')
    st.markdown('<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:1rem;">'
                + "".join(chips) + "</div>", unsafe_allow_html=True)


# ================================================================
# URGENT ITEMS
# ================================================================
def render_urgent(filtered, n=3):
    st.subheader(f"Top {n} Urgent Items")
    if filtered.empty:
        st.info("No urgent items.")
        return
    urg = filtered.sort_values(["impact_score", "confidence_score"], ascending=False).head(n)
    cols = st.columns(n)
    for i, (_, r) in enumerate(urg.iterrows()):
        with cols[i]:
            rv = str(r.get("risk_level", "Low")).lower()
            bc = RISK_COLORS.get(rv, "#94a3b8")
            sc = r.get("impact_score", 0)
            pct = min(sc / 10 * 100, 100)
            bar_c = "#dc2626" if sc >= 8 else ("#f59e0b" if sc >= 5 else "#3b82f6")
            # Card header
            st.markdown(
                f'<div style="border-left:4px solid {bc};border-radius:12px;'
                f'padding:1rem;background:white;box-shadow:0 2px 8px rgba(0,0,0,0.06);">'
                f'<div style="font-size:1.5rem;color:#e2e8f0;font-weight:800;float:right;">#{i+1}</div>'
                f'<div style="font-size:0.88rem;font-weight:700;color:#0f172a;line-height:1.3;">'
                f'{r.get("title", "Untitled")}</div>'
                f'<div style="font-size:0.74rem;color:#64748b;margin-top:0.25rem;">'
                f'{r.get("source", "?")} | {fmt_date(r.get("date"))}</div></div>',
                unsafe_allow_html=True,
            )
            # Score bar
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin:0.3rem 0;">'
                f'<div style="flex:1;background:#f1f5f9;border-radius:999px;height:5px;overflow:hidden;">'
                f'<div style="width:{pct}%;background:{bar_c};height:100%;border-radius:999px;"></div></div>'
                f'<span style="font-size:0.78rem;font-weight:700;color:{bar_c};">{sc}/10</span></div>',
                unsafe_allow_html=True,
            )
            mc1, mc2 = st.columns(2)
            mc1.caption(f"**{r.get('priority', 'Monitor')}**")
            mc2.caption(f"**{r.get('topic', '?')}**")
            # Why
            st.markdown(
                f'<div style="background:#f8fafc;border-radius:8px;padding:0.4rem 0.6rem;'
                f'font-size:0.78rem;color:#334155;border:1px solid #f1f5f9;">'
                f'<strong>Why:</strong> {r.get("why_this_matters", "N/A")}</div>',
                unsafe_allow_html=True,
            )


# ================================================================
# TIMELINE
# ================================================================
def render_timeline(filtered, mx=8):
    st.subheader("Recent Timeline")
    if filtered.empty:
        st.info("No data.")
        return
    for _, r in filtered.sort_values("date", ascending=False).head(mx).iterrows():
        rv = str(r.get("risk_level", "Low")).lower()
        dc = RISK_COLORS.get(rv, "#94a3b8")
        wl = " [WL]" if is_watchlisted(r.get("id", "")) else ""
        st.markdown(
            f'<div style="display:flex;gap:12px;margin-bottom:0.45rem;padding-bottom:0.45rem;'
            f'border-bottom:1px solid #f1f5f9;">'
            f'<div style="width:10px;height:10px;border-radius:50%;background:{dc};'
            f'margin-top:5px;flex-shrink:0;"></div>'
            f'<div><div style="font-size:0.82rem;font-weight:600;color:#1e293b;">'
            f'{r.get("title", "Untitled")}{wl}</div>'
            f'<div style="font-size:0.72rem;color:#94a3b8;">'
            f'{r.get("source", "?")} | {fmt_date(r.get("date"))} | '
            f'Score {r.get("impact_score", 0)}/10 | {r.get("priority", "Monitor")}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )


# ================================================================
# VIEW: OVERVIEW (istatistikler SADECE burada, compact)
# ================================================================
def render_overview(filtered, ct):
    # 5 kompakt metrik - TEK satır
    c1, c2, c3, c4, c5 = st.columns(5)

    t = len(filtered)
    imm = int((filtered["priority"] == "Immediate").sum()) if not filtered.empty else 0
    rev = int((filtered["priority"] == "Review").sum()) if not filtered.empty else 0
    high = int((filtered["risk_level"].astype(str).str.lower() == "high").sum()) if not filtered.empty else 0
    avg = round(filtered["impact_score"].mean(), 1) if not filtered.empty else 0

    c1.metric("Updates", t)
    c2.metric("Immediate", imm)
    c3.metric("Review", rev)
    c4.metric("High Risk", high)
    c5.metric("Avg Impact", f"{avg}/10")

    st.caption(f"👁️ {analytics['visits']} visitors • Need context? Expand below")

    with st.expander("About this tool", expanded=False):
        intro1, intro2, intro3 = st.columns(3)

        with intro1:
            st.markdown(
                """
                <div style="
                    background:#ffffff;
                    border:1px solid #e2e8f0;
                    border-radius:14px;
                    padding:0.9rem;
                    min-height:140px;
                ">
                    <div style="font-size:0.95rem;margin-bottom:0.3rem;">🔎</div>
                    <div style="font-size:0.9rem;font-weight:700;color:#0f172a;margin-bottom:0.3rem;">
                        What it does
                    </div>
                    <div style="font-size:0.82rem;color:#475569;">
                        Converts regulatory updates into structured, actionable insights.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with intro2:
            st.markdown(
                """
                <div style="
                    background:#ffffff;
                    border:1px solid #e2e8f0;
                    border-radius:14px;
                    padding:0.9rem;
                    min-height:140px;
                ">
                    <div style="font-size:0.95rem;margin-bottom:0.3rem;">⚡</div>
                    <div style="font-size:0.9rem;font-weight:700;color:#0f172a;margin-bottom:0.3rem;">
                        Why it matters
                    </div>
                    <div style="font-size:0.82rem;color:#475569;">
                        Turns information into decisions: urgency, risk, and next steps.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with intro3:
            st.markdown(
                """
                <div style="
                    background:#ffffff;
                    border:1px solid #e2e8f0;
                    border-radius:14px;
                    padding:0.9rem;
                    min-height:140px;
                ">
                    <div style="font-size:0.95rem;margin-bottom:0.3rem;">📈</div>
                    <div style="font-size:0.9rem;font-weight:700;color:#0f172a;margin-bottom:0.3rem;">
                        Why it scales
                    </div>
                    <div style="font-size:0.82rem;color:#475569;">
                        Supports alerts, monitoring, reporting, and AI-driven workflows.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            
           # --- Compact Client Insights (clickable) ---
        st.subheader("Client Insights")

    if filtered.empty:
        st.info("No data available.")
    else:
        ins = client_insights(filtered, ct)
        st.info(ins.get("headline", ""))

        top_item_for_action = filtered.sort_values(
            ["impact_score", "confidence_score"],
            ascending=False
        ).iloc[0]

c_focus, c_next = st.columns(2)

with c_focus:
    st.caption("Focus")
    st.write(ins.get("focus", ""))

with c_next:
    st.caption("Next")

    next_step = ins.get("next_step", "")
    st.write(next_step)

    if st.button("Create Task", key=f"task_btn_{ct}_overview"):
        if top_item_for_action is not None:

            item = {
                "id": str(top_item_for_action.get("id", "")),
                "type": "task",
                "status": "open",
                "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                "client_type": ct,
                "title": f"Review: {top_item_for_action.get('title', 'Untitled')}",
                "source": top_item_for_action.get("source", ""),
                "risk_level": top_item_for_action.get("risk_level", ""),
                "priority": top_item_for_action.get("priority", ""),
                "next_step": next_step,
                "url": top_item_for_action.get("url", ""),
            }

            added = add_work_item(item)

            if added:
                analytics["actions"] += 1
                save_analytics(analytics)
                st.success("Task created")
            else:
                st.info("Task already exists")

        st.markdown("**Top relevant items**")

        top3 = filtered.sort_values(
            ["impact_score", "confidence_score"],
            ascending=False
        ).head(3)

        for _, r in top3.iterrows():
            title = r.get("title", "Untitled")
            why = r.get("why_this_matters", "")
            url = r.get("url", "")
            source = r.get("source", "")
            risk = str(r.get("risk_level", "")).lower()

            risk_label = ""
            if risk == "high":
                risk_label = "HIGH"
            elif risk == "medium":
                risk_label = "MED"

            box1, box2 = st.columns([6, 1])

            with box1:
                if url and str(url).strip():
                    st.markdown(f"**[{title} ↗]({url})**")
                else:
                    st.markdown(f"**{title}**")
                st.write(why)
                st.caption(source)

            with box2:
                if risk_label:
                    st.metric("Risk", risk_label)

            st.divider()

    render_urgent(filtered)
    render_timeline(filtered)

    # ============================================================
    # Quick Analytics
    # ============================================================
    st.subheader("Quick Analytics")

    if not filtered.empty:
        fr = get_frames(filtered)

        immediate_count = int((filtered["priority"] == "Immediate").sum()) if "priority" in filtered.columns else 0
        high_risk_count = int((filtered["risk_level"].astype(str).str.lower() == "high").sum()) if "risk_level" in filtered.columns else 0
        avg_impact = round(filtered["impact_score"].mean(), 1) if "impact_score" in filtered.columns else 0

        k1, k2, k3 = st.columns(3)
        k1.metric("Immediate", immediate_count)
        k2.metric("High Risk", high_risk_count)
        k3.metric("Avg Impact", f"{avg_impact}/10")

        g1, g2 = st.columns(2)

        with g1:
            if "topic" in fr:
                fig_topic = px.pie(
                    fr["topic"],
                    names="topic",
                    values="count",
                    hole=0.5
                )
                fig_topic.update_layout(
                    margin=dict(t=10, b=10, l=10, r=10),
                    height=300,
                    legend_title_text=""
                )
                st.plotly_chart(fig_topic, use_container_width=True)

        with g2:
            if "pri" in fr:
                fig_pri = px.bar(
                    fr["pri"],
                    x="priority",
                    y="count",
                    color="priority",
                    color_discrete_map=PRIORITY_COLORS,
                    text="count"
                )
                fig_pri.update_layout(
                    margin=dict(t=10, b=10, l=10, r=10),
                    height=300,
                    showlegend=False,
                    xaxis_title="",
                    yaxis_title=""
                )
                fig_pri.update_traces(textposition="outside")
                st.plotly_chart(fig_pri, use_container_width=True)

    else:
        st.info("No analytics available.")
# ================================================================
# VIEW: ANALYTICS
# ================================================================
def render_analytics(filtered):
    st.subheader("Analytics Dashboard")
    if filtered.empty:
        st.info("No data.")
        return
    fr = get_frames(filtered)
    t1, t2, t3, t4 = st.tabs(["Distribution", "Heatmap & Scatter", "Trends", "Geography"])
    with t1:
        c1, c2 = st.columns(2)
        if "src" in fr:
            fig = px.bar(fr["src"], x="source", y="count", title="By Source",
                         color="count", color_continuous_scale="Blues")
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c1.plotly_chart(fig, use_container_width=True)
        if "topic" in fr:
            fig = px.pie(fr["topic"], names="topic", values="count", title="Topics", hole=0.4)
            fig.update_layout(margin=dict(t=40, b=20))
            c2.plotly_chart(fig, use_container_width=True)
        c3, c4 = st.columns(2)
        if "pri" in fr:
            fig = px.bar(fr["pri"], x="priority", y="count", title="Priority",
                         color="priority", color_discrete_map=PRIORITY_COLORS)
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c3.plotly_chart(fig, use_container_width=True)
        if "risk" in fr:
            fig = px.bar(fr["risk"], x="risk_level", y="count", title="Risk",
                         color="risk_level",
                         color_discrete_map={"High": "#dc2626", "Medium": "#f59e0b", "Low": "#16a34a"})
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c4.plotly_chart(fig, use_container_width=True)
        c5, c6 = st.columns(2)
        if "score_topic" in fr:
            fig = px.bar(fr["score_topic"], x="topic", y="impact_score",
                         title="Avg Impact by Topic", color="impact_score", color_continuous_scale="OrRd")
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c5.plotly_chart(fig, use_container_width=True)
        if "conf_src" in fr:
            fig = px.bar(fr["conf_src"], x="source", y="confidence_score",
                         title="Avg Confidence by Source", color="confidence_score", color_continuous_scale="Greens")
            fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
            c6.plotly_chart(fig, use_container_width=True)
    with t2:
        if "heatmap" in fr:
            piv = fr["heatmap"].pivot_table(index="topic", columns="risk_level", values="count", fill_value=0)
            fig = px.imshow(piv, text_auto=True, aspect="auto", title="Topic x Risk",
                            color_continuous_scale="YlOrRd")
            fig.update_layout(margin=dict(t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)
        if "scatter" in fr:
            fig = px.scatter(fr["scatter"], x="impact_score", y="confidence_score",
                             color="risk_level", hover_data=["title", "source", "topic"],
                             title="Impact vs Confidence",
                             color_discrete_map={"High": "#dc2626", "Medium": "#f59e0b", "Low": "#16a34a"})
            fig.update_layout(margin=dict(t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)
    with t3:
        if "trend" in fr and not fr["trend"].empty:
            fig = px.area(fr["trend"], x="date_only", y="count", title="Volume Over Time", markers=True)
            fig.update_layout(margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        if "status" in fr:
            fig = px.pie(fr["status"], names="source_status", values="count", title="Data Status", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    with t4:
        if "jur" in fr and not fr["jur"].empty:
            fig = px.bar(fr["jur"], x="jurisdiction", y="count", title="By Jurisdiction",
                         color="count", color_continuous_scale="Viridis")
            fig.update_layout(margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No jurisdiction data.")


# ================================================================
# VIEW: REPORTS
# ================================================================
def render_reports(filtered, ct):
    st.subheader("Report Generator")
    rtype = st.radio("Type", ["Weekly Summary", "Full Report", "Executive Brief"], horizontal=True)
    if rtype == "Weekly Summary":
        txt = weekly_report(filtered, ct)
    elif rtype == "Full Report":
        txt = full_report(filtered, ct)
    else:
        ins = client_insights(filtered, ct)
        txt = (f"EXECUTIVE BRIEF\n{'='*50}\nClient: {ct}\n"
               f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
               f"HEADLINE\n{ins['headline']}\n\nKEY RISK\n{ins['key_risk']}\n\n"
               f"FOCUS\n{ins['focus']}\n\nNEXT STEP\n{ins['next_step']}\n{'='*50}")
    prev = txt.split("\n")[:20]
    st.code("\n".join(prev) + ("\n..." if len(txt.split("\n")) > 20 else ""), language=None)

    pdf = build_pdf(rtype, txt)
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        st.download_button("TXT", txt, f"{sanitize_fn(rtype)}_{sanitize_fn(ct)}.txt", "text/plain", key="r-txt")
    with d2:
        st.download_button("PDF", pdf, f"{sanitize_fn(rtype)}_{sanitize_fn(ct)}.pdf", "application/pdf", key="r-pdf")
    with d3:
        if not filtered.empty:
            st.download_button("CSV", build_csv(filtered), f"data_{sanitize_fn(ct)}.csv", "text/csv", key="r-csv")
    with d4:
        if not filtered.empty:
            st.download_button("Excel", build_excel(filtered), f"data_{sanitize_fn(ct)}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="r-xl")
    if not filtered.empty:
        st.subheader("Stats")
        s1, s2, s3 = st.columns(3)
        s1.metric("Immediate", int((filtered["priority"] == "Immediate").sum()))
        s2.metric("Review", int((filtered["priority"] == "Review").sum()))
        s3.metric("Monitor", int((filtered["priority"] == "Monitor").sum()))
        
def render_updates(filtered, ct):
    st.subheader("Latest Regulatory Updates")

    q = st.text_input(
        "Search updates",
        placeholder="Search by title, topic, source..."
    )

    view_df = search(filtered, q)

    if view_df.empty:
        st.info("No updates found.")
        return

    for idx, row in view_df.iterrows():
        render_card(row, idx, ct)

# ================================================================
# SINGLE UPDATE CARD - guvenli cache okuma
# ================================================================
def render_card(row, idx, ct):
    rid = str(safe_val(row.get("id"), f"row-{idx}"))
    wl = is_watchlisted(rid)
    ai_key = f"ai-{rid}-{ct}"

    # --- GUVENLI CACHE OKUMA ---
    cache = st.session_state.get("ai_cache", {})
    cached = cache.get(ai_key) if isinstance(cache, dict) else None

    if isinstance(cached, dict) and "ai_summary" in cached:
        ai_sum = str(cached.get("ai_summary", "No summary."))
        biz_imp = str(cached.get("business_impact", "No impact."))
        rec_act = str(cached.get("recommended_action", "No action."))
        model = str(cached.get("_model_used", "cached"))
    else:
        ai_sum = str(safe_val(row.get("ai_summary"), "No summary available."))
        biz_imp = str(safe_val(row.get("business_impact"), "No impact analysis."))
        rec_act = str(safe_val(row.get("recommended_action"), "No action available."))
        model = "initial data"

    title = str(safe_val(row.get("title"), "Untitled"))
    source = str(safe_val(row.get("source"), "Unknown"))
    date_s = fmt_date(row.get("date"))
    topic = str(safe_val(row.get("topic"), "Unknown"))
    jur = str(safe_val(row.get("jurisdiction"), "Unknown"))
    url = str(safe_val(row.get("url"), ""))
    rv = str(row.get("risk_level", "Low")).lower()
    bc = RISK_COLORS.get(rv, "#94a3b8")
    sc = row.get("impact_score", 0)
    pri = str(safe_val(row.get("priority"), "Monitor"))
    why = str(safe_val(row.get("why_this_matters"), ""))
    ss = str(safe_val(row.get("source_status"), "unknown"))
    conf = int(row.get("confidence_score", 0))
    fm = str(safe_val(row.get("fetch_method"), "n/a"))
    nr = str(safe_val(row.get("notification_reference"), "n/a"))
    adj_act = adjust_action(rec_act, ct, topic, pri)
    wl_m = "[WL] " if wl else ""

    sc_color = {"live": "#059669", "fallback": "#d97706"}.get(ss.lower(), "#9ca3af")
    r_bg = {"high": "#fee2e2", "medium": "#ffedd5", "low": "#dcfce7"}.get(rv, "#f1f5f9")
    r_fg = {"high": "#b91c1c", "medium": "#c2410c", "low": "#15803d"}.get(rv, "#64748b")
    p_bg = {"Immediate": "#fee2e2", "Review": "#fef3c7", "Monitor": "#dbeafe"}.get(pri, "#f1f5f9")
    p_fg = {"Immediate": "#991b1b", "Review": "#92400e", "Monitor": "#1d4ed8"}.get(pri, "#64748b")
    co_bg = "#dcfce7" if conf >= 85 else ("#fef3c7" if conf >= 60 else "#fee2e2")
    co_fg = "#166534" if conf >= 85 else ("#92400e" if conf >= 60 else "#991b1b")
    ps = "display:inline-block;padding:0.2rem 0.5rem;border-radius:999px;font-size:0.68rem;font-weight:700;"
    pct = min(sc / 10 * 100, 100)
    bar_c = "#dc2626" if sc >= 8 else ("#f59e0b" if sc >= 5 else "#3b82f6")
    bs = "margin-top:0.3rem;padding:0.4rem 0.6rem;background:#f8fafc;border-radius:8px;border:1px solid #f1f5f9;"
    ts = "font-size:0.68rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:0.1rem;"
    vs = "font-size:0.82rem;color:#1e293b;line-height:1.5;"

    # Header
    st.markdown(
        f'<div style="border-left:5px solid {bc};border-radius:14px;'
        f'padding:0.9rem 1rem;background:white;box-shadow:0 4px 16px rgba(0,0,0,0.05);'
        f'border:1px solid #e2e8f0;">'
        f'<span style="{ps}background:rgba(0,0,0,0.04);color:{sc_color};">{ss.upper()}</span>'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-top:0.25rem;">'
        f'<div style="font-size:0.98rem;font-weight:700;color:#0f172a;line-height:1.3;flex:1;">'
        f'{wl_m}{title}</div>'
        f'<div style="background:#0f172a;color:white;border-radius:10px;padding:0.2rem 0.5rem;'
        f'font-size:0.74rem;font-weight:700;margin-left:8px;white-space:nowrap;">{sc}/10</div></div>'
        f'<div style="font-size:0.78rem;color:#64748b;margin-top:0.2rem;">'
        f'{source} &middot; {date_s} &middot; {jur}</div>'
        f'<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.1rem;">'
        f'Fetch: {fm} &middot; Ref: {nr} &middot; Model: {model}</div></div>',
        unsafe_allow_html=True,
    )

    # Pills
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin:0.3rem 0;">'
        f'<span style="{ps}background:#eef2ff;color:#4338ca;">{source}</span>'
        f'<span style="{ps}background:#e0f2fe;color:#0369a1;">{topic}</span>'
        f'<span style="{ps}background:{r_bg};color:{r_fg};">{rv.title()} Risk</span>'
        f'<span style="{ps}background:{p_bg};color:{p_fg};">{pri}</span>'
        f'<span style="{ps}background:{co_bg};color:{co_fg};">Conf. {conf}</span></div>',
        unsafe_allow_html=True,
    )

    # Score bar
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin:0.2rem 0;">'
        f'<div style="flex:1;background:#f1f5f9;border-radius:999px;height:5px;overflow:hidden;">'
        f'<div style="width:{pct}%;background:{bar_c};height:100%;border-radius:999px;"></div></div>'
        f'<span style="font-size:0.76rem;font-weight:700;color:{bar_c};">{sc}/10</span></div>',
        unsafe_allow_html=True,
    )

    # Content blocks - HER BIRI AYRI
    for bt, bv in [("AI Summary", ai_sum), ("Why This Matters", why),
                   ("Business Impact", biz_imp), ("Recommended Action", adj_act)]:
        st.markdown(
            f'<div style="{bs}"><div style="{ts}">{bt}</div><div style="{vs}">{bv}</div></div>',
            unsafe_allow_html=True,
        )

    # Buttons
    enriched = {**row.to_dict(), "ai_summary": ai_sum, "business_impact": biz_imp, "recommended_action": adj_act}
    alert = build_alert(enriched, ct, sc, pri, why)
    sf = sanitize_fn(title)
    pdf = build_pdf(f"Alert - {title}", alert)

    b1, b2, b3, b4, b5 = st.columns(5)
    with b1:
        if st.button("Remove WL" if wl else "Add WL", key=f"wl-{rid}"):
            toggle_watchlist(rid)
            st.rerun()
    with b2:
        if st.button("AI Analyze", key=f"aib-{rid}-{ct}"):
            with st.spinner("Analyzing..."):
                res = ai_analyze(row, ct)
                if "ai_cache" not in st.session_state:
                    st.session_state["ai_cache"] = {}
                st.session_state["ai_cache"][ai_key] = res
                st.rerun()
    with b3:
        st.download_button("TXT", alert, f"{sf}.txt", "text/plain", key=f"t-{rid}-{ct}")
    with b4:
        st.download_button("PDF", pdf, f"{sf}.pdf", "application/pdf", key=f"p-{rid}-{ct}")
    with b5:
        if url and url != "n/a":
            st.link_button("Source", url)

    with st.expander("Notes & Raw Text"):
        nv = get_user_note(rid)
        nn = st.text_area("Note", value=nv, key=f"n-{rid}", placeholder="Add note...", height=70)
        if nn != nv:
            save_user_note(rid, nn)
        st.text_area("Raw", value=str(safe_val(row.get("raw_text"), "No raw text.")),
                      height=100, disabled=True, key=f"raw-{rid}")

    st.divider()


# ================================================================
# VIEW: WATCHLIST
# ================================================================
def render_watchlist(filtered, ct):
    st.subheader("Watchlist")

    work_items = load_work_items()
    saved_items = [x for x in work_items if str(x.get("type", "")) == "watchlist"]

    if not saved_items:
        st.info("Watchlist is empty.")
        return

    st.caption(f"{len(saved_items)} saved watchlist item(s)")

    for item in reversed(saved_items):
        rid = str(item.get("id", ""))
        title = safe_val(item.get("title"), "Untitled")
        source = safe_val(item.get("source"), "Unknown")
        pri = safe_val(item.get("priority"), "Monitor")
        rv = str(safe_val(item.get("risk_level"), "Low")).lower()
        url = safe_val(item.get("url"), "")
        created_at = safe_val(item.get("created_at"), "n/a")

        bc = RISK_COLORS.get(rv, "#94a3b8")
        r_bg = {"high": "#fee2e2", "medium": "#ffedd5", "low": "#dcfce7"}.get(rv, "#f1f5f9")
        r_fg = {"high": "#b91c1c", "medium": "#c2410c", "low": "#15803d"}.get(rv, "#64748b")
        p_bg = {"Immediate": "#fee2e2", "Review": "#fef3c7", "Monitor": "#dbeafe"}.get(pri, "#f1f5f9")
        p_fg = {"Immediate": "#991b1b", "Review": "#92400e", "Monitor": "#1d4ed8"}.get(pri, "#64748b")
        ps = "display:inline-block;padding:0.2rem 0.5rem;border-radius:999px;font-size:0.68rem;font-weight:700;"

        st.markdown(
            f'<div style="border-left:5px solid {bc};border-radius:14px;'
            f'padding:0.9rem 1rem;background:linear-gradient(135deg,#fffbeb 0%,#fff 100%);'
            f'box-shadow:0 4px 16px rgba(0,0,0,0.05);border:1px solid #e2e8f0;'
            f'border-right:3px solid #f59e0b;">'
            f'<div style="font-size:0.98rem;font-weight:700;color:#0f172a;line-height:1.3;">'
            f'[WL] {title}</div>'
            f'<div style="font-size:0.78rem;color:#64748b;margin-top:0.25rem;">'
            f'{source} &middot; Saved: {created_at}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin:0.35rem 0;">'
            f'<span style="{ps}background:#eef2ff;color:#4338ca;">{source}</span>'
            f'<span style="{ps}background:{r_bg};color:{r_fg};">{rv.title()} Risk</span>'
            f'<span style="{ps}background:{p_bg};color:{p_fg};">{pri}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)

        with c1:
            if url and url != "n/a":
                st.link_button("Source", url)

        with c2:
            if st.button("Remove", key=f"rm_wl_{rid}_{created_at}"):
                remove_work_item(rid, "watchlist")
                st.success("Removed from watchlist")
                st.rerun()

        st.divider()

# ================================================================
# VIEW: COMPARISON
# ================================================================
def render_comparison(filtered, ct):
    st.subheader("Comparison View")
    if filtered.empty or "date" not in filtered.columns:
        st.info("Not enough data.")
        return

    dates = filtered["date"].dropna()
    if dates.empty:
        st.info("No date data.")
        return

    min_d = dates.min().date()
    max_d = dates.max().date()
    mid_d = min_d + (max_d - min_d) / 2

    st.markdown("**Period Comparison**")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("*Period 1*")
        p1s = st.date_input("P1 Start", value=min_d, key="p1s")
        p1e = st.date_input("P1 End", value=mid_d, key="p1e")
    with c2:
        st.markdown("*Period 2*")
        p2s = st.date_input("P2 Start", value=mid_d + timedelta(days=1), key="p2s")
        p2e = st.date_input("P2 End", value=max_d, key="p2e")

    p1 = filtered[(filtered["date"].dt.date >= p1s) & (filtered["date"].dt.date <= p1e)]
    p2 = filtered[(filtered["date"].dt.date >= p2s) & (filtered["date"].dt.date <= p2e)]

    metrics = {
        "Total": (len(p1), len(p2)),
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

    rows = []
    for name, (v1, v2) in metrics.items():
        d = v2 - v1
        rows.append({"Metric": name, "Period 1": v1, "Period 2": v2,
                      "Change": f"+{d}" if d > 0 else str(d)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if not p1.empty and not p2.empty and "topic" in filtered.columns:
        t1 = p1["topic"].value_counts().reset_index()
        t1.columns = ["topic", "Period 1"]
        t2 = p2["topic"].value_counts().reset_index()
        t2.columns = ["topic", "Period 2"]
        m = t1.merge(t2, on="topic", how="outer").fillna(0)
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Period 1", x=m["topic"], y=m["Period 1"], marker_color="#3b82f6"))
        fig.add_trace(go.Bar(name="Period 2", x=m["topic"], y=m["Period 2"], marker_color="#f59e0b"))
        fig.update_layout(barmode="group", title="Topics: P1 vs P2", margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Client Type Comparison**")
    sel = st.multiselect("Compare types", CLIENT_TYPES, default=[ct])
    if sel and not filtered.empty:
        cr = []
        for c in sel:
            tmp = filtered.copy()
            tmp["_i"] = tmp.apply(lambda r: calc_impact(r, c), axis=1)
            tmp["_p"] = tmp["_i"].apply(det_priority)
            cr.append({
                "Client": c,
                "Avg Impact": round(tmp["_i"].mean(), 1),
                "Immediate": int((tmp["_p"] == "Immediate").sum()),
                "Review": int((tmp["_p"] == "Review").sum()),
                "Monitor": int((tmp["_p"] == "Monitor").sum()),
            })
        cdf = pd.DataFrame(cr)
        st.dataframe(cdf, use_container_width=True, hide_index=True)
        mel = cdf.melt(id_vars="Client", value_vars=["Immediate", "Review", "Monitor"])
        fig = px.bar(mel, x="Client", y="value", color="variable",
                     barmode="group", title="Priority by Client",
                     color_discrete_map=PRIORITY_COLORS)
        fig.update_layout(margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)


# ================================================================
# APP INITIALIZATION
# ================================================================
ensure_data_dir()
analytics = load_analytics()

if "visited" not in st.session_state:
    analytics["visits"] += 1
    st.session_state["visited"] = True
    save_analytics(analytics)

auto_triggered = False
auto_msg = None

if should_auto_refresh(LIVE_DATA_FILE, AUTO_REFRESH_MINUTES):
    try:
        refresh_live_data()
        auto_triggered = True
        auto_msg = f"Auto-refresh completed (every {AUTO_REFRESH_MINUTES} min)."
    except Exception:
        auto_msg = "Auto-refresh failed. Showing existing data."

if WATCHLIST_FILE.exists():
    st.session_state["watchlist"] = load_watchlist()
if NOTES_FILE.exists():
    st.session_state["user_notes"] = load_user_notes()

combine_data.clear()
df = combine_data()

if not df.empty:
    df["confidence_score"] = df.apply(calc_confidence, axis=1)


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
        ["Overview", "Updates", "Analytics", "Reports", "Watchlist", "Worklist", "Comparison"]
    )

    st.divider()

    if st.button("Refresh Live Data", width="stretch"):
        with st.spinner("Fetching from EFSA & RASFF..."):
            try:
                refresh_live_data()
                combine_data.clear()
                st.success("Refreshed.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")
    last_upd = format_relative_time(LIVE_DATA_FILE)
    st.caption(f"Last updated: {last_upd}")

    try:
        has_or = bool(st.secrets.get("OPENROUTER_API_KEY", ""))
    except Exception:
        has_or = False
    if has_or:
        st.success("OpenRouter connected")
    else:
        st.info("Local AI mode")

    st.divider()
    st.markdown("**Filters**")

    sel_src = []
    sel_top = []
    sel_risk = []
    d_mode = "All"
    min_conf = 0
    d_range = None

    if not df.empty:
        so = sorted(df["source"].dropna().astype(str).unique().tolist()) if "source" in df.columns else []
        to = sorted(df["topic"].dropna().astype(str).unique().tolist()) if "topic" in df.columns else []
        ro = sorted(df["risk_level"].dropna().astype(str).unique().tolist()) if "risk_level" in df.columns else []

        sel_src = st.multiselect("Source", so, default=so)
        sel_top = st.multiselect("Topic", to, default=to)
        sel_risk = st.multiselect("Risk", ro, default=ro)
        d_mode = st.radio("Data Mode", ["All", "Live Only", "Fallback Only"], horizontal=True)
        min_conf = st.slider("Min Confidence", 0, 100, 0, 5)

        if "date" in df.columns:
            vd = df["date"].dropna()
            if not vd.empty:
                d_range = st.date_input("Date Range",
                                        value=(vd.min().date(), vd.max().date()),
                                        min_value=vd.min().date(),
                                        max_value=vd.max().date())

    wlc = len(st.session_state.get("watchlist", []))
    if wlc:
        st.caption(f"Watchlist: {wlc} item(s)")


# ================================================================
# MAIN AREA
# ================================================================
# Hero stats
h_total = len(df)
h_imm = 0
h_avg = 0
h_live = 0

if not df.empty:
    t_imp = df.apply(lambda r: calc_impact(r, client_type), axis=1)
    t_pri = t_imp.apply(det_priority)
    h_imm = int((t_pri == "Immediate").sum())
    h_avg = round(t_imp.mean(), 1)
    if "source_status" in df.columns:
        lc = (df["source_status"].astype(str).str.lower() == "live").sum()
        h_live = int(lc / h_total * 100) if h_total > 0 else 0

render_hero(client_type, last_upd, h_total, h_imm, h_avg, h_live)

if auto_msg:
    if auto_triggered:
        st.success(auto_msg)
    else:
        st.warning(auto_msg)

render_strip(client_type)

if df.empty:
    st.warning("No data. Click Refresh Live Data.")
    st.stop()

# ================================================================
# APPLY FILTERS
# ================================================================
filtered = df.copy()

if sel_src and "source" in filtered.columns:
    filtered = filtered[filtered["source"].isin(sel_src)]
if sel_top and "topic" in filtered.columns:
    filtered = filtered[filtered["topic"].isin(sel_top)]
if sel_risk and "risk_level" in filtered.columns:
    filtered = filtered[filtered["risk_level"].isin(sel_risk)]
if d_mode == "Live Only" and "source_status" in filtered.columns:
    filtered = filtered[filtered["source_status"].astype(str).str.lower() == "live"]
elif d_mode == "Fallback Only" and "source_status" in filtered.columns:
    filtered = filtered[filtered["source_status"].astype(str).str.lower() == "fallback"]
if "confidence_score" in filtered.columns:
    filtered = filtered[filtered["confidence_score"] >= min_conf]
if d_range and len(d_range) == 2 and "date" in filtered.columns:
    sd, ed = d_range
    filtered = filtered[filtered["date"].dt.date.between(sd, ed).fillna(False)]

# Consulting fields
if not filtered.empty:
    filtered = filtered.copy()
    filtered["impact_score"] = filtered.apply(lambda r: calc_impact(r, client_type), axis=1)
    filtered["priority"] = filtered["impact_score"].apply(det_priority)
    filtered["why_this_matters"] = filtered.apply(lambda r: get_why(r, client_type), axis=1)

# ================================================================
# ROUTE
# ================================================================
if view_mode == "Overview":
    render_overview(filtered, client_type)
elif view_mode == "Updates":
    render_updates(filtered, client_type)
elif view_mode == "Analytics":
    render_analytics(filtered)
elif view_mode == "Reports":
    render_reports(filtered, client_type)
elif view_mode == "Watchlist":
    render_watchlist(filtered, client_type)
elif view_mode == "Comparison":
    render_comparison(filtered, client_type)

# ================================================================
# FOOTER
# ================================================================
st.divider()
st.caption("Food Regulatory Intelligence Dashboard v2.0 | Horizon scanning, client intelligence, consulting outputs, analytics")
