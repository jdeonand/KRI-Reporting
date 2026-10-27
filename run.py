"""Build everything: python run.py   (writes out/kri.db, docs/index.html, docs/kri_status.csv)"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

from kri import checks, dashboard, db, generate  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate data, verify it, calculate KRIs, build the dashboard")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--inject-defects", action="store_true", help="add known data problems to demo the checks")
    ap.add_argument("--db", default=os.path.join(HERE, "out", "kri.db"))
    ap.add_argument("--html", default=os.path.join(HERE, "docs", "index.html"))
    ap.add_argument("--csv", default=os.path.join(HERE, "docs", "kri_status.csv"))
    a = ap.parse_args(argv)

    for path in (a.db, a.html, a.csv):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(a.db):
        os.remove(a.db)

    conn = db.connect(a.db)
    counts = generate.generate(conn, seed=a.seed, inject_defects=a.inject_defects)
    print("Generated:", counts)

    results = checks.run_all(conn)
    for r in results:
        print(("PASS " if r["passed"] else "FAIL ") + r["name"] + (f"  ({r['failures']} issue(s) {r['detail']})" if not r["passed"] else ""))
    if checks.failures(results):
        print("\nReconciliation failed: dashboard NOT built.")
        return 1

    with open(a.html, "w", encoding="utf-8") as f:
        f.write(dashboard.build_html(conn, results))
    rows = db.rows(conn, "SELECT kri_id, name, scope, business_unit, month_end, numerator, denominator, value, amber, red, status FROM kri_status ORDER BY kri_id, scope, business_unit, month_end")
    with open(a.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {a.html}\nWrote {a.csv} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
