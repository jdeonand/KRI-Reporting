"""Generate a SYNTHETIC technology-risk dataset with a built-in story.

Nothing here comes from a real organisation. Seven fictional business units, ~100 assets
each, and 24 months of events (vulnerability findings, incidents, access reviews, phishing
simulations). Each unit's behaviour drifts over time so the dashboard has something to say:

  Payments        remediation slows sharply in the last 5 months (overdue vulnerabilities climb)
  Markets         starts slow at remediating and improves over time (noisy month to month)
  Insurance       incident detection gets much faster after month 12
  Wealth          access-review completion collapses in the last 4 months
  Retail          phishing click rate falls after a training programme (month 10)
  Commercial      incident volume rises in the last 3 months
  Shared Services broadly stable

Seeded and deterministic. `inject_defects=True` adds known data problems so the
reconciliation checks have something to catch.
"""
import calendar
import math
import random
from datetime import date, timedelta

from . import db

BUSINESS_UNITS = ["Retail", "Commercial", "Wealth", "Markets", "Insurance", "Payments", "Shared Services"]
SEVERITIES = ["Critical", "High", "Medium", "Low"]
SEV_WEIGHTS = [0.08, 0.22, 0.45, 0.25]
SLA_DAYS = {"Critical": 15, "High": 30, "Medium": 60, "Low": 90}
N_MONTHS = 24
WARMUP = 6  # months of history before the first reported month, so a backlog already exists


def month_end(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def month_list(end_year=2026, end_month=9, n=N_MONTHS):
    """Return the n month-end dates ending at (end_year, end_month), oldest first."""
    y, m = end_year, end_month
    out = []
    for _ in range(n):
        out.append(month_end(y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def poisson(rng, lam):
    """Knuth's algorithm (standard library only)."""
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _remediation_factor(bu, idx):
    """Multiple of the SLA that remediation typically takes (>1 means chronically late)."""
    base = {"Retail": 0.6, "Commercial": 0.66, "Wealth": 0.72, "Insurance": 0.62, "Shared Services": 0.74}
    if bu == "Payments":
        return 0.7 + (1.0 * (idx - 17) / 6 if idx >= 17 else 0)
    if bu == "Markets":
        return 1.1 - 0.5 * min(1.0, max(idx, 0) / 23)
    return base.get(bu, 0.7)


def _detect_median_hours(bu, idx):
    if bu == "Insurance":
        return 28 if idx < 12 else 9
    return 14


def _review_ontime_prob(bu, idx):
    return 0.62 if (bu == "Wealth" and idx >= 20) else 0.93


def _phish_click_prob(bu, idx):
    if bu == "Retail":
        return 0.12 if idx < 10 else 0.04
    return 0.062


def generate(conn, seed=7, assets_per_bu=100, inject_defects=False, end_year=2026, end_month=9):
    rng = random.Random(seed)
    months = month_list(end_year, end_month)
    as_of = months[-1]
    first_report = months[0]
    start = (first_report.replace(day=1) - timedelta(days=1))
    for _ in range(WARMUP - 1):
        start = start.replace(day=1) - timedelta(days=1)
    start = start.replace(day=1)  # first day of the warm-up window

    db.create_schema(conn)
    conn.executemany("INSERT INTO dim_business_unit VALUES (?)", [(b,) for b in BUSINESS_UNITS])
    conn.executemany("INSERT INTO dim_month VALUES (?)", [(m.isoformat(),) for m in months])

    assets, findings, incidents, reviews, phishing = [], [], [], [], []
    all_months = month_list(end_year, end_month, N_MONTHS + WARMUP)  # warm-up + reporting months

    for bu in BUSINESS_UNITS:
        n_assets = assets_per_bu + rng.randint(-15, 25)
        for k in range(n_assets):
            assets.append((f"{bu[:3].upper()}-{k:04d}", bu, rng.choices(["Low", "Medium", "High"], [0.4, 0.4, 0.2])[0]))

    by_bu = {}
    for a in assets:
        by_bu.setdefault(a[1], []).append(a[0])

    fid = iid = rid = 0
    for bu in BUSINESS_UNITS:
        for mi, me in enumerate(all_months):
            idx = mi - WARMUP  # negative during warm-up
            first = me.replace(day=1)
            days_in_month = me.day
            factor = _remediation_factor(bu, idx)
            # --- vulnerability findings
            for asset_id in by_bu[bu]:
                for _ in range(poisson(rng, 0.9)):
                    fid += 1
                    sev = rng.choices(SEVERITIES, SEV_WEIGHTS)[0]
                    opened = first + timedelta(days=rng.randrange(days_in_month))
                    due = opened + timedelta(days=SLA_DAYS[sev])
                    take = max(1, round(SLA_DAYS[sev] * factor * math.exp(rng.gauss(0, 0.45))))
                    closed = opened + timedelta(days=take)
                    findings.append((fid, asset_id, sev, opened.isoformat(), due.isoformat(),
                                     closed.isoformat() if closed <= as_of else None))
            # --- incidents
            for _ in range(poisson(rng, 17 if (bu == 'Commercial' and idx >= 21) else 5.0)):
                iid += 1
                sev = rng.choices(SEVERITIES, [0.04, 0.16, 0.45, 0.35])[0]
                occurred = first + timedelta(days=rng.randrange(days_in_month))
                hours = round(_detect_median_hours(bu, idx) * math.exp(rng.gauss(0, 0.5)), 1)
                incidents.append((iid, bu, occurred.isoformat(), sev, hours))
            if idx < 0:
                continue  # access reviews and phishing are only reported for reporting months
            # --- access reviews due this month
            for _ in range(rng.randint(22, 38)):
                rid += 1
                due = first + timedelta(days=rng.randrange(days_in_month))
                if rng.random() < _review_ontime_prob(bu, idx):
                    done = due - timedelta(days=rng.randint(0, 10))
                elif rng.random() < 0.8:
                    done = due + timedelta(days=rng.randint(1, 25))
                else:
                    done = None
                reviews.append((rid, bu, due.isoformat(), done.isoformat() if done and done <= as_of else None))
            # --- phishing simulation
            sent = rng.randint(450, 900)
            clicks = sum(rng.random() < _phish_click_prob(bu, idx) for _ in range(sent))
            phishing.append((bu, me.isoformat(), sent, clicks))

    if inject_defects:
        findings += [(fid + 1, "ZZZ-9999", "High", "2026-01-05", "2026-02-04", None),     # orphan asset
                     (fid + 2, "ZZZ-9998", "Critical", "2026-02-05", "2026-02-20", None)]
        findings.append((fid + 3, assets[0][0], "High", "2026-03-10", "2026-04-09", "2026-03-01"))  # closed before opened
        findings.append((fid + 4, assets[1][0], "Low", "2026-03-10", "2026-03-01", None))           # due before opened
        phishing.pop(3)                                                                             # missing BU-month

    conn.executemany("INSERT INTO assets VALUES (?,?,?)", assets)
    conn.executemany("INSERT INTO findings VALUES (?,?,?,?,?,?)", findings)
    conn.executemany("INSERT INTO incidents VALUES (?,?,?,?,?)", incidents)
    conn.executemany("INSERT INTO access_reviews VALUES (?,?,?,?)", reviews)
    conn.executemany("INSERT INTO phishing_campaigns VALUES (?,?,?,?)", phishing)
    conn.commit()
    db.install_views(conn)
    return {"assets": len(assets), "findings": len(findings), "incidents": len(incidents),
            "access_reviews": len(reviews), "phishing_rows": len(phishing), "months": len(months)}
