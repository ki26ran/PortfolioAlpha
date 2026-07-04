#!/usr/bin/env python3
"""
PortfolioAlpha — Data Sync Agent.

Usage:
    python agents/data_sync.py              # Quick sync (7d daily, 3d 5m, 2d 1m)
    python agents/data_sync.py --full        # Full sync (3y daily, 60d 5m, 30d 1m)
    python agents/data_sync.py --daily       # Daily only
    python agents/data_sync.py --intraday    # Intraday only (5m + 1m)

Designed for cron/systemd. Logs to data/sync_log.txt.
Dashboard page: reports/sync_status.py
"""
import os, sys, time, argparse
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from common.market_data.cache import get_cache

SYNC_LOG = os.path.join(BASE, "data", "sync_log.txt")
os.makedirs(os.path.dirname(SYNC_LOG), exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(SYNC_LOG, "a") as f:
        f.write(line + "\n")


def sync_daily(cache, full=False):
    tickers = cache.get_universe("nifty200")
    ago = 1095 if full else 7
    start = (datetime.now() - timedelta(days=ago)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    log(f"Daily sync: {len(tickers)} tickers {start} to {end}")
    t0 = time.time()
    result = cache._bulk_fetch_daily(tickers, start, end)
    elapsed = time.time() - t0
    log(f"  Done — {result['batches_fetched']} batches, {elapsed:.0f}s")


def sync_intraday(cache, interval, days_back, label, full=False):
    tickers = cache.get_universe("nifty200")
    ago = 60 if full else days_back
    start = (datetime.now() - timedelta(days=ago)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    log(f"{label} sync: {len(tickers)} tickers {start} to {end}")
    t0 = time.time()
    result = cache._bulk_fetch_intraday(tickers, interval, start, end)
    elapsed = time.time() - t0
    log(f"  Done — {result['batches_fetched']} batches, {elapsed:.0f}s")
    return result


def run_sync(full=False, daily=True, intraday=True):
    cache = get_cache()
    log(f"Provider: {type(cache.provider).__name__}")
    log(f"Mode: {'FULL' if full else 'QUICK'} sync")

    if daily:
        sync_daily(cache, full)
    if intraday:
        sync_intraday(cache, "5m", 3, "5-min", full)
        sync_intraday(cache, "1m", 2, "1-min", full)

    log("Data sync complete")


def get_status():
    if not os.path.exists(SYNC_LOG):
        return {"last_sync": None, "lines": 0}
    with open(SYNC_LOG) as f:
        lines = f.readlines()
    last = lines[-1].strip() if lines else None
    return {"last_sync": last, "lines": len(lines)}


def get_sync_log(n=20):
    if not os.path.exists(SYNC_LOG):
        return []
    with open(SYNC_LOG) as f:
        lines = f.readlines()
    return [l.strip() for l in lines[-n:]]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PortfolioAlpha Data Sync")
    parser.add_argument("--full", action="store_true", help="Full sync (3y daily, 60d 5m, 30d 1m)")
    parser.add_argument("--daily", action="store_true", help="Daily only")
    parser.add_argument("--intraday", action="store_true", help="Intraday only (5m + 1m)")
    args = parser.parse_args()

    run_sync(
        full=args.full,
        daily=not args.intraday or args.daily,
        intraday=not args.daily or args.intraday,
    )
