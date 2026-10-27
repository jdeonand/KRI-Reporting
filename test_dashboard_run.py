import contextlib
import io
import os
import tempfile
import unittest

import run
from kri import checks, dashboard, db, generate


def build_html(mutate=None):
    conn = db.connect()
    generate.generate(conn)
    if mutate:
        mutate(conn)
    return dashboard.build_html(conn, checks.run_all(conn))


class TestDashboard(unittest.TestCase):
    def test_page_contains_every_kri_the_banner_and_the_checks(self):
        html = build_html()
        for k in range(1, 7):
            self.assertIn(f"KRI-0{k}", html)
        self.assertIn("Synthetic data", html)
        self.assertIn("7 of 7 reconciliation checks passed", html)
        self.assertIn("September 2026", html)

    def test_page_has_no_javascript_and_no_external_assets(self):
        html = build_html().lower()
        self.assertNotIn("<script", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_business_unit_names_are_html_escaped(self):
        def rename(conn):
            for t in ("dim_business_unit", "assets", "incidents", "access_reviews", "phishing_campaigns"):
                conn.execute(f"UPDATE {t} SET business_unit = '<script>alert(1)</script>' WHERE business_unit = 'Retail'")
            conn.commit()
        html = build_html(rename)
        self.assertNotIn("<script", html.lower())
        self.assertIn("&lt;script&gt;", html)

    def test_status_is_always_written_in_words_not_only_colour(self):
        html = build_html()
        for word in ("Red", "Amber", "Green"):
            self.assertIn(word, html)

    def test_sparkline_survives_a_flat_series(self):
        svg = dashboard.sparkline([("2026-01-31", 5.0)] * 12, amber=10, red=20)
        self.assertIn("<polyline", svg)

    def test_change_text_says_better_or_worse_by_direction(self):
        worse_up = dashboard.change_text({"value": 12, "value_3m_ago": 8, "unit": "%", "direction": "higher_is_worse"})
        better_up = dashboard.change_text({"value": 92, "value_3m_ago": 88, "unit": "%", "direction": "lower_is_worse"})
        self.assertIn("worse", worse_up)
        self.assertIn("better", better_up)


class TestRunScript(unittest.TestCase):
    def test_clean_run_writes_dashboard_and_csv(self):
        with tempfile.TemporaryDirectory() as d:
            args = ["--db", f"{d}/k.db", "--html", f"{d}/i.html", "--csv", f"{d}/s.csv"]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run.main(args), 0)
            self.assertTrue(os.path.getsize(f"{d}/i.html") > 5000)
            with open(f"{d}/s.csv", encoding="utf-8") as f:
                self.assertTrue(f.read().startswith("kri_id,"))

    def test_failed_checks_stop_the_build_and_write_no_dashboard(self):
        with tempfile.TemporaryDirectory() as d:
            args = ["--db", f"{d}/k.db", "--html", f"{d}/i.html", "--csv", f"{d}/s.csv", "--inject-defects"]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run.main(args), 1)
            self.assertFalse(os.path.exists(f"{d}/i.html"))


if __name__ == "__main__":
    unittest.main()
