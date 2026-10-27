-- Synthetic technology-risk data model (all tables are populated by src/kri/generate.py).
DROP TABLE IF EXISTS dim_business_unit;  DROP TABLE IF EXISTS dim_month;
DROP TABLE IF EXISTS assets;             DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS incidents;          DROP TABLE IF EXISTS access_reviews;
DROP TABLE IF EXISTS phishing_campaigns; DROP TABLE IF EXISTS kri_definitions;
DROP TABLE IF EXISTS kri_thresholds;

CREATE TABLE dim_business_unit (business_unit TEXT PRIMARY KEY);
CREATE TABLE dim_month          (month_end TEXT PRIMARY KEY);              -- reporting months, 'YYYY-MM-DD'

CREATE TABLE assets (
    asset_id      TEXT PRIMARY KEY,
    business_unit TEXT NOT NULL REFERENCES dim_business_unit(business_unit),
    criticality   TEXT NOT NULL CHECK (criticality IN ('Low','Medium','High'))
);
CREATE TABLE findings (                                                     -- one vulnerability finding on one asset
    finding_id  INTEGER PRIMARY KEY,
    asset_id    TEXT NOT NULL,
    severity    TEXT NOT NULL CHECK (severity IN ('Low','Medium','High','Critical')),
    opened_date TEXT NOT NULL,
    due_date    TEXT NOT NULL,                                              -- opened + SLA for its severity
    closed_date TEXT                                                        -- NULL while still open
);
CREATE TABLE incidents (
    incident_id   INTEGER PRIMARY KEY,
    business_unit TEXT NOT NULL,
    occurred_date TEXT NOT NULL,
    severity      TEXT NOT NULL CHECK (severity IN ('Low','Medium','High','Critical')),
    detect_hours  REAL NOT NULL                                             -- time from occurrence to detection
);
CREATE TABLE access_reviews (
    review_id      INTEGER PRIMARY KEY,
    business_unit  TEXT NOT NULL,
    due_date       TEXT NOT NULL,
    completed_date TEXT                                                     -- NULL if not completed
);
CREATE TABLE phishing_campaigns (
    business_unit TEXT NOT NULL,
    month_end     TEXT NOT NULL,
    emails_sent   INTEGER NOT NULL,
    clicks        INTEGER NOT NULL,
    PRIMARY KEY (business_unit, month_end)
);

CREATE TABLE kri_definitions (
    kri_id      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    unit        TEXT NOT NULL,
    direction   TEXT NOT NULL CHECK (direction IN ('higher_is_worse','lower_is_worse')),
    agg         TEXT NOT NULL CHECK (agg IN ('ratio','sum')),   -- how business units roll up to the enterprise
    scale       REAL NOT NULL,                                  -- value = scale * numerator / denominator
    description TEXT NOT NULL
);
CREATE TABLE kri_thresholds (
    kri_id TEXT NOT NULL REFERENCES kri_definitions(kri_id),
    scope  TEXT NOT NULL CHECK (scope IN ('business_unit','enterprise')),
    amber  REAL NOT NULL,
    red    REAL NOT NULL,
    PRIMARY KEY (kri_id, scope)
);

INSERT INTO kri_definitions VALUES
 ('KRI-01','Overdue critical/high vulnerabilities','%','higher_is_worse','ratio',100,
  'Share of open Critical and High findings, at month end, that are past their SLA due date.'),
 ('KRI-02','Mean time to remediate critical vulnerabilities','days','higher_is_worse','ratio',1,
  'Average days from open to close for Critical findings closed in the month.'),
 ('KRI-03','High/critical security incidents','count','higher_is_worse','sum',1,
  'Number of High and Critical incidents that occurred in the month.'),
 ('KRI-04','Mean time to detect incidents','hours','higher_is_worse','ratio',1,
  'Average hours from occurrence to detection for incidents in the month.'),
 ('KRI-05','Access reviews completed on time','%','lower_is_worse','ratio',100,
  'Share of access reviews due in the month that were completed by their due date.'),
 ('KRI-06','Phishing simulation click rate','%','higher_is_worse','ratio',100,
  'Clicks divided by simulated phishing emails sent in the month.');

INSERT INTO kri_thresholds VALUES
 ('KRI-01','business_unit',10,20),  ('KRI-01','enterprise',10,20),
 ('KRI-02','business_unit',15,25),  ('KRI-02','enterprise',15,25),
 ('KRI-03','business_unit',2,4),    ('KRI-03','enterprise',8,14),
 ('KRI-04','business_unit',24,48),  ('KRI-04','enterprise',24,48),
 ('KRI-05','business_unit',90,80),  ('KRI-05','enterprise',90,80),
 ('KRI-06','business_unit',8,12),   ('KRI-06','enterprise',8,12);
