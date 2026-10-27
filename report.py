"""Pull dashboard-ready data out of the KRI views."""
from . import db
from .status import RANK, status_for


def latest_month(conn):
    return conn.execute("SELECT MAX(month_end) FROM dim_month").fetchone()[0]


def definitions(conn):
    return db.rows(conn, """SELECT d.kri_id, d.name, d.unit, d.direction, d.description,
                                   e.amber AS ent_amber, e.red AS ent_red, b.amber AS bu_amber, b.red AS bu_red
                            FROM kri_definitions d
                            JOIN kri_thresholds e ON e.kri_id = d.kri_id AND e.scope = 'enterprise'
                            JOIN kri_thresholds b ON b.kri_id = d.kri_id AND b.scope = 'business_unit'
                            ORDER BY d.kri_id""")


def enterprise_snapshot(conn, month):
    return db.rows(conn, """SELECT kri_id, name, unit, value, status, value_3m_ago, amber, red, direction
                            FROM kri_status WHERE scope = 'enterprise' AND month_end = ? ORDER BY kri_id""", (month,))


def enterprise_series(conn, months=12):
    out = {}
    for r in db.rows(conn, """SELECT kri_id, month_end, value FROM kri_status WHERE scope = 'enterprise'
                              ORDER BY kri_id, month_end"""):
        out.setdefault(r["kri_id"], []).append((r["month_end"], r["value"]))
    return {k: v[-months:] for k, v in out.items()}


def heatmap(conn, month):
    grid = {}
    for r in db.rows(conn, """SELECT business_unit, kri_id, value, status FROM kri_status
                              WHERE scope = 'business_unit' AND month_end = ?""", (month,)):
        grid.setdefault(r["business_unit"], {})[r["kri_id"]] = r
    return grid


def movers(conn, month, limit=6):
    """Business-unit KRIs whose status got worse versus three months earlier, worst first."""
    rows = db.rows(conn, """SELECT business_unit, kri_id, name, unit, value, value_3m_ago, status, amber, red, direction
                            FROM kri_status WHERE scope = 'business_unit' AND month_end = ?
                              AND value_3m_ago IS NOT NULL""", (month,))
    out = []
    for r in rows:
        before = status_for(r["value_3m_ago"], r["amber"], r["red"], r["direction"])
        r["status_before"] = before
        r["worsened_by"] = RANK[r["status"]] - RANK[before]
        sign = 1 if r["direction"] == "higher_is_worse" else -1
        r["bad_move"] = sign * (r["value"] - r["value_3m_ago"])
        if r["worsened_by"] > 0:
            out.append(r)
    out.sort(key=lambda r: (-r["worsened_by"], -RANK[r["status"]], -r["bad_move"]))
    return out[:limit]


def status_counts(snapshot):
    counts = {"Red": 0, "Amber": 0, "Green": 0}
    for r in snapshot:
        counts[r["status"]] += 1
    return counts
