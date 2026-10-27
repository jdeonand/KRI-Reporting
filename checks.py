"""Reconciliation and integrity checks that run BEFORE any KRI is published.

A KRI that is quietly wrong is worse than a late one. These checks catch broken joins,
orphaned records, impossible dates and missing reporting periods, and the build stops if any
fail. Several recompute a number a second, independent way and compare it with the KRI view.
"""
from . import db


def _count(conn, sql):
    return conn.execute(sql).fetchone()[0]


def _result(name, description, bad, detail=""):
    return {"name": name, "description": description, "passed": bad == 0, "failures": bad, "detail": detail}


def check_findings_have_assets(conn):
    bad = _count(conn, "SELECT COUNT(*) FROM findings f LEFT JOIN assets a ON a.asset_id = f.asset_id WHERE a.asset_id IS NULL")
    return _result("findings_have_assets", "Every finding belongs to a known asset", bad,
                   "orphaned findings are silently dropped by the KRI joins" if bad else "")


def check_finding_dates(conn):
    bad = _count(conn, "SELECT COUNT(*) FROM findings WHERE due_date < opened_date OR (closed_date IS NOT NULL AND closed_date < opened_date)")
    return _result("finding_dates_logical", "Due and closed dates are never before the opened date", bad)


def check_known_business_units(conn):
    bad = 0
    for table in ("incidents", "access_reviews", "phishing_campaigns"):
        bad += _count(conn, f"SELECT COUNT(*) FROM {table} t LEFT JOIN dim_business_unit b ON b.business_unit = t.business_unit WHERE b.business_unit IS NULL")
    return _result("known_business_units", "Incidents, reviews and phishing rows use known business units", bad)


def check_period_completeness(conn):
    expected = _count(conn, "SELECT COUNT(*) FROM dim_business_unit, dim_month")
    got = _count(conn, "SELECT COUNT(*) FROM phishing_campaigns p JOIN dim_month m ON m.month_end = p.month_end")
    return _result("phishing_complete", "Phishing data exists for every business unit and reporting month",
                   expected - got, f"expected {expected} rows, found {got}" if expected != got else "")


def check_kri01_reconciles(conn):
    """Recompute enterprise open/overdue Critical+High findings straight from `findings`
    (no join to assets) and compare with the KRI view."""
    sql = """
    WITH direct AS (
      SELECT m.month_end,
             SUM(CASE WHEN f.due_date < m.month_end THEN 1 ELSE 0 END) AS overdue, COUNT(*) AS open_n
      FROM dim_month m JOIN findings f ON f.severity IN ('Critical','High')
           AND f.opened_date <= m.month_end AND (f.closed_date IS NULL OR f.closed_date > m.month_end)
      GROUP BY m.month_end)
    SELECT COUNT(*) FROM direct d
    LEFT JOIN kri_inputs i ON i.kri_id = 'KRI-01' AND i.scope = 'enterprise' AND i.month_end = d.month_end
    WHERE i.numerator IS NOT d.overdue OR i.denominator IS NOT d.open_n"""
    return _result("kri01_reconciles", "KRI-01 enterprise numbers match an independent recount from raw findings", _count(conn, sql))


def check_kri03_reconciles(conn):
    sql = """
    SELECT (SELECT COUNT(*) FROM incidents i JOIN dim_month m ON i.occurred_date >= date(m.month_end,'start of month')
                 AND i.occurred_date <= m.month_end WHERE i.severity IN ('High','Critical'))
         - (SELECT COALESCE(SUM(numerator),0) FROM kri_inputs WHERE kri_id = 'KRI-03' AND scope = 'enterprise')"""
    return _result("kri03_reconciles", "KRI-03 enterprise total equals the raw High/Critical incident count", abs(_count(conn, sql)))


def check_thresholds_ordered(conn):
    sql = """SELECT COUNT(*) FROM kri_thresholds t JOIN kri_definitions d USING (kri_id)
             WHERE (d.direction = 'higher_is_worse' AND t.amber >= t.red)
                OR (d.direction = 'lower_is_worse' AND t.amber <= t.red)"""
    return _result("thresholds_ordered", "Amber is always a milder level than Red", _count(conn, sql))


CHECKS = [check_findings_have_assets, check_finding_dates, check_known_business_units,
          check_period_completeness, check_kri01_reconciles, check_kri03_reconciles, check_thresholds_ordered]


def run_all(conn):
    return [c(conn) for c in CHECKS]


def failures(results):
    return [r for r in results if not r["passed"]]
