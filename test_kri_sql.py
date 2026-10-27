"""KRI maths verified against a tiny hand-built dataset where every answer is worked out by hand."""
import unittest

from kri import db
from kri.status import status_for

MONTH = "2026-03-31"


def build():
    conn = db.connect()
    db.create_schema(conn)
    conn.executemany("INSERT INTO dim_business_unit VALUES (?)", [("A",), ("B",)])
    conn.executemany("INSERT INTO dim_month VALUES (?)", [("2025-12-31",), (MONTH,)])
    conn.executemany("INSERT INTO assets VALUES (?,?,?)", [("a1", "A", "High"), ("b1", "B", "High")])
    f = [  # id, asset, severity, opened, due, closed
        (1, "a1", "Critical", "2026-01-01", "2026-01-16", None),          # open, overdue
        (2, "a1", "High",     "2026-03-10", "2026-04-09", None),          # open, not yet due
        (3, "a1", "Critical", "2026-01-01", "2026-01-16", "2026-02-01"),  # closed before month end: not open
        (4, "a1", "Low",      "2026-01-01", "2026-01-31", None),          # wrong severity: ignored
        (5, "a1", "High",     "2026-03-01", "2026-03-31", "2026-04-05"),  # closed AFTER month end => still open; due == month end => not overdue
        (6, "b1", "High",     "2026-01-01", "2026-01-31", None),          # open, overdue (unit B)
        (7, "a1", "Critical", "2026-03-01", "2026-03-16", "2026-03-11"),  # closed in March after 10 days
        (8, "a1", "Critical", "2026-03-01", "2026-03-16", "2026-03-21"),  # closed in March after 20 days
    ]
    conn.executemany("INSERT INTO findings VALUES (?,?,?,?,?,?)", f)
    conn.executemany("INSERT INTO incidents VALUES (?,?,?,?,?)", [
        (1, "A", "2026-03-05", "High", 10.0), (2, "A", "2026-03-20", "Critical", 20.0),
        (3, "A", "2026-03-21", "Low", 30.0), (4, "A", "2026-02-10", "High", 99.0)])  # last is in February
    conn.executemany("INSERT INTO access_reviews VALUES (?,?,?,?)", [
        (1, "A", "2026-03-10", "2026-03-09"),   # on time
        (2, "A", "2026-03-15", "2026-03-20"),   # late
        (3, "A", "2026-03-20", None),           # never done
        (4, "B", "2026-03-12", "2026-03-12")])  # on time (same day counts)
    conn.executemany("INSERT INTO phishing_campaigns VALUES (?,?,?,?)", [
        ("A", MONTH, 100, 10), ("B", MONTH, 300, 3), ("A", "2025-12-31", 100, 20), ("B", "2025-12-31", 100, 10)])
    conn.commit()
    db.install_views(conn)
    return conn


def val(conn, kri, scope, bu, month=MONTH):
    r = conn.execute("SELECT * FROM kri_status WHERE kri_id=? AND scope=? AND business_unit=? AND month_end=?",
                     (kri, scope, bu, month)).fetchone()
    return dict(r) if r else None


class TestKriCalculations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = build()

    def test_kri01_counts_only_open_critical_high_and_flags_overdue(self):
        a = val(self.c, "KRI-01", "business_unit", "A")
        self.assertEqual((a["numerator"], a["denominator"]), (1, 3))   # findings 1, 2, 5 are open; only 1 is overdue
        b = val(self.c, "KRI-01", "business_unit", "B")
        self.assertEqual((b["numerator"], b["denominator"]), (1, 1))

    def test_enterprise_ratio_is_pooled_not_an_average_of_percentages(self):
        ent = val(self.c, "KRI-01", "enterprise", "Enterprise")
        self.assertAlmostEqual(ent["value"], 50.0)          # (1+1)/(3+1)
        average_of_units = (100 * 1 / 3 + 100 * 1 / 1) / 2   # 66.7: the wrong answer
        self.assertNotAlmostEqual(ent["value"], average_of_units)

    def test_kri02_mean_time_to_remediate(self):
        a = val(self.c, "KRI-02", "business_unit", "A")
        self.assertAlmostEqual(a["value"], 15.0)             # (10 + 20) / 2
        self.assertIsNone(val(self.c, "KRI-02", "business_unit", "B"))  # nothing closed: missing, not zero

    def test_kri03_counts_only_high_critical_in_the_month_and_keeps_true_zeros(self):
        self.assertEqual(val(self.c, "KRI-03", "business_unit", "A")["value"], 2)
        self.assertEqual(val(self.c, "KRI-03", "business_unit", "B")["value"], 0)   # a real zero
        self.assertEqual(val(self.c, "KRI-03", "enterprise", "Enterprise")["value"], 2)  # summed, not divided

    def test_kri04_mean_time_to_detect_uses_all_severities_in_the_month(self):
        self.assertAlmostEqual(val(self.c, "KRI-04", "business_unit", "A")["value"], 20.0)  # (10+20+30)/3, February excluded
        self.assertIsNone(val(self.c, "KRI-04", "business_unit", "B"))

    def test_kri05_on_time_completion(self):
        self.assertAlmostEqual(val(self.c, "KRI-05", "business_unit", "A")["value"], 100 / 3)
        self.assertAlmostEqual(val(self.c, "KRI-05", "business_unit", "B")["value"], 100.0)
        self.assertAlmostEqual(val(self.c, "KRI-05", "enterprise", "Enterprise")["value"], 50.0)

    def test_kri06_click_rate_is_pooled(self):
        self.assertAlmostEqual(val(self.c, "KRI-06", "enterprise", "Enterprise")["value"], 100 * 13 / 400)

    def test_value_three_months_ago_is_looked_up_by_date(self):
        a = val(self.c, "KRI-06", "business_unit", "A")
        self.assertAlmostEqual(a["value_3m_ago"], 20.0)       # December 2025
        self.assertIsNone(val(self.c, "KRI-06", "business_unit", "A", month="2025-12-31")["value_3m_ago"])


class TestStatusLogic(unittest.TestCase):
    def test_higher_is_worse_boundaries(self):
        for v, expected in [(9.99, "Green"), (10, "Amber"), (19.99, "Amber"), (20, "Red"), (35, "Red")]:
            self.assertEqual(status_for(v, 10, 20, "higher_is_worse"), expected, v)

    def test_lower_is_worse_boundaries(self):
        for v, expected in [(95, "Green"), (90.01, "Green"), (90, "Amber"), (80.01, "Amber"), (80, "Red"), (40, "Red")]:
            self.assertEqual(status_for(v, 90, 80, "lower_is_worse"), expected, v)

    def test_none_stays_none(self):
        self.assertIsNone(status_for(None, 10, 20, "higher_is_worse"))

    def test_sql_and_python_status_logic_agree_on_every_row(self):
        from kri import generate
        conn = db.connect()
        generate.generate(conn)
        mismatches = 0
        for r in db.rows(conn, "SELECT value, amber, red, direction, status FROM kri_status"):
            if status_for(r["value"], r["amber"], r["red"], r["direction"]) != r["status"]:
                mismatches += 1
        self.assertEqual(mismatches, 0)


if __name__ == "__main__":
    unittest.main()
