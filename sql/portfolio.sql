-- SQLite reference implementation. Rates are fractions, not percentages.
CREATE VIEW portfolio_baseline AS
SELECT COUNT(*) AS total_clients, COALESCE(SUM(default_label), 0) AS positive_labels,
       1.0 * SUM(default_label) / NULLIF(COUNT(*), 0) AS label_rate
FROM portfolio;

CREATE VIEW classified_clients AS
SELECT *, CASE WHEN pay_0 >= 2 THEN 'PAY_0 >= 2'
               WHEN pay_0 = 1 THEN 'PAY_0 = 1' ELSE 'PAY_0 <= 0' END AS pay0_group,
          CASE WHEN limit_bal <= 50000 THEN '<= 50,000'
               WHEN limit_bal <= 140000 THEN '50,000-140,000'
               WHEN limit_bal <= 240000 THEN '140,000-240,000'
               ELSE '> 240,000' END AS limit_band
FROM portfolio;

CREATE VIEW repayment_segments AS
SELECT pay0_group, COUNT(*) AS total_clients, SUM(default_label) AS positive_labels,
       AVG(default_label * 1.0) AS label_rate,
       COUNT(*) * 1.0 / (SELECT total_clients FROM portfolio_baseline) AS portfolio_share,
       SUM(default_label) * 1.0 / NULLIF((SELECT positive_labels FROM portfolio_baseline), 0) AS label_share
FROM classified_clients GROUP BY pay0_group;

CREATE VIEW stratified_segments AS
SELECT pay0_group, limit_band, COUNT(*) AS total_clients,
       SUM(default_label) AS positive_labels, AVG(default_label * 1.0) AS label_rate,
       COUNT(*) * 1.0 / (SELECT total_clients FROM portfolio_baseline) AS portfolio_share,
       SUM(default_label) * 1.0 / NULLIF((SELECT positive_labels FROM portfolio_baseline), 0) AS label_share
FROM classified_clients GROUP BY pay0_group, limit_band;

CREATE VIEW review_populations AS
SELECT 'scope_a' AS scope, * FROM portfolio WHERE pay_0 >= 2
UNION ALL SELECT 'scope_b', * FROM portfolio WHERE pay_0 > 0
UNION ALL SELECT 'increment', * FROM portfolio WHERE pay_0 = 1;

CREATE VIEW review_summary AS
SELECT names.scope, COUNT(pop.id) AS clients, COALESCE(SUM(pop.default_label), 0) AS positive_labels,
       COUNT(pop.id) * 1.0 / (SELECT total_clients FROM portfolio_baseline) AS workload_share,
       COALESCE(SUM(pop.default_label), 0) * 1.0 / NULLIF((SELECT positive_labels FROM portfolio_baseline), 0) AS positive_label_coverage,
       SUM(pop.default_label) * 1.0 / NULLIF(COUNT(pop.id), 0) AS label_rate
FROM (SELECT 'scope_a' AS scope UNION ALL SELECT 'scope_b' UNION ALL SELECT 'increment') names
LEFT JOIN review_populations pop ON names.scope = pop.scope GROUP BY names.scope;
