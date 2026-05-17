# ChartDex Demo Metrics Context

## Business Context

Acme Outdoor is a fictional mid-sized eCommerce company selling outdoor apparel and gear: jackets, shoes, backpacks, camping equipment, water bottles, and accessories. Customers shop through web desktop, web mobile, iOS app, and Android app. Checkout performance matters because small conversion changes have a direct revenue impact.

## Checkout Flow

The generated metrics follow this funnel:

sessions -> product_views -> add_to_cart -> cart_views -> checkout_started -> shipping_submitted -> promo_attempted -> promo_applied -> payment_started -> purchase_completed

Not every checkout includes a promo attempt. Rows with `promo_code = 'none'` normally have zero promo attempts.

## Core Formulas

- `product_view_rate = product_views / sessions`
- `add_to_cart_rate = add_to_cart / product_views`
- `cart_view_rate = cart_views / add_to_cart`
- `checkout_start_rate = checkout_started / cart_views`
- `shipping_completion_rate = shipping_submitted / checkout_started`
- `promo_success_rate = promo_success / promo_attempts`
- `promo_error_rate = promo_errors / promo_attempts`
- `payment_error_rate = payment_errors / payment_started`
- `checkout_conversion = purchases / checkout_started`
- `payment_completion_rate = purchases / payment_started`
- `overall_conversion = purchases / sessions`
- `average_order_value = revenue_cents / purchases`
- `refund_rate = refunds / purchases`
- `revenue = revenue_cents / 100`

Use zero-denominator handling when explaining or computing derived metrics.

## Dimensions

Key breakdowns include `platform`, `channel`, `region`, `customer_segment`, `product_category`, `cart_size_bucket`, `cart_weight_bucket`, `promo_code`, and `checkout_variant`.

Important values:

- Platforms: `web_desktop_mac`, `web_desktop_windows`, `web_mobile`, `ios_app`, `android_app`
- Promo codes: `none`, `WELCOME10`, `FREESHIP50`, `FROST20`, `GEARUP15`, `MOTHERSDAY`
- Checkout variants: `classic_checkout`, `checkout_v2_control`, `checkout_v2_treatment`

## Experiments

`EXP-001: Bigger checkout CTA` runs around days 35-65. The hypothesis is that a larger Continue to Payment button improves mobile checkout progression. Treatment should be modestly better on mobile.

`EXP-002: Shipping estimator` runs around days 80-115. The hypothesis is that earlier shipping estimates reduce abandonment. Treatment should modestly improve shipping completion and checkout conversion, with a slight AOV lift.

`EXP-003: checkout_v2 rollout` starts around day 130 and ramps toward the dataset end. It is the central demo experiment. Before the hidden bug period, `checkout_v2_treatment` generally improves conversion and slightly lowers payment errors. Near the end, Android treatment performance dips.

## Promotions And Incidents

Spring Gear Launch runs around days 20-30 and raises sessions, product views, and revenue, especially in paid search, social, and email.

Easter / long-weekend sale runs around days 55-62 with `WELCOME10` and `FREESHIP50`. Sessions and purchases rise while AOV softens slightly.

Mid-season sale runs around days 105-112 with `GEARUP15`, strongest for email, returning customers, and VIP customers.

Frost promo runs around days 160-179 with `FROST20`. Before the hidden bug, it improves revenue and conversion for jackets and backpacks, with more heavy and 3+ item carts.

`INC-001: Payment provider degradation` is a one-day incident around day 88. Payment errors rise sharply and purchases fall, strongest on `web_desktop_windows` and `web_mobile`.

`INC-002: Image CDN issue` is a one-day incident around day 122. Product views and add-to-cart drop mostly on web platforms, with a smaller revenue decline.

## Internal Data-Generation Note

`BUG-1772: Android checkout_v2 promo validation bug` is intentionally generated but is not known to the app user.

The affected slice is:

- `platform = 'android_app'`
- `checkout_variant = 'checkout_v2_treatment'`
- `promo_code = 'FROST20'`
- `cart_size_bucket = '3_plus_items'`
- `cart_weight_bucket = 'heavy'`

The bug starts 7-10 days before the dataset end. Users can enter the promo code, but at payment time the discount conflicts with heavy-item shipping rules. The generated data shows promo errors and payment errors rising sharply while checkout conversion falls in this narrow slice. Globally, checkout conversion only dips slightly, so the issue should require breakdowns to diagnose.

## Seed Dashboards

The database includes org dashboards for Revenue Overview, Checkout Funnel, and Campaign Performance. It intentionally does not include an initial org dashboard named Experiment Rollout Health; Codex should create that dynamically in the demo when asked how the new experiment rollout is going.

## Suggested Demo Questions

- Show me the checkout conversion dashboard.
- How is checkout conversion computed?
- How's the new experiment rollout going?
- What's that dip in Android conversion?
- Is the issue tied to a promo code?
- Summarize this as an engineering follow-up.

Expected final diagnosis: the dip is isolated to Android users in `checkout_v2_treatment` using `FROST20` with 3+ heavy carts. Payment errors and promo validation failures increased at the same time, suggesting a platform-specific promo validation bug rather than broad demand weakness.

