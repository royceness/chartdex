# Acme Outdoor Dashboard Recommendations

This file recommends the small set of dashboards Acme Outdoor should have seeded for the ChartDex demo. Keep these dashboards focused: each one should answer a common business question in three or four panels, using the generated SQLite views where possible.

## 1. Revenue Overview

Purpose: executive and growth-team view of whether the store is healthy.

Recommended panels:

- Revenue over time
- Sessions over time
- Average order value over time
- Purchases by platform

Queries:

```sql
-- Revenue, sessions, and AOV over time.
SELECT
    date,
    revenue_cents / 100.0 AS revenue,
    sessions,
    average_order_value_cents / 100.0 AS average_order_value
FROM v_daily_overview
ORDER BY date;
```

```sql
-- Purchases by platform for the latest 30 days.
SELECT
    platform,
    SUM(purchases) AS purchases,
    SUM(revenue_cents) / 100.0 AS revenue
FROM metric_facts_daily
WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
GROUP BY platform
ORDER BY purchases DESC;
```

## 2. Checkout Funnel

Purpose: operating view for checkout health and drop-off.

Recommended panels:

- Funnel totals from sessions to purchases
- Checkout conversion by platform
- Payment error rate by platform
- Promo success rate by promo code

Queries:

```sql
-- Funnel totals for the latest 30 days.
SELECT
    SUM(sessions) AS sessions,
    SUM(product_views) AS product_views,
    SUM(add_to_cart) AS add_to_cart,
    SUM(cart_views) AS cart_views,
    SUM(checkout_started) AS checkout_started,
    SUM(shipping_submitted) AS shipping_submitted,
    SUM(payment_started) AS payment_started,
    SUM(purchases) AS purchases
FROM metric_facts_daily
WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days');
```

```sql
-- Checkout conversion and payment errors by platform over time.
SELECT
    date,
    platform,
    checkout_conversion,
    payment_error_rate,
    promo_error_rate
FROM v_checkout_by_platform
ORDER BY date, platform;
```

```sql
-- Promo success by promo code for the latest 30 days.
SELECT
    promo_code,
    SUM(promo_attempts) AS promo_attempts,
    SUM(promo_success) AS promo_success,
    CASE WHEN SUM(promo_attempts) = 0 THEN 0.0
         ELSE CAST(SUM(promo_success) AS REAL) / SUM(promo_attempts)
    END AS promo_success_rate
FROM metric_facts_daily
WHERE promo_code <> 'none'
  AND date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
GROUP BY promo_code
ORDER BY promo_attempts DESC;
```

## 3. Campaign Performance

Purpose: growth-team view of whether campaigns are bringing valuable traffic.

Recommended panels:

- Revenue by channel
- Sessions by channel
- Overall conversion by channel
- Promo performance by code

Queries:

```sql
-- Channel performance for the latest 30 days.
SELECT
    channel,
    SUM(sessions) AS sessions,
    SUM(purchases) AS purchases,
    SUM(revenue_cents) / 100.0 AS revenue,
    CASE WHEN SUM(sessions) = 0 THEN 0.0
         ELSE CAST(SUM(purchases) AS REAL) / SUM(sessions)
    END AS overall_conversion
FROM metric_facts_daily
WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
GROUP BY channel
ORDER BY revenue DESC;
```

```sql
-- Promo code performance for the latest 30 days.
SELECT
    promo_code,
    SUM(checkout_started) AS checkout_started,
    SUM(promo_attempts) AS promo_attempts,
    SUM(promo_errors) AS promo_errors,
    SUM(purchases) AS purchases,
    SUM(revenue_cents) / 100.0 AS revenue,
    CASE WHEN SUM(checkout_started) = 0 THEN 0.0
         ELSE CAST(SUM(purchases) AS REAL) / SUM(checkout_started)
    END AS checkout_conversion
FROM metric_facts_daily
WHERE promo_code <> 'none'
  AND date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
GROUP BY promo_code
ORDER BY revenue DESC;
```

## 4. Experiment Rollout Health

Purpose: product and engineering view of active checkout experiments and rollouts.

Seed recommendation: do not seed this as an org dashboard initially. Let Codex create it during the demo when the user asks how the new experiment rollout is going.

Recommended panels:

- Checkout conversion by checkout variant
- Checkout conversion by platform and variant
- Payment error rate by platform and variant
- Promo error rate by promo code for checkout_v2 treatment

Queries:

```sql
-- Checkout conversion by variant over time.
SELECT
    date,
    checkout_variant,
    SUM(checkout_started) AS checkout_started,
    SUM(purchases) AS purchases,
    CASE WHEN SUM(checkout_started) = 0 THEN 0.0
         ELSE CAST(SUM(purchases) AS REAL) / SUM(checkout_started)
    END AS checkout_conversion
FROM metric_facts_daily
WHERE date >= date((SELECT MAX(date) FROM metric_facts_daily), '-59 days')
GROUP BY date, checkout_variant
ORDER BY date, checkout_variant;
```

```sql
-- Platform and variant rollout health.
SELECT
    date,
    platform,
    checkout_variant,
    checkout_started,
    purchases,
    checkout_conversion,
    payment_error_rate
FROM v_experiment_rollout
WHERE date >= date((SELECT MAX(date) FROM v_experiment_rollout), '-59 days')
ORDER BY date, platform, checkout_variant;
```

```sql
-- Promo error rates inside checkout_v2 treatment for the latest 30 days.
SELECT
    promo_code,
    cart_size_bucket,
    cart_weight_bucket,
    SUM(promo_attempts) AS promo_attempts,
    SUM(promo_errors) AS promo_errors,
    SUM(payment_errors) AS payment_errors,
    SUM(purchases) AS purchases,
    CASE WHEN SUM(promo_attempts) = 0 THEN 0.0
         ELSE CAST(SUM(promo_errors) AS REAL) / SUM(promo_attempts)
    END AS promo_error_rate,
    CASE WHEN SUM(checkout_started) = 0 THEN 0.0
         ELSE CAST(SUM(purchases) AS REAL) / SUM(checkout_started)
    END AS checkout_conversion
FROM metric_facts_daily
WHERE checkout_variant = 'checkout_v2_treatment'
  AND promo_code <> 'none'
  AND date >= date((SELECT MAX(date) FROM metric_facts_daily), '-29 days')
GROUP BY promo_code, cart_size_bucket, cart_weight_bucket
ORDER BY promo_error_rate DESC, promo_attempts DESC;
```

## Suggested Seed Set

Seed these org dashboards by default:

- Revenue Overview
- Checkout Funnel
- Campaign Performance

Leave Experiment Rollout Health unseeded so the demo can show Codex creating it on demand. If the implementation team wants a fourth default dashboard later, this is the best candidate because it uses the same generated data and directly supports rollout anomaly investigation.
