"""
GA4 Data API client — pulls daily traffic, sources, devices, landing pages.

Reuses the SAME service account as Google Drive (add the service account's
client_email as a Viewer on the GA4 property).

Requires:
  SERVICE_ACCOUNT_JSON   — same service account JSON blob
  GA4_PROPERTY_ID        — e.g. "properties/123456789"  (or just "123456789";
                           we'll normalize)

Exposes:
  fetch_ga_report(sa_info, property_id, since, until) -> dict | None
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kocskin_report.ga")


def _normalize_property_id(pid: str) -> str:
    pid = str(pid).strip()
    if pid.startswith("properties/"):
        return pid
    return f"properties/{pid}"


def _run_report(client, property_id: str, body: Dict[str, Any]):
    """Thin wrapper that returns the raw response."""
    from google.analytics.data_v1beta.types import RunReportRequest

    req = RunReportRequest(property=property_id, **body)
    return client.run_report(req)


def _row_value(row, idx: int) -> str:
    try:
        return row.dimension_values[idx].value
    except Exception:
        return ""


def _metric_value(row, idx: int) -> float:
    try:
        v = row.metric_values[idx].value
        return float(v) if v not in (None, "") else 0.0
    except Exception:
        return 0.0


def fetch_ga_report(
    sa_info: Dict[str, Any],
    property_id: str,
    since: str,
    until: str,
) -> Optional[Dict[str, Any]]:
    """
    Returns a dict payload that the HTML template will render.

    Gracefully returns None on failure (missing lib / creds error / permission
    denied) so the report can still publish without GA data.

    Shape of returned dict:
    {
        "daily": [{"date": "2026-04-10", "sessions": 123, "users": 98,
                   "new_users": 40, "pageviews": 410}, ...],
        "traffic_sources": [{"channel": "Organic Search", "sessions": 500,
                             "users": 400, "conversions": 10}, ...],
        "devices":         [{"device": "mobile", "sessions": 700,
                             "users": 600}, ...],
        "landing_pages":   [{"path": "/products/xxx", "sessions": 120,
                             "users": 100, "bounce_rate": 0.35}, ...],
        "totals": {"sessions": X, "users": X, "new_users": X,
                   "pageviews": X, "conversions": X, "purchase_revenue": X},
    }
    """
    try:
        from google.oauth2 import service_account
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, OrderBy, Filter, FilterExpression,
        )
    except ImportError as e:
        logger.error("GA: google-analytics-data not installed: %s", e)
        return None

    try:
        scopes = [
            "https://www.googleapis.com/auth/analytics.readonly",
        ]
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=scopes,
        )
        client = BetaAnalyticsDataClient(credentials=creds)
    except Exception as e:
        logger.error("GA: failed to build client: %s", e)
        return None

    pid = _normalize_property_id(property_id)
    date_range = DateRange(start_date=since, end_date=until)

    out: Dict[str, Any] = {
        "daily": [],
        "traffic_sources": [],
        "devices": [],
        "landing_pages": [],
        "totals": {
            "sessions": 0,
            "users": 0,
            "new_users": 0,
            "pageviews": 0,
            "conversions": 0,
            "purchase_revenue": 0.0,
        },
    }

    # -------- Daily series --------
    try:
        resp = client.run_report(
            request={
                "property": pid,
                "date_ranges": [date_range],
                "dimensions": [Dimension(name="date")],
                "metrics": [
                    Metric(name="sessions"),
                    Metric(name="totalUsers"),
                    Metric(name="newUsers"),
                    Metric(name="screenPageViews"),
                ],
                "order_bys": [OrderBy(
                    dimension=OrderBy.DimensionOrderBy(dimension_name="date"),
                )],
                "limit": 500,
            }
        )
        for row in resp.rows:
            d = _row_value(row, 0)  # YYYYMMDD
            iso = f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
            out["daily"].append({
                "date": iso,
                "sessions": int(_metric_value(row, 0)),
                "users": int(_metric_value(row, 1)),
                "new_users": int(_metric_value(row, 2)),
                "pageviews": int(_metric_value(row, 3)),
            })
    except Exception as e:
        logger.error("GA: daily series failed: %s", e)

    # -------- Traffic sources (default channel group) --------
    try:
        resp = client.run_report(
            request={
                "property": pid,
                "date_ranges": [date_range],
                "dimensions": [Dimension(name="sessionDefaultChannelGroup")],
                "metrics": [
                    Metric(name="sessions"),
                    Metric(name="totalUsers"),
                    Metric(name="conversions"),
                ],
                "order_bys": [OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                    desc=True,
                )],
                "limit": 20,
            }
        )
        for row in resp.rows:
            out["traffic_sources"].append({
                "channel": _row_value(row, 0) or "(not set)",
                "sessions": int(_metric_value(row, 0)),
                "users": int(_metric_value(row, 1)),
                "conversions": int(_metric_value(row, 2)),
            })
    except Exception as e:
        logger.error("GA: traffic sources failed: %s", e)

    # -------- Device category --------
    try:
        resp = client.run_report(
            request={
                "property": pid,
                "date_ranges": [date_range],
                "dimensions": [Dimension(name="deviceCategory")],
                "metrics": [
                    Metric(name="sessions"),
                    Metric(name="totalUsers"),
                ],
                "order_bys": [OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                    desc=True,
                )],
                "limit": 10,
            }
        )
        for row in resp.rows:
            out["devices"].append({
                "device": _row_value(row, 0) or "(not set)",
                "sessions": int(_metric_value(row, 0)),
                "users": int(_metric_value(row, 1)),
            })
    except Exception as e:
        logger.error("GA: devices failed: %s", e)

    # -------- Top landing pages --------
    try:
        resp = client.run_report(
            request={
                "property": pid,
                "date_ranges": [date_range],
                "dimensions": [Dimension(name="landingPagePlusQueryString")],
                "metrics": [
                    Metric(name="sessions"),
                    Metric(name="totalUsers"),
                    Metric(name="bounceRate"),
                ],
                "order_bys": [OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                    desc=True,
                )],
                "limit": 15,
            }
        )
        for row in resp.rows:
            out["landing_pages"].append({
                "path": _row_value(row, 0) or "(not set)",
                "sessions": int(_metric_value(row, 0)),
                "users": int(_metric_value(row, 1)),
                "bounce_rate": round(_metric_value(row, 2), 4),
            })
    except Exception as e:
        logger.error("GA: landing pages failed: %s", e)

    # -------- Totals (sessions/users/conversions/revenue) --------
    try:
        resp = client.run_report(
            request={
                "property": pid,
                "date_ranges": [date_range],
                "metrics": [
                    Metric(name="sessions"),
                    Metric(name="totalUsers"),
                    Metric(name="newUsers"),
                    Metric(name="screenPageViews"),
                    Metric(name="conversions"),
                    Metric(name="purchaseRevenue"),
                ],
            }
        )
        if resp.rows:
            row = resp.rows[0]
            out["totals"] = {
                "sessions": int(_metric_value(row, 0)),
                "users": int(_metric_value(row, 1)),
                "new_users": int(_metric_value(row, 2)),
                "pageviews": int(_metric_value(row, 3)),
                "conversions": int(_metric_value(row, 4)),
                "purchase_revenue": float(_metric_value(row, 5)),
            }
    except Exception as e:
        logger.error("GA: totals failed: %s", e)

    logger.info(
        "GA: %d daily rows, %d sources, %d devices, %d landing pages | "
        "totals sessions=%d users=%d conversions=%d",
        len(out["daily"]), len(out["traffic_sources"]),
        len(out["devices"]), len(out["landing_pages"]),
        out["totals"]["sessions"], out["totals"]["users"],
        out["totals"]["conversions"],
    )
    return out
