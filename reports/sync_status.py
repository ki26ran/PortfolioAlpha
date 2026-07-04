import streamlit as st
import os, sys, json
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
ROOT = os.path.dirname(BASE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common.market_data.cache import get_cache

SYNC_LOG = os.path.join(BASE, "data", "sync_log.txt")
RESULT_FILE = os.path.join(BASE, "data", "last_sync_result.json")

CSS = """
<style>
    .metric-card { border-radius: 8px; padding: 10px 14px; margin: 4px 0; border-left: 4px solid; background: #1a1a2e; }
    .sync-ok { color: #00e676; font-weight: 700; }
    .sync-label { color: #888; font-size: 0.85rem; }
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
        con = cache._db_read()
        stats = {}
        for tf, table in [("Daily", "daily_bars"), ("5-min", "bars_5min"), ("1-min", "bars_1min")]:
            row = con.execute(f"SELECT COUNT(DISTINCT ticker), COUNT(*) FROM {table}").fetchone()
            r2 = con.execute(f"SELECT MAX(date)::VARCHAR FROM {table}").fetchone() if tf == "Daily" else con.execute(f"SELECT MAX(datetime_ist)::VARCHAR FROM {table}").fetchone()
            stats[tf] = {"tickers": row[0] or 0, "rows": row[1] or 0, "last_date": r2[0][:10] if r2 and r2[0] else "-"}
        con.close()
        return stats
    except Exception as e:
        return {"error": str(e)}


def get_last_result():
    if not os.path.exists(RESULT_FILE):
        return None
    with open(RESULT_FILE) as f:
        return json.load(f)


def show():
    st.title("Data Sync")
    st.markdown(CSS, unsafe_allow_html=True)

    # ── Last sync result ──────────────────────────────────
    last = get_last_result()
    if last:
        finished = last.get("finished_at", "")
        if finished:
            try:
                dt = datetime.fromisoformat(finished)
                st.caption(f"Last sync: {dt.strftime('%d-%b %Y %H:%M')}  |  {last['mode']}  |  {last['provider']}  |  {last['total_seconds']}s")
            except Exception:
                st.caption(f"Last sync: {last['mode']} | {last['total_seconds']}s")

        cols = st.columns(3)
        for i, tf in enumerate(["daily", "5m", "1m"]):
            if tf in last:
                d = last[tf]
                after = last.get("counts_after", {}).get(tf, {})
                rows = after.get("rows", 0)
                tickers = after.get("tickers", 0)
                label = {"daily": "Daily", "5m": "5-min", "1m": "1-min"}[tf]
                with cols[i]:
                    st.metric(f"{label} Bars", f"{rows:,}", help=f"{tickers} tickers")
        st.divider()

    # ── Current DB stats ──────────────────────────────────
    stats = get_db_stats()
    if "error" not in stats:
        cols = st.columns(3)
        for i, (tf, data) in enumerate(stats.items()):
            with cols[i]:
                st.metric(f"{tf} Bars", f"{data['rows']:,}",
                          help=f"{data['tickers']} tickers | Last: {data['last_date']}")
    else:
        st.error(f"DB error: {stats['error']}")

    # ── Run sync button ───────────────────────────────────
    st.divider()
    if st.button("Run Sync Now", type="primary", use_container_width=True):
        with st.spinner("Syncing data (daily + 5m + 1m)..."):
            from agents.data_sync import run_sync
            try:
                result = run_sync()
                st.success(f"Sync complete — {result['total_seconds']}s")
            except Exception as e:
                st.error(f"Sync failed: {e}")
        st.rerun()

    # ── Sync log ──────────────────────────────────────────
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
- Schedule: Daily at 08:00, weekdays only
""")
