-- Example analyst queries on top of the KRI views.

-- 1. Latest enterprise snapshot: value, status, and change vs three months ago
SELECT kri_id, name, ROUND(value, 1) AS value, unit, status,
       ROUND(value - value_3m_ago, 1) AS change_3m
FROM kri_status
WHERE scope = 'enterprise' AND month_end = (SELECT MAX(month_end) FROM dim_month)
ORDER BY kri_id;

-- 2. Business units ranked by number of Red KRIs this month (window function)
SELECT business_unit, SUM(status = 'Red') AS red_kris, SUM(status = 'Amber') AS amber_kris,
       RANK() OVER (ORDER BY SUM(status = 'Red') DESC, SUM(status = 'Amber') DESC) AS rank
FROM kri_status
WHERE scope = 'business_unit' AND month_end = (SELECT MAX(month_end) FROM dim_month)
GROUP BY business_unit
ORDER BY rank;

-- 3. Months each business unit spent Red on overdue vulnerabilities (KRI-01)
SELECT business_unit, SUM(status = 'Red') AS months_red, COUNT(*) AS months_reported
FROM kri_status
WHERE kri_id = 'KRI-01' AND scope = 'business_unit'
GROUP BY business_unit
ORDER BY months_red DESC;

-- 4. Three-month rolling average of enterprise phishing click rate
SELECT month_end, ROUND(value, 2) AS click_rate,
       ROUND(AVG(value) OVER (ORDER BY month_end ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS rolling_3m
FROM kri_values
WHERE kri_id = 'KRI-06' AND scope = 'enterprise'
ORDER BY month_end;
