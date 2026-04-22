import streamlit as st
import pandas as pd
import json
from scrapers.efsa_rss_scraper import fetch_efsa_updates
from scrapers.rasff_scraper import fetch_rasff_updates

st.set_page_config(layout="wide")

st.title("Food Regulatory Intelligence Dashboard")

# DATA LOAD
def load_data():
    try:
        with open("data/regulatory_data.json") as f:
            return pd.DataFrame(json.load(f))
    except:
        return pd.DataFrame()

def load_live():
    try:
        with open("data/live_updates.json") as f:
            return pd.DataFrame(json.load(f))
    except:
        return pd.DataFrame()

# REFRESH BUTTON
if st.button("🔄 Refresh Live Data"):
    efsa = fetch_efsa_updates()
    rasff = fetch_rasff_updates()

    live = efsa + rasff

    with open("data/live_updates.json", "w") as f:
        json.dump(live, f)

    st.success("Live data updated!")

# COMBINE
df = pd.concat([load_live(), load_data()])

if df.empty:
    st.warning("No data found")
    st.stop()

# FILTERS
source = st.sidebar.multiselect("Source", df["source"].unique(), default=df["source"].unique())
topic = st.sidebar.multiselect("Topic", df["topic"].unique(), default=df["topic"].unique())

df = df[df["source"].isin(source)]
df = df[df["topic"].isin(topic)]

# DISPLAY
for _, row in df.iterrows():
    with st.container():
        st.subheader(row["title"])

        st.write(f"**Source:** {row['source']} | **Date:** {row['date']}")
        st.write(f"**Topic:** {row['topic']} | **Risk:** {row.get('risk_level','Medium')}")

        st.markdown("**AI Summary**")
        st.write(row.get("ai_summary",""))

        st.markdown("**Business Impact**")
        st.write(row.get("business_impact",""))

        st.markdown("**Recommended Action**")
        st.write(row.get("recommended_action",""))

        st.divider()
