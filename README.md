# Technology Risk KRI Reporting

A small, tested project that turns raw risk events into **Key Risk Indicators (KRIs)** with
**red / amber / green status**, checks the numbers before publishing them, and renders a
self-contained dashboard page.

The KRIs are calculated **in SQL**. Python generates the data, verifies it, and builds the page.

![Dashboard preview](docs/dashboard_preview.png)

> **About the data:** everything here is **synthetic**. Seven fictional business units, about
> 100 assets each, and 24 months of generated vulnerability findings, incidents, access reviews
> and phishing simulations. Some unit behaviour is deliberately scripted (for example Payments
> remediation slows late, and Wealth access-review completion collapses) so the dashboard has
> something to say. No real organisation's data is used.

## The KRIs

| ID | KRI | Direction | Business-unit thresholds (amber / red) |
|---|---|---|---|
| KRI-01 | Overdue critical/high vulnerabilities (%) | higher is worse | 10 / 20 |
| KRI-02 | Mean time to remediate critical vulnerabilities (days) | higher is worse | 15 / 25 |
| KRI-03 | High/critical security incidents (count) | higher is worse | 2 / 4 |
| KRI-04 | Mean time to detect incidents (hours) | higher is worse | 24 / 48 |
| KRI-05 | Access reviews completed on time (%) | lower is worse | 90 / 80 |
| KRI-06 | Phishing simulation click rate (%) | higher is worse | 8 / 12 |

Enterprise thresholds are the same, except KRI-03 (8 / 14) because it is a count that adds up across units.

## How it works

```
generate synthetic data ──> reconciliation checks ──┬─ any fail ──> STOP (no dashboard)
   (SQLite tables)            (7 checks)            │
                                                    └─ all pass ──> KRI views in SQL ──> dashboard.html + CSV
```

## Design decisions worth knowing

- **Pooled ratios, not averaged percentages.** Every KRI is a numerator over a denominator. Business units roll up to the enterprise by summing numerators and denominators. Averaging unit percentages would give a 3-finding unit the same weight as a 30-finding one. A test proves the two methods give different answers on a hand-built case.
- **A true zero is not a missing value.** A quiet month with no high/critical incidents is a real `0` (LEFT JOIN from every unit and month). A month with no incidents has *no* detection time to average, so KRI-04 is correctly `n/a`, not `0` hours, which would look like a perfect score.
- **Check before you publish.** Seven reconciliation checks run first, including two that recompute a KRI a second, independent way and compare. If any fail, the build stops and writes no dashboard. `python run.py --inject-defects` demonstrates this: it adds orphaned findings, impossible dates, and a missing reporting row, and the build refuses to proceed.
- **Boundary rule.** A value exactly on a threshold takes the worse status. SQL and Python implement the same logic, and a test confirms they agree on every one of the 1,150 KRI rows.
- **Accessible status.** Status is always written in words (Red / Amber / Green), never colour alone. The page has no JavaScript and no external assets.
- **Trend from the right month.** "3 months ago" is found by date, not by row position, so a missing month cannot silently shift the comparison.

## Example output (synthetic, September 2026)

Enterprise: overdue critical/high vulnerabilities **12.5% (Amber)**, up 4.2 points over three months; high/critical incidents **10 (Amber)**; access reviews on time **89.1% (Amber)**; the other three KRIs Green.
At unit level, **Payments** is Red on overdue vulnerabilities (26.5%, moved from Amber) and **Wealth** is Red on access-review completion (63.6%).

`sql/analysis.sql` has analyst-style queries on top of the views, including a `RANK()` window
function for units by number of red KRIs and a rolling three-month average.

## Run it

Requires Python 3.9+ (standard library only, no packages to install).

```bash
python run.py                                  # builds docs/index.html and docs/kri_status.csv
python run.py --inject-defects                 # shows the checks stopping a bad build
python -m unittest discover -s tests -t .      # 32 tests
```

### View the dashboard online (free)

In your repository: **Settings > Pages > Build and deployment > Deploy from a branch >
`main` / `docs` folder > Save.** After a minute the dashboard is live at
`https://<your-username>.github.io/<repository-name>/`.

## Project structure

```
sql/    schema.sql (tables, KRI definitions, thresholds)   kri_views.sql (the KRI calculations)   analysis.sql
src/kri/   generate.py  checks.py  report.py  dashboard.py  status.py  db.py
tests/     KRI maths on a hand-built dataset, checks, generator, dashboard, and the run script
docs/      index.html (dashboard), kri_status.csv, dashboard_preview.png
```

## Limitations

- Synthetic data with simple statistical behaviour; real data is messier (late-arriving records, reclassified severities, restated history).
- Business units, thresholds and SLAs are illustrative, not drawn from any real risk framework.
- SQLite stands in for a warehouse; the SQL is ANSI-style but the date functions (`date(..., 'start of month')`, `julianday`) would need translating for Snowflake or Postgres.
- The dashboard is a static snapshot of one month, not an interactive tool.

## Possible next steps

- Load into Snowflake and translate the date functions
- Schedule the build and publish the page automatically
- Add drill-through from a Red cell to the underlying findings
- Alert when a KRI crosses a threshold

## License

MIT
