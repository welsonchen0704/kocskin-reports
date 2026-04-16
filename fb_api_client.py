"""
Facebook Marketing API client — pulls ad insights.
Replaces the manual CSV upload for KOCSKIN FB ads.

Requires:
  FB_ACCESS_TOKEN      — Long-Lived User Token (60-day) or System User Token
  FB_AD_ACCOUNT_ID     — e.g. act_2053421094961197

Returns records with the same shape as the former CSV parser output,
so downstream aggregation code is unchanged.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("kocskin_report.fb")

GRAPH_VERSION = "v19.0"
BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Fields we want at the ad level (equivalent to the original CSV)
INSIGHT_FIELDS = ",".join([
    "date_start", "date_stop",
    "ad_name", "ad_id",
    "adset_name", "adset_id",
    "campaign_name", "campaign_id",
    "spend", "impressions", "reach", "frequency",
    "actions", "action_values",
    "purchase_roas",
    "cpm",
    "cost_per_action_type",
])


class FbApiError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------

def check_token_expiry(token: str) -> Dict[str, Any]:
    """
    Returns a dict with:
      - is_valid (bool)
      - expires_at (ISO str or None — None means never expires / system user)
      - days_left (int or None)
      - raw (dict) — FB's debug response
    """
    url = f"{BASE}/debug_token"
    params = {"input_token": token, "access_token": token}
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        raise FbApiError(f"debug_token failed: {r.status_code} {r.text[:200]}")
    data = r.json().get("data", {})
    is_valid = bool(data.get("is_valid"))
    exp_unix = data.get("expires_at")  # 0 = never expires (system user)
    expires_at = None
    days_left = None
    if exp_unix and exp_unix > 0:
        expires_at_dt = datetime.fromtimestamp(exp_unix, tz=timezone.utc)
        expires_at = expires_at_dt.isoformat()
        days_left = (expires_at_dt - datetime.now(timezone.utc)).days
    return {
        "is_valid": is_valid,
        "expires_at": expires_at,
        "days_left": days_left,
        "raw": data,
    }


def warn_if_expiring(info: Dict[str, Any], threshold_days: int = 10) -> None:
    """Log red warning if token <= threshold days to expiry."""
    if not info.get("is_valid"):
        logger.error("⚠️⚠️⚠️ FB TOKEN IS INVALID! ⚠️⚠️⚠️")
        logger.error("   Raw: %s", info.get("raw"))
        return
    dl = info.get("days_left")
    if dl is None:
        logger.info("FB token: never expires (System User) ✓")
        return
    if dl <= threshold_days:
        logger.error(
            "⚠️⚠️⚠️ FB TOKEN EXPIRING in %d DAYS (%s) — RENEW NOW ⚠️⚠️⚠️",
            dl, info.get("expires_at"),
        )
        logger.error("   Go to: https://developers.facebook.com/tools/explorer/")
        logger.error("   Or better: set up a System User Token to avoid this entirely.")
    else:
        logger.info("FB token: valid, %d days left (expires %s)", dl, info.get("expires_at"))


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def _extract_purchases(actions: Optional[List[Dict]]) -> float:
    """Sum purchase-type actions (offsite_conversion.fb_pixel_purchase)."""
    if not actions:
        return 0.0
    total = 0.0
    for a in actions:
        t = a.get("action_type", "")
        if t in ("offsite_conversion.fb_pixel_purchase", "purchase", "omni_purchase"):
            try:
                total += float(a.get("value", 0))
            except (TypeError, ValueError):
                pass
            break  # use the first matching purchase type to avoid double-counting
    return total


def _extract_purchase_roas(purchase_roas: Optional[List[Dict]]) -> float:
    """Extract the primary purchase ROAS value."""
    if not purchase_roas:
        return 0.0
    for r in purchase_roas:
        t = r.get("action_type", "")
        if t in ("offsite_conversion.fb_pixel_purchase", "purchase", "omni_purchase"):
            try:
                return float(r.get("value", 0))
            except (TypeError, ValueError):
                return 0.0
    # fallback: first entry
    try:
        return float(purchase_roas[0].get("value", 0))
    except (TypeError, ValueError, IndexError):
        return 0.0


def _fetch_page(url: str, params: Dict[str, Any], retries: int = 3) -> Dict[str, Any]:
    last_exc = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (500, 502, 503, 504, 429):
                wait = 2 ** i
                logger.warning("FB API %s, retry in %ds", r.status_code, wait)
                time.sleep(wait)
                continue
            raise FbApiError(f"FB API {r.status_code}: {r.text[:300]}")
        except requests.RequestException as e:
            last_exc = e
            time.sleep(2 ** i)
    raise FbApiError(f"FB API failed after {retries} retries: {last_exc}")


def fetch_ad_insights(
    token: str,
    ad_account_id: str,
    since: str,
    until: str,
) -> List[Dict[str, Any]]:
    """
    Fetches ad-level insights for [since, until] (inclusive, YYYY-MM-DD).

    Pulls BOTH active and paused ads via the ads endpoint + insights.edge,
    returning one record per ad. Active / inactive is determined by each ad's
    effective_status.

    Returns a list of dicts with the SAME keys our old CSV parser produced, so
    downstream aggregation (in generate_report.py) works unchanged.
    """
    if not ad_account_id.startswith("act_"):
        ad_account_id = f"act_{ad_account_id}"

    # Step 1: list ads (id, name, effective_status, adset_name, campaign_name)
    ads_url = f"{BASE}/{ad_account_id}/ads"
    ads: List[Dict[str, Any]] = []
    ads_params = {
        "access_token": token,
        "fields": "id,name,effective_status,adset{name,id},campaign{name,id}",
        "limit": 500,
    }
    url = ads_url
    params = ads_params
    while True:
        page = _fetch_page(url, params)
        ads.extend(page.get("data", []))
        nxt = page.get("paging", {}).get("next")
        if not nxt:
            break
        url, params = nxt, {}
    logger.info("FB: fetched %d ads in account", len(ads))

    # Build a lookup: ad_id -> metadata
    meta: Dict[str, Dict[str, Any]] = {}
    for ad in ads:
        meta[ad["id"]] = {
            "ad_name": ad.get("name"),
            "effective_status": ad.get("effective_status"),
            "adset_name": (ad.get("adset") or {}).get("name"),
            "adset_id": (ad.get("adset") or {}).get("id"),
            "campaign_name": (ad.get("campaign") or {}).get("name"),
            "campaign_id": (ad.get("campaign") or {}).get("id"),
        }

    # Step 2: pull insights at account level, level=ad (one call, paginated)
    insights_url = f"{BASE}/{ad_account_id}/insights"
    insights_params = {
        "access_token": token,
        "level": "ad",
        "fields": INSIGHT_FIELDS,
        "time_range": f'{{"since":"{since}","until":"{until}"}}',
        "time_increment": "all_days",
        "limit": 500,
    }
    insight_rows: List[Dict[str, Any]] = []
    url = insights_url
    params = insights_params
    while True:
        page = _fetch_page(url, params)
        insight_rows.extend(page.get("data", []))
        nxt = page.get("paging", {}).get("next")
        if not nxt:
            break
        url, params = nxt, {}
    logger.info("FB: fetched %d insight rows for %s ~ %s",
                len(insight_rows), since, until)

    # Step 3: normalize into the CSV-compatible shape
    records: List[Dict[str, Any]] = []
    seen_ad_ids = set()
    for row in insight_rows:
        ad_id = row.get("ad_id") or row.get("id")
        seen_ad_ids.add(ad_id)
        m = meta.get(ad_id, {})
        purchases = _extract_purchases(row.get("actions"))
        roas = _extract_purchase_roas(row.get("purchase_roas"))
        effective = (m.get("effective_status") or "").upper()
        status_label = "active" if effective == "ACTIVE" else "inactive"
        records.append({
            "分析報告開始": row.get("date_start", since),
            "分析報告結束": row.get("date_stop", until),
            "廣告名稱": row.get("ad_name") or m.get("ad_name"),
            "廣告投遞": status_label,
            "成果": int(purchases) if purchases else None,
            "花費金額 (TWD)": float(row.get("spend", 0) or 0),
            "曝光次數": int(row.get("impressions", 0) or 0),
            "觸及人數": int(row.get("reach", 0) or 0),
            "廣告組合名稱": row.get("adset_name") or m.get("adset_name") or "未分組",
            "購買 ROAS（廣告投資報酬率）": roas,
            "頻率": float(row.get("frequency", 0) or 0),
            "購買次數": int(purchases),
            "歸因設定": "點擊後 7 天",
            "_ad_id": ad_id,
            "_effective_status": effective,
        })

    # Include ads that had ZERO spend (no insights row) so the "total ads" count is accurate
    for ad_id, m in meta.items():
        if ad_id in seen_ad_ids:
            continue
        effective = (m.get("effective_status") or "").upper()
        status_label = "active" if effective == "ACTIVE" else "inactive"
        records.append({
            "分析報告開始": since,
            "分析報告結束": until,
            "廣告名稱": m.get("ad_name"),
            "廣告投遞": status_label,
            "成果": None,
            "花費金額 (TWD)": 0.0,
            "曝光次數": 0,
            "觸及人數": 0,
            "廣告組合名稱": m.get("adset_name") or "未分組",
            "購買 ROAS（廣告投資報酬率）": 0.0,
            "頻率": 0.0,
            "購買次數": 0,
            "歸因設定": "點擊後 7 天",
            "_ad_id": ad_id,
            "_effective_status": effective,
        })

    logger.info("FB: normalized %d records (%d with spend, %d without)",
                len(records), len(seen_ad_ids), len(records) - len(seen_ad_ids))
    return records
