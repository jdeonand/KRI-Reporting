-- KRI calculation layer. Every KRI is expressed as numerator / denominator so that business
-- units roll up to the enterprise by SUMMING numerators and denominators (a pooled ratio),
-- never by averaging the units' percentages, which would give a small unit the same weight
-- as a large one.
DROP VIEW IF EXISTS kri_inputs_bu;  DROP VIEW IF EXISTS kri_inputs;
DROP VIEW IF EXISTS kri_values;     DROP VIEW IF EXISTS kri_status;

CREATE VIEW kri_inputs_bu AS
-- KRI-01: open Critical/High findings at month end, and how many are past due
SELECT 'KRI-01' AS kri_id, m.month_end, a.business_unit,
       SUM(CASE WHEN f.due_date < m.month_end THEN 1 ELSE 0 END) AS numerator,
       COUNT(*) AS denominator
FROM dim_month m
JOIN findings f ON f.severity IN ('Critical','High')
               AND f.opened_date <= m.month_end
               AND (f.closed_date IS NULL OR f.closed_date > m.month_end)
JOIN assets a ON a.asset_id = f.asset_id
GROUP BY m.month_end, a.business_unit
UNION ALL
-- KRI-02: Critical findings closed in the month; total days open / number closed
SELECT 'KRI-02', m.month_end, a.business_unit,
       SUM(julianday(f.closed_date) - julianday(f.opened_date)), COUNT(*)
FROM dim_month m
JOIN findings f ON f.severity = 'Critical'
               AND f.closed_date >= date(m.month_end, 'start of month')
               AND f.closed_date <= m.month_end
JOIN assets a ON a.asset_id = f.asset_id
GROUP BY m.month_end, a.business_unit
UNION ALL
-- KRI-03: count of High/Critical incidents; LEFT JOIN so a quiet month is a real 0, not missing
SELECT 'KRI-03', m.month_end, b.business_unit, COUNT(i.incident_id), 1
FROM dim_month m
CROSS JOIN dim_business_unit b
LEFT JOIN incidents i ON i.business_unit = b.business_unit
                     AND i.severity IN ('High','Critical')
                     AND i.occurred_date >= date(m.month_end, 'start of month')
                     AND i.occurred_date <= m.month_end
GROUP BY m.month_end, b.business_unit
UNION ALL
-- KRI-04: detection hours across all incidents in the month (missing if there were none)
SELECT 'KRI-04', m.month_end, i.business_unit, SUM(i.detect_hours), COUNT(*)
FROM dim_month m
JOIN incidents i ON i.occurred_date >= date(m.month_end, 'start of month')
                AND i.occurred_date <= m.month_end
GROUP BY m.month_end, i.business_unit
UNION ALL
-- KRI-05: access reviews due in the month, and how many were completed by the due date
SELECT 'KRI-05', m.month_end, r.business_unit,
       SUM(CASE WHEN r.completed_date IS NOT NULL AND r.completed_date <= r.due_date THEN 1 ELSE 0 END),
       COUNT(*)
FROM dim_month m
JOIN access_reviews r ON r.due_date >= date(m.month_end, 'start of month')
                     AND r.due_date <= m.month_end
GROUP BY m.month_end, r.business_unit
UNION ALL
-- KRI-06: phishing clicks / emails sent
SELECT 'KRI-06', p.month_end, p.business_unit, SUM(p.clicks), SUM(p.emails_sent)
FROM phishing_campaigns p
JOIN dim_month m ON m.month_end = p.month_end
GROUP BY p.month_end, p.business_unit;

CREATE VIEW kri_inputs AS
SELECT kri_id, 'business_unit' AS scope, business_unit, month_end, numerator, denominator
FROM kri_inputs_bu
UNION ALL
SELECT i.kri_id, 'enterprise', 'Enterprise', i.month_end,
       SUM(i.numerator),
       CASE WHEN d.agg = 'sum' THEN 1 ELSE SUM(i.denominator) END
FROM kri_inputs_bu i
JOIN kri_definitions d ON d.kri_id = i.kri_id
GROUP BY i.kri_id, i.month_end;

CREATE VIEW kri_values AS
SELECT i.kri_id, d.name, d.unit, i.scope, i.business_unit, i.month_end,
       i.numerator, i.denominator,
       d.scale * i.numerator / i.denominator AS value
FROM kri_inputs i
JOIN kri_definitions d ON d.kri_id = i.kri_id
WHERE i.denominator > 0;

CREATE VIEW kri_status AS
SELECT v.*, t.amber, t.red, d.direction,
       CASE WHEN d.direction = 'higher_is_worse'
            THEN CASE WHEN v.value >= t.red THEN 'Red' WHEN v.value >= t.amber THEN 'Amber' ELSE 'Green' END
            ELSE CASE WHEN v.value <= t.red THEN 'Red' WHEN v.value <= t.amber THEN 'Amber' ELSE 'Green' END
       END AS status,
       p.value AS value_3m_ago
FROM kri_values v
JOIN kri_definitions d ON d.kri_id = v.kri_id
JOIN kri_thresholds  t ON t.kri_id = v.kri_id AND t.scope = v.scope
LEFT JOIN kri_values p ON p.kri_id = v.kri_id AND p.scope = v.scope
                      AND p.business_unit = v.business_unit
                      AND p.month_end = date(v.month_end, 'start of month', '-2 months', '-1 day');
