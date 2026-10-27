import unittest

from kri import checks, db, generate, report


def fresh(**kw):
    conn = db.connect()
    generate.generate(conn, **kw)
    return conn


class TestChecks(unittest.TestCase):
    def test_clean_data_passes_every_check(self):
        results = checks.run_all(fresh())
        self.assertEqual(checks.failures(results), [])
        self.assertEqual(len(results), 7)

    def test_injected_defects_are_each_caught_by_the_right_check(self):
        failed = {r["name"] for r in checks.failures(checks.run_all(fresh(inject_defects=True)))}
        self.assertTrue({"findings_have_assets", "finding_dates_logical", "phishing_complete", "kri01_reconciles"} <= failed)

    def test_orphaned_findings_make_the_independent_recount_disagree_with_the_kri(self):
        conn = fresh()
        conn.execute("INSERT INTO findings VALUES (999999,'NOPE','Critical','2026-08-01','2026-08-16',NULL)")
        conn.commit()
        self.assertFalse(checks.check_kri01_reconciles(conn)["passed"])

    def test_misordered_thresholds_are_flagged(self):
        conn = fresh()
        conn.execute("UPDATE kri_thresholds SET amber = 30 WHERE kri_id = 'KRI-01' AND scope = 'enterprise'")
        conn.commit()
        self.assertFalse(checks.check_thresholds_ordered(conn)["passed"])


class TestGenerate(unittest.TestCase):
    def test_same_seed_gives_identical_data_and_kris(self):
        a, b = fresh(seed=3), fresh(seed=3)
        q = "SELECT kri_id, business_unit, month_end, value FROM kri_status ORDER BY 1, 2, 3"
        self.assertEqual(db.rows(a, q), db.rows(b, q))

    def test_different_seeds_differ(self):
        q = "SELECT COUNT(*) FROM findings"
        self.assertNotEqual(fresh(seed=1).execute(q).fetchone()[0], fresh(seed=2).execute(q).fetchone()[0])

    def test_reporting_window_is_24_months_ending_september_2026(self):
        conn = fresh()
        months = [r[0] for r in conn.execute("SELECT month_end FROM dim_month ORDER BY 1")]
        self.assertEqual((len(months), months[0], months[-1]), (24, "2024-10-31", "2026-09-30"))

    def test_no_event_is_dated_after_the_reporting_date(self):
        conn = fresh()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM findings WHERE closed_date > '2026-09-30'").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM incidents WHERE occurred_date > '2026-09-30'").fetchone()[0], 0)

    def test_built_in_stories_show_up_in_the_kris(self):
        conn = fresh()

        def v(kri, bu, month):
            r = conn.execute("SELECT value FROM kri_status WHERE kri_id=? AND business_unit=? AND month_end=?", (kri, bu, month)).fetchone()
            return r[0] if r else None

        def avg(kri, bu, lo, hi):
            return conn.execute("SELECT AVG(value) FROM kri_status WHERE kri_id=? AND business_unit=? AND month_end BETWEEN ? AND ?",
                                (kri, bu, lo, hi)).fetchone()[0]

        self.assertGreater(avg("KRI-01", "Payments", "2026-07-31", "2026-09-30"), avg("KRI-01", "Payments", "2025-01-31", "2025-12-31"))
        self.assertLess(avg("KRI-05", "Wealth", "2026-06-30", "2026-09-30"), avg("KRI-05", "Wealth", "2025-01-31", "2025-12-31") - 15)
        self.assertLess(avg("KRI-04", "Insurance", "2026-03-31", "2026-09-30"), avg("KRI-04", "Insurance", "2024-10-31", "2025-09-30"))
        self.assertLess(avg("KRI-06", "Retail", "2026-03-31", "2026-09-30"), avg("KRI-06", "Retail", "2024-10-31", "2025-06-30"))


class TestExampleSql(unittest.TestCase):
    def test_every_query_in_analysis_sql_runs_and_returns_rows(self):
        conn = fresh()
        text = (db.SQL_DIR / "analysis.sql").read_text(encoding="utf-8")
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
        statements = [s for s in text.split(";") if s.strip()]
        self.assertEqual(len(statements), 4)
        for stmt in statements:
            self.assertTrue(conn.execute(stmt).fetchall(), stmt[:60])


class TestReport(unittest.TestCase):
    def test_movers_only_include_worsened_kris_worst_first(self):
        conn = fresh()
        movers = report.movers(conn, report.latest_month(conn))
        self.assertTrue(movers)
        self.assertTrue(all(m["worsened_by"] > 0 for m in movers))
        self.assertEqual([m["worsened_by"] for m in movers], sorted((m["worsened_by"] for m in movers), reverse=True))

    def test_status_counts_sum_to_number_of_kris(self):
        conn = fresh()
        snap = report.enterprise_snapshot(conn, report.latest_month(conn))
        self.assertEqual(sum(report.status_counts(snap).values()), 6)


if __name__ == "__main__":
    unittest.main()
