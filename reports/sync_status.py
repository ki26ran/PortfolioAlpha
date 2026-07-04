import streamlit as st
import os, sys, time
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
ROOT = os.path.dirname(BASE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common.market_data.cache import get_cache

SYNC_LOG = os.path.join(BASE, "data", "sync_log.txt")

CSS = """
<style>
    .metric-card { border-radius: 8px; padding: 10px 14px; margin: 4px 0; border-left: 4px solid; background: #1a1a2e; }
    .status-ok { color: #00e676; font-weight: 600; }
    .status-warn { color: #ffd740; font-weight: 600; }
    .status-err { color: #ff5252; font-weight: 600; }
</style>
"""


def get_sync_log(n=30):
    if not os.path.exists(SYNC_LOG):
        return []
    with open(SYNC_LOG) as f:
        lines = f.readlines()
    return [l.strip() for l in lines[-n:]]


def get_db_stats():
    try:
        cache = get_cache()
        bars = cache._db_read()
        stats = {}
        for tf, table in [("Daily", "daily_bars"), ("5-min", "bars_5min"), ("1-min", "bars_1min")]:
            row = bars.execute(f"SELECT COUNT(DISTINCT ticker), COUNT(*) FROM {table}").fetchone()
            stats[tf] = {"tickers": row[0] or 0, "bars": row[1] or 0}
        bars.close()
        return stats
    except Exception as e:
        return {"error": str(e)}


def show():
    st.title("Data Sync")
    st.markdown(CSS, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    stats = get_db_stats()
    if "error" not in stats:
        col1.metric("Daily Bars", f"{stats['Daily']['bars']:,}", help=f"{stats['Daily']['tickers']} tickers")
        col2.metric("5-min Bars", f"{stats['5-min']['bars']:,}", help=f"{stats['5-min']['tickers']} tickers")
        col3.metric("1-min Bars", f"{stats['1-min']['bars']:,}", help=f"{stats['1-min']['tickers']} tickers")
    else:
        st.error(f"DB error: {stats['error']}")

    st.divider()

    if st.button("Run Sync Now", type="primary", use_container_width=True):
        with st.spinner("Syncing daily data..."):
            from agents.data_sync import run_sync
            run_sync()
        st.success("Sync complete!")
        st.rerun()

    st.divider()
    st.subheader("Sync Log")
    logs = get_sync_log(50)
    if logs:
        st.code("\n".join(reversed(logs)), language="bash", line_height=1.2)
    else:
        st.info("No sync logs yet. Run a sync to populate.")

    st.divider()
    st.subheader("Scheduling")
    st.markdown("""
**Ubuntu** — Create `/etc/cron.d/portfolioalpha-sync`:
```
# Market data sync (Mon-Fri)
30 8 * * 1-5 root cd /path/to/PortfolioAlpha && python3 agents/data_sync.py >> /var/log/portfolioalpha-sync.log 2>&1
```

**Windows** — Use **Scheduler** page to create a task:
- Script: `python agents/data_sync.py`
- Schedule: Daily at 08:30, weekdays only
""")
