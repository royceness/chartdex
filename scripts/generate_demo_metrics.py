#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import random
import sqlite3
from typing import Any


PLATFORMS = [
    "web_desktop_mac",
    "web_desktop_windows",
    "web_mobile",
    "ios_app",
    "android_app",
]
CHANNELS = ["direct", "organic_search", "paid_search", "email", "social", "affiliate"]
REGIONS = ["US", "AU", "UK", "EU"]
CUSTOMER_SEGMENTS = ["new", "returning", "vip"]
PRODUCT_CATEGORIES = ["jackets", "shoes", "backpacks", "camping", "accessories"]
CART_SIZE_BUCKETS = ["1_item", "2_items", "3_plus_items"]
CART_WEIGHT_BUCKETS = ["light", "standard", "heavy"]
PROMO_CODES = ["none", "WELCOME10", "FREESHIP50", "FROST20", "GEARUP15", "MOTHERSDAY"]
CHECKOUT_VARIANTS = ["classic_checkout", "checkout_v2_control", "checkout_v2_treatment"]

FACT_COLUMNS = [
    "date",
    "platform",
    "channel",
    "region",
    "customer_segment",
    "product_category",
    "cart_size_bucket",
    "cart_weight_bucket",
    "promo_code",
    "checkout_variant",
    "sessions",
    "product_views",
    "add_to_cart",
    "cart_views",
    "checkout_started",
    "shipping_submitted",
    "promo_attempts",
    "promo_success",
    "promo_errors",
    "payment_started",
    "payment_errors",
    "purchases",
    "revenue_cents",
    "refunds",
    "refund_amount_cents",
]


@dataclass(frozen=True)
class EventWindow:
    start: int
    end: int

    def contains(self, day_index: int) -> bool:
        return self.start <= day_index <= self.end


@dataclass(frozen=True)
class Timeline:
    spring_launch: EventWindow
    bigger_cta: EventWindow
    easter_sale: EventWindow
    payment_incident: EventWindow
    shipping_estimator: EventWindow
    midseason_sale: EventWindow
    cdn_incident: EventWindow
    checkout_v2_rollout: EventWindow
    frost_promo: EventWindow
    hidden_bug: EventWindow


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def resolve_date_range(
    *, days: int, start_date: date | None = None, end_date: date | None = None
) -> tuple[date, date, int]:
    if days < 1:
        raise ValueError("--days must be at least 1")

    if start_date and end_date:
        if end_date < start_date:
            raise ValueError("--end-date must be on or after --start-date")
        resolved_days = (end_date - start_date).days + 1
        return start_date, end_date, resolved_days
    if start_date:
        return start_date, start_date + timedelta(days=days - 1), days
    if end_date:
        return end_date - timedelta(days=days - 1), end_date, days

    resolved_end = date.today()
    return resolved_end - timedelta(days=days - 1), resolved_end, days


def scaled_day(template_day: int, total_days: int) -> int:
    if total_days <= 1:
        return 0
    return max(0, min(total_days - 1, round(template_day * (total_days - 1) / 179)))


def build_timeline(total_days: int) -> Timeline:
    def window(start: int, end: int) -> EventWindow:
        return EventWindow(scaled_day(start, total_days), scaled_day(end, total_days))

    return Timeline(
        spring_launch=window(20, 30),
        bigger_cta=window(35, 65),
        easter_sale=window(55, 62),
        payment_incident=window(88, 88),
        shipping_estimator=window(80, 115),
        midseason_sale=window(105, 112),
        cdn_incident=window(122, 122),
        checkout_v2_rollout=window(130, 179),
        frost_promo=window(160, 179),
        hidden_bug=window(171, 179),
    )


def choose_weighted(rng: random.Random, weighted_values: list[tuple[str, float]]) -> str:
    total = sum(weight for _, weight in weighted_values)
    pick = rng.random() * total
    upto = 0.0
    for value, weight in weighted_values:
        upto += weight
        if upto >= pick:
            return value
    return weighted_values[-1][0]


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def round_count(value: float) -> int:
    return max(0, int(round(value)))


def sampled_count(rng: random.Random, value: float) -> int:
    if value <= 0:
        return 0
    whole = math.floor(value)
    return whole + (1 if rng.random() < value - whole else 0)


def platform_weights() -> list[tuple[str, float]]:
    return [
        ("web_desktop_mac", 0.16),
        ("web_desktop_windows", 0.20),
        ("web_mobile", 0.28),
        ("ios_app", 0.19),
        ("android_app", 0.17),
    ]


def channel_weights(day_index: int, timeline: Timeline) -> list[tuple[str, float]]:
    weights = {
        "direct": 0.23,
        "organic_search": 0.25,
        "paid_search": 0.19,
        "email": 0.12,
        "social": 0.13,
        "affiliate": 0.08,
    }
    if timeline.spring_launch.contains(day_index):
        weights["paid_search"] *= 1.45
        weights["social"] *= 1.35
        weights["email"] *= 1.25
    if timeline.easter_sale.contains(day_index):
        weights["email"] *= 1.65
        weights["paid_search"] *= 1.25
        weights["social"] *= 1.2
    if timeline.midseason_sale.contains(day_index):
        weights["email"] *= 2.1
        weights["direct"] *= 1.2
    if timeline.frost_promo.contains(day_index):
        weights["email"] *= 1.45
        weights["paid_search"] *= 1.25
    return list(weights.items())


def segment_weights(day_index: int, timeline: Timeline, channel: str) -> list[tuple[str, float]]:
    weights = {"new": 0.46, "returning": 0.42, "vip": 0.12}
    if channel in {"email", "direct"}:
        weights["returning"] *= 1.25
        weights["vip"] *= 1.35
        weights["new"] *= 0.75
    if timeline.midseason_sale.contains(day_index):
        weights["returning"] *= 1.2
        weights["vip"] *= 1.25
    return list(weights.items())


def product_weights(day_index: int, timeline: Timeline, promo_code: str) -> list[tuple[str, float]]:
    weights = {
        "jackets": 0.18,
        "shoes": 0.22,
        "backpacks": 0.20,
        "camping": 0.18,
        "accessories": 0.22,
    }
    if timeline.spring_launch.contains(day_index):
        weights["jackets"] *= 1.25
        weights["backpacks"] *= 1.3
        weights["camping"] *= 1.2
    if promo_code == "FROST20":
        weights["jackets"] *= 2.0
        weights["backpacks"] *= 1.7
        weights["accessories"] *= 0.55
    if promo_code == "GEARUP15":
        weights["camping"] *= 1.55
        weights["backpacks"] *= 1.35
    return list(weights.items())


def cart_size_weights(day_index: int, timeline: Timeline, promo_code: str) -> list[tuple[str, float]]:
    weights = {"1_item": 0.48, "2_items": 0.33, "3_plus_items": 0.19}
    if promo_code in {"FROST20", "GEARUP15", "FREESHIP50"}:
        weights["2_items"] *= 1.15
        weights["3_plus_items"] *= 1.55
        weights["1_item"] *= 0.65
    if timeline.frost_promo.contains(day_index):
        weights["3_plus_items"] *= 1.25
    return list(weights.items())


def cart_weight_weights(promo_code: str, cart_size_bucket: str, product_category: str) -> list[tuple[str, float]]:
    weights = {"light": 0.39, "standard": 0.43, "heavy": 0.18}
    if cart_size_bucket == "3_plus_items":
        weights["heavy"] *= 1.75
        weights["standard"] *= 1.15
        weights["light"] *= 0.55
    if product_category in {"camping", "backpacks"}:
        weights["heavy"] *= 1.6
    if promo_code == "FROST20":
        weights["heavy"] *= 1.4
    return list(weights.items())


def promo_weights(day_index: int, timeline: Timeline) -> list[tuple[str, float]]:
    weights = {
        "none": 0.68,
        "WELCOME10": 0.10,
        "FREESHIP50": 0.08,
        "FROST20": 0.01,
        "GEARUP15": 0.06,
        "MOTHERSDAY": 0.07,
    }
    if timeline.easter_sale.contains(day_index):
        weights["WELCOME10"] *= 2.5
        weights["FREESHIP50"] *= 2.9
        weights["none"] *= 0.55
    if timeline.midseason_sale.contains(day_index):
        weights["GEARUP15"] *= 4.0
        weights["none"] *= 0.55
    if timeline.frost_promo.contains(day_index):
        weights["FROST20"] *= 28.0
        weights["none"] *= 0.56
        weights["WELCOME10"] *= 0.55
        weights["MOTHERSDAY"] *= 0.4
    if not timeline.frost_promo.contains(day_index):
        weights["FROST20"] *= 0.08
    return list(weights.items())


def checkout_variant_weights(day_index: int, timeline: Timeline) -> list[tuple[str, float]]:
    if timeline.checkout_v2_rollout.contains(day_index):
        denominator = max(1, timeline.checkout_v2_rollout.end - timeline.checkout_v2_rollout.start)
        progress = (day_index - timeline.checkout_v2_rollout.start) / denominator
        treatment = 0.20 + 0.44 * progress
        control = 0.24 + 0.04 * progress
        classic = 1.0 - treatment - control
        return [
            ("classic_checkout", max(0.08, classic)),
            ("checkout_v2_control", control),
            ("checkout_v2_treatment", treatment),
        ]
    if timeline.bigger_cta.contains(day_index):
        return [
            ("classic_checkout", 0.44),
            ("checkout_v2_control", 0.28),
            ("checkout_v2_treatment", 0.28),
        ]
    if timeline.shipping_estimator.contains(day_index):
        return [
            ("classic_checkout", 0.58),
            ("checkout_v2_control", 0.23),
            ("checkout_v2_treatment", 0.19),
        ]
    return [
        ("classic_checkout", 0.88),
        ("checkout_v2_control", 0.07),
        ("checkout_v2_treatment", 0.05),
    ]


def daily_session_target(day_index: int, current_date: date, timeline: Timeline, total_days: int) -> float:
    weekday = current_date.weekday()
    weekday_multiplier = {
        0: 0.96,
        1: 0.98,
        2: 1.0,
        3: 1.02,
        4: 1.06,
        5: 1.14,
        6: 1.10,
    }[weekday]
    trend = 1.0 + 0.0010 * day_index
    seasonal = 1.0 + 0.025 * math.sin(day_index / max(1, total_days) * math.tau * 2.0)
    event_multiplier = 1.0
    if timeline.spring_launch.contains(day_index):
        event_multiplier *= 1.22
    if timeline.easter_sale.contains(day_index):
        event_multiplier *= 1.34
    if timeline.midseason_sale.contains(day_index):
        event_multiplier *= 1.18
    if timeline.frost_promo.contains(day_index):
        event_multiplier *= 1.18
    return 47000.0 * weekday_multiplier * trend * seasonal * event_multiplier


def random_slice(
    rng: random.Random, day_index: int, timeline: Timeline
) -> tuple[str, str, str, str, str, str, str, str, str]:
    promo_code = choose_weighted(rng, promo_weights(day_index, timeline))
    channel = choose_weighted(rng, channel_weights(day_index, timeline))
    segment = choose_weighted(rng, segment_weights(day_index, timeline, channel))
    product = choose_weighted(rng, product_weights(day_index, timeline, promo_code))
    cart_size = choose_weighted(rng, cart_size_weights(day_index, timeline, promo_code))
    cart_weight = choose_weighted(rng, cart_weight_weights(promo_code, cart_size, product))
    return (
        choose_weighted(rng, platform_weights()),
        channel,
        choose_weighted(rng, [("US", 0.58), ("AU", 0.13), ("UK", 0.14), ("EU", 0.15)]),
        segment,
        product,
        cart_size,
        cart_weight,
        promo_code,
        choose_weighted(rng, checkout_variant_weights(day_index, timeline)),
    )


def guaranteed_slices(day_index: int, timeline: Timeline) -> list[tuple[str, str, str, str, str, str, str, str, str, float]]:
    slices: list[tuple[str, str, str, str, str, str, str, str, str, float]] = []
    if timeline.frost_promo.contains(day_index):
        base = 1050.0 if day_index < timeline.hidden_bug.start else 4700.0
        slices.extend(
            [
                (
                    "android_app",
                    "email",
                    "US",
                    "returning",
                    "jackets",
                    "3_plus_items",
                    "heavy",
                    "FROST20",
                    "checkout_v2_treatment",
                    base,
                ),
                (
                    "ios_app",
                    "email",
                    "US",
                    "returning",
                    "jackets",
                    "3_plus_items",
                    "heavy",
                    "FROST20",
                    "checkout_v2_treatment",
                    980.0,
                ),
                (
                    "android_app",
                    "direct",
                    "US",
                    "returning",
                    "jackets",
                    "2_items",
                    "standard",
                    "FROST20",
                    "checkout_v2_treatment",
                    760.0,
                ),
            ]
        )
    return slices


def generate_funnel_counts(
    *,
    rng: random.Random,
    day_index: int,
    sessions: int,
    platform: str,
    channel: str,
    customer_segment: str,
    product_category: str,
    cart_size_bucket: str,
    cart_weight_bucket: str,
    promo_code: str,
    checkout_variant: str,
    timeline: Timeline,
) -> dict[str, int]:
    product_view_rate = 0.73 * rng.uniform(0.96, 1.04)
    add_to_cart_rate = 0.155 * rng.uniform(0.92, 1.08)
    cart_view_rate = 0.83 * rng.uniform(0.96, 1.03)
    checkout_start_rate = 0.63 * rng.uniform(0.94, 1.06)
    shipping_submit_rate = 0.82 * rng.uniform(0.95, 1.05)
    payment_start_rate = 0.90 * rng.uniform(0.96, 1.03)
    purchase_rate = 0.83 * rng.uniform(0.96, 1.04)
    payment_error_rate = 0.026 * rng.uniform(0.88, 1.18)
    promo_error_rate = 0.035 * rng.uniform(0.85, 1.20)
    aov_cents = 8850.0 * rng.uniform(0.92, 1.08)

    conversion_multiplier = 1.0
    if platform == "ios_app":
        conversion_multiplier *= 1.08
        aov_cents *= 1.04
    elif platform == "android_app":
        conversion_multiplier *= 0.97
        payment_error_rate *= 1.05
    elif platform == "web_desktop_mac":
        conversion_multiplier *= 1.03
        aov_cents *= 1.05
    elif platform == "web_mobile":
        conversion_multiplier *= 0.92
    elif platform == "web_desktop_windows":
        conversion_multiplier *= 0.99

    if customer_segment == "vip":
        conversion_multiplier *= 1.20
        aov_cents *= 1.15
    elif customer_segment == "returning":
        conversion_multiplier *= 1.08
    elif customer_segment == "new":
        conversion_multiplier *= 0.92

    if channel == "email":
        conversion_multiplier *= 1.12
    elif channel == "social":
        conversion_multiplier *= 0.90
    elif channel == "paid_search":
        conversion_multiplier *= 1.02
    elif channel == "direct":
        conversion_multiplier *= 1.06

    if cart_size_bucket == "2_items":
        conversion_multiplier *= 1.03
        aov_cents *= 1.38
    elif cart_size_bucket == "3_plus_items":
        conversion_multiplier *= 0.95
        aov_cents *= 1.78

    if cart_weight_bucket == "heavy":
        conversion_multiplier *= 0.92
        aov_cents *= 1.25
        shipping_submit_rate *= 0.96
    elif cart_weight_bucket == "light":
        aov_cents *= 0.82

    if product_category == "jackets":
        aov_cents *= 1.25
    elif product_category == "shoes":
        aov_cents *= 1.08
    elif product_category == "camping":
        aov_cents *= 1.35
    elif product_category == "accessories":
        aov_cents *= 0.62

    if promo_code != "none":
        conversion_multiplier *= 1.06
        aov_cents *= {
            "WELCOME10": 0.92,
            "FREESHIP50": 0.96,
            "FROST20": 0.90,
            "GEARUP15": 0.93,
            "MOTHERSDAY": 0.94,
        }[promo_code]
    if promo_code == "FREESHIP50" and cart_weight_bucket == "heavy":
        promo_error_rate *= 1.45

    if timeline.spring_launch.contains(day_index):
        product_view_rate *= 1.08
        aov_cents *= 1.06
    if timeline.easter_sale.contains(day_index):
        conversion_multiplier *= 1.10
        aov_cents *= 0.94
    if timeline.midseason_sale.contains(day_index):
        conversion_multiplier *= 1.07
    if timeline.frost_promo.contains(day_index) and promo_code == "FROST20":
        if product_category in {"jackets", "backpacks"}:
            conversion_multiplier *= 1.10
            aov_cents *= 1.04

    if timeline.bigger_cta.contains(day_index) and checkout_variant == "checkout_v2_treatment":
        if platform in {"web_mobile", "ios_app", "android_app"}:
            payment_start_rate *= 1.025
            conversion_multiplier *= 1.025
    if timeline.shipping_estimator.contains(day_index) and checkout_variant == "checkout_v2_treatment":
        shipping_submit_rate *= 1.025
        conversion_multiplier *= 1.015
        aov_cents *= 1.015
    if timeline.checkout_v2_rollout.contains(day_index):
        if checkout_variant == "checkout_v2_treatment":
            conversion_multiplier *= 1.055
            payment_error_rate *= 0.90
        elif checkout_variant == "checkout_v2_control":
            conversion_multiplier *= 1.01
            payment_error_rate *= 0.97

    if timeline.payment_incident.contains(day_index):
        payment_error_rate *= 2.85
        if platform in {"web_desktop_windows", "web_mobile"}:
            payment_error_rate *= 1.25
        purchase_rate *= 0.88
    if timeline.cdn_incident.contains(day_index) and platform.startswith("web_"):
        product_view_rate *= 0.83
        add_to_cart_rate *= 0.90
        purchase_rate *= 0.96

    is_hidden_bug_slice = (
        timeline.hidden_bug.contains(day_index)
        and platform == "android_app"
        and checkout_variant == "checkout_v2_treatment"
        and promo_code == "FROST20"
        and cart_size_bucket == "3_plus_items"
        and cart_weight_bucket == "heavy"
    )
    if is_hidden_bug_slice:
        promo_error_rate *= 5.4
        payment_error_rate *= 3.2
        shipping_submit_rate *= 0.90
        payment_start_rate *= 0.92
        purchase_rate *= 0.28

    shipping_submit_rate = clamp(shipping_submit_rate * math.sqrt(conversion_multiplier), 0.50, 0.96)
    payment_start_rate = clamp(payment_start_rate * math.sqrt(conversion_multiplier), 0.58, 0.98)
    purchase_rate = clamp(purchase_rate * conversion_multiplier, 0.38, 0.96)
    product_view_rate = clamp(product_view_rate, 0.52, 0.92)
    add_to_cart_rate = clamp(add_to_cart_rate, 0.08, 0.25)
    cart_view_rate = clamp(cart_view_rate, 0.68, 0.94)
    checkout_start_rate = clamp(checkout_start_rate, 0.45, 0.82)
    promo_error_rate = clamp(promo_error_rate, 0.005, 0.55)
    payment_error_rate = clamp(payment_error_rate, 0.004, 0.35)

    product_views = min(sessions, round_count(sessions * product_view_rate))
    add_to_cart = min(product_views, round_count(product_views * add_to_cart_rate))
    cart_views = min(add_to_cart, round_count(add_to_cart * cart_view_rate))
    checkout_started = min(cart_views, round_count(cart_views * checkout_start_rate))
    shipping_submitted = min(
        checkout_started, round_count(checkout_started * shipping_submit_rate)
    )
    if promo_code == "none":
        promo_attempts = 0
        promo_success = 0
        promo_errors = 0
    else:
        promo_attempts = min(shipping_submitted, round_count(shipping_submitted * 0.88))
        promo_errors = min(promo_attempts, sampled_count(rng, promo_attempts * promo_error_rate))
        promo_success = max(0, promo_attempts - promo_errors)

    payment_started = min(shipping_submitted, round_count(shipping_submitted * payment_start_rate))
    payment_errors = min(payment_started, sampled_count(rng, payment_started * payment_error_rate))
    purchases = min(payment_started, round_count((payment_started - payment_errors) * purchase_rate))

    refunds = sampled_count(rng, purchases * rng.uniform(0.006, 0.018))
    refund_amount_cents = round_count(refunds * aov_cents * rng.uniform(0.65, 0.95))
    revenue_cents = round_count(purchases * aov_cents)

    return {
        "sessions": sessions,
        "product_views": product_views,
        "add_to_cart": add_to_cart,
        "cart_views": cart_views,
        "checkout_started": checkout_started,
        "shipping_submitted": shipping_submitted,
        "promo_attempts": promo_attempts,
        "promo_success": promo_success,
        "promo_errors": promo_errors,
        "payment_started": payment_started,
        "payment_errors": payment_errors,
        "purchases": purchases,
        "revenue_cents": revenue_cents,
        "refunds": refunds,
        "refund_amount_cents": refund_amount_cents,
    }


def generate_fact_rows(
    *, start: date, total_days: int, seed: int, timeline: Timeline
) -> list[tuple[Any, ...]]:
    rng = random.Random(seed)
    rows: list[tuple[Any, ...]] = []
    metric_columns = FACT_COLUMNS[10:]
    for day_index in range(total_days):
        current_date = start + timedelta(days=day_index)
        target_sessions = daily_session_target(day_index, current_date, timeline, total_days)
        slices_per_day = 435 if total_days >= 120 else max(180, min(435, total_days * 4))
        base_sessions = target_sessions / slices_per_day
        aggregated: dict[tuple[str, ...], dict[str, int]] = defaultdict(
            lambda: {column: 0 for column in metric_columns}
        )

        for _ in range(slices_per_day):
            dims = random_slice(rng, day_index, timeline)
            sessions = round_count(base_sessions * rng.lognormvariate(-0.09, 0.48))
            if sessions < 8:
                sessions = 8
            counts = generate_funnel_counts(
                rng=rng,
                day_index=day_index,
                sessions=sessions,
                platform=dims[0],
                channel=dims[1],
                customer_segment=dims[3],
                product_category=dims[4],
                cart_size_bucket=dims[5],
                cart_weight_bucket=dims[6],
                promo_code=dims[7],
                checkout_variant=dims[8],
                timeline=timeline,
            )
            key = (current_date.isoformat(), *dims)
            for column, value in counts.items():
                aggregated[key][column] += value

        for guaranteed in guaranteed_slices(day_index, timeline):
            dims = guaranteed[:-1]
            sessions = round_count(guaranteed[-1] * rng.uniform(0.92, 1.08))
            counts = generate_funnel_counts(
                rng=rng,
                day_index=day_index,
                sessions=sessions,
                platform=dims[0],
                channel=dims[1],
                customer_segment=dims[3],
                product_category=dims[4],
                cart_size_bucket=dims[5],
                cart_weight_bucket=dims[6],
                promo_code=dims[7],
                checkout_variant=dims[8],
                timeline=timeline,
            )
            key = (current_date.isoformat(), *dims)
            for column, value in counts.items():
                aggregated[key][column] += value

        for key, counts in sorted(aggregated.items()):
            rows.append((*key, *(counts[column] for column in metric_columns)))
    return rows


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metric_facts_daily (
            date TEXT NOT NULL,
            platform TEXT NOT NULL,
            channel TEXT NOT NULL,
            region TEXT NOT NULL,
            customer_segment TEXT NOT NULL,
            product_category TEXT NOT NULL,
            cart_size_bucket TEXT NOT NULL,
            cart_weight_bucket TEXT NOT NULL,
            promo_code TEXT NOT NULL,
            checkout_variant TEXT NOT NULL,
            sessions INTEGER NOT NULL,
            product_views INTEGER NOT NULL,
            add_to_cart INTEGER NOT NULL,
            cart_views INTEGER NOT NULL,
            checkout_started INTEGER NOT NULL,
            shipping_submitted INTEGER NOT NULL,
            promo_attempts INTEGER NOT NULL,
            promo_success INTEGER NOT NULL,
            promo_errors INTEGER NOT NULL,
            payment_started INTEGER NOT NULL,
            payment_errors INTEGER NOT NULL,
            purchases INTEGER NOT NULL,
            revenue_cents INTEGER NOT NULL,
            refunds INTEGER NOT NULL,
            refund_amount_cents INTEGER NOT NULL
        );

        CREATE INDEX idx_metric_facts_daily_date ON metric_facts_daily(date);
        CREATE INDEX idx_metric_facts_daily_platform ON metric_facts_daily(platform);
        CREATE INDEX idx_metric_facts_daily_variant ON metric_facts_daily(checkout_variant);
        CREATE INDEX idx_metric_facts_daily_promo ON metric_facts_daily(promo_code);
        CREATE INDEX idx_metric_facts_daily_bug_probe ON metric_facts_daily(
            platform, checkout_variant, promo_code, cart_size_bucket, cart_weight_bucket, date
        );

        CREATE TABLE metric_catalog (
            metric_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            formula TEXT NOT NULL,
            description TEXT NOT NULL,
            ui_location TEXT NOT NULL,
            good_for TEXT NOT NULL,
            common_failure_modes TEXT NOT NULL,
            recommended_breakdowns TEXT NOT NULL
        );

        CREATE TABLE business_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            description TEXT NOT NULL,
            affected_dimensions_json TEXT NOT NULL,
            expected_impact TEXT NOT NULL,
            demo_hint TEXT NOT NULL
        );

        CREATE TABLE experiments (
            experiment_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            status TEXT NOT NULL,
            hypothesis TEXT NOT NULL,
            variants_json TEXT NOT NULL,
            rollout_notes TEXT NOT NULL,
            success_metric TEXT NOT NULL,
            guardrail_metrics TEXT NOT NULL
        );

        CREATE TABLE ui_metric_mapping (
            metric_id TEXT NOT NULL,
            ui_step TEXT NOT NULL,
            ui_component TEXT NOT NULL,
            description TEXT NOT NULL
        );

        CREATE TABLE seed_dashboards (
            id TEXT PRIMARY KEY,
            space TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            tags TEXT NOT NULL,
            panels_json TEXT NOT NULL
        );
        """
    )


def insert_metadata(connection: sqlite3.Connection, start: date, timeline: Timeline) -> None:
    metric_rows = [
        (
            "product_view_rate",
            "Product View Rate",
            "product_views / sessions",
            "Measures how many sessions reach product detail pages.",
            "Browse and product discovery",
            "Understanding discovery health before cart intent.",
            "image CDN issues, search relevance, category navigation bugs, slow product pages.",
            "platform, channel, product_category, region.",
        ),
        (
            "add_to_cart_rate",
            "Add to Cart Rate",
            "add_to_cart / product_views",
            "Measures how often product views turn into add-to-cart actions.",
            "Product detail pages",
            "Detecting product detail page or merchandising issues.",
            "pricing mismatch, inventory confusion, broken add-to-cart button, product media issues.",
            "platform, product_category, channel, customer_segment.",
        ),
        (
            "checkout_conversion",
            "Checkout Conversion",
            "purchases / checkout_started",
            "Measures how many users who start checkout complete a purchase.",
            "Checkout funnel, payment step, experiment dashboards",
            "Detecting checkout friction independent of top-of-funnel traffic.",
            "payment failures, promo code bugs, platform-specific UI issues, shipping form issues, app regressions.",
            "platform, channel, checkout_variant, promo_code, cart_size_bucket, cart_weight_bucket.",
        ),
        (
            "payment_error_rate",
            "Payment Error Rate",
            "payment_errors / payment_started",
            "Measures the share of payment attempts that encounter an error.",
            "Payment step",
            "Identifying gateway, validation, app, or payment-method regressions.",
            "provider outage, bad request payload, promo incompatibility, mobile app bug.",
            "platform, checkout_variant, promo_code, cart_size_bucket.",
        ),
        (
            "promo_success_rate",
            "Promo Success Rate",
            "promo_success / promo_attempts",
            "Measures how often attempted promo codes are successfully applied.",
            "Cart and promo step",
            "Detecting broken promotions or eligibility confusion.",
            "invalid code, incompatible cart contents, app bug, heavy-item shipping exclusion.",
            "promo_code, platform, cart_size_bucket, cart_weight_bucket, checkout_variant.",
        ),
        (
            "promo_error_rate",
            "Promo Error Rate",
            "promo_errors / promo_attempts",
            "Measures how often attempted promo codes produce validation errors.",
            "Promo step and payment validation",
            "Finding promotion eligibility and validation regressions.",
            "expired code, rule conflict, platform-specific validation bug, shipping exclusion.",
            "promo_code, platform, checkout_variant, cart_size_bucket, cart_weight_bucket.",
        ),
        (
            "overall_conversion",
            "Overall Conversion",
            "purchases / sessions",
            "Measures how many sessions result in a purchase.",
            "Revenue overview",
            "Monitoring end-to-end business performance.",
            "traffic mix shifts, site outages, checkout bugs, campaign quality changes.",
            "channel, platform, customer_segment, region.",
        ),
        (
            "average_order_value",
            "Average Order Value",
            "revenue_cents / purchases",
            "Measures average purchase value before refunds.",
            "Revenue overview and campaign dashboards",
            "Understanding order mix, promo discounting, and basket-building behavior.",
            "discount mix, bundle changes, shipping thresholds, product mix shifts, VIP/customer mix changes.",
            "promo_code, cart_size_bucket, cart_weight_bucket, product_category, customer_segment.",
        ),
        (
            "refund_rate",
            "Refund Rate",
            "refunds / purchases",
            "Measures the share of purchases later refunded.",
            "Revenue quality dashboard",
            "Guardrailing campaign and product quality.",
            "product quality issues, sizing mismatch, campaign mis-targeting, fulfillment issues.",
            "product_category, region, channel, customer_segment.",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO metric_catalog (
            metric_id, display_name, formula, description, ui_location, good_for,
            common_failure_modes, recommended_breakdowns
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        metric_rows,
    )

    def event_date(day_index: int) -> str:
        return (start + timedelta(days=day_index)).isoformat()

    events = [
        (
            "PROMO-001",
            "promotion",
            "Spring Gear Launch",
            timeline.spring_launch,
            "Launch campaign for new jackets, backpacks, and camping gear.",
            {"channels": ["paid_search", "social", "email"], "categories": ["jackets", "backpacks", "camping"]},
            "Sessions, product views, and revenue rise during the launch window.",
            "Use as a clean example of campaign-driven growth.",
        ),
        (
            "EXP-001",
            "experiment",
            "Bigger checkout CTA",
            timeline.bigger_cta,
            "Mobile checkout experiment with a larger Continue to Payment button.",
            {"platforms": ["web_mobile", "ios_app", "android_app"], "variants": CHECKOUT_VARIANTS},
            "Treatment improves checkout conversion by roughly 2-4% on mobile.",
            "Useful historical example of a healthy mobile checkout experiment.",
        ),
        (
            "PROMO-002",
            "promotion",
            "Easter / long-weekend sale",
            timeline.easter_sale,
            "Promotional sale using WELCOME10 and FREESHIP50.",
            {"promo_codes": ["WELCOME10", "FREESHIP50"], "channels": ["email", "paid_search", "social"]},
            "Sessions and purchases increase while AOV is modestly lower.",
            "Good for explaining why revenue can rise while AOV softens.",
        ),
        (
            "INC-001",
            "outage",
            "Payment provider degradation",
            timeline.payment_incident,
            "One-day payment provider degradation affecting all platforms.",
            {"platforms": PLATFORMS, "strongest": ["web_desktop_windows", "web_mobile"]},
            "Payment errors rise sharply and purchases fall for one day.",
            "Visible daily incident but old enough not to be the main demo bug.",
        ),
        (
            "EXP-002",
            "experiment",
            "Shipping estimator",
            timeline.shipping_estimator,
            "Experiment showing shipping estimates earlier in checkout.",
            {"variants": CHECKOUT_VARIANTS},
            "Shipping completion and checkout conversion improve slightly; AOV rises modestly.",
            "Useful comparison point for healthy checkout product work.",
        ),
        (
            "PROMO-003",
            "promotion",
            "Mid-season sale",
            timeline.midseason_sale,
            "Returning-customer and VIP sale using GEARUP15.",
            {"promo_codes": ["GEARUP15"], "segments": ["returning", "vip"], "channels": ["email"]},
            "Email revenue and returning-user conversion improve.",
            "Shows segment/channel interactions without an incident.",
        ),
        (
            "INC-002",
            "outage",
            "Image CDN issue",
            timeline.cdn_incident,
            "One-day image CDN issue that hurts web product discovery.",
            {"platforms": ["web_desktop_mac", "web_desktop_windows", "web_mobile"]},
            "Product views and add-to-cart fall, with revenue down 4-8%.",
            "Useful historical context for top-of-funnel drops.",
        ),
        (
            "EXP-003",
            "experiment",
            "checkout_v2 rollout",
            timeline.checkout_v2_rollout,
            "Checkout v2 ramps from a small cohort to most treatment traffic.",
            {"variants": ["checkout_v2_control", "checkout_v2_treatment"], "platforms": PLATFORMS},
            "Treatment initially improves conversion by 3-6% and lowers payment errors.",
            "Central demo experiment; investigate late Android dip.",
        ),
        (
            "PROMO-004",
            "promotion",
            "Frost promo",
            timeline.frost_promo,
            "FROST20 promotion for cold-weather gear and larger baskets.",
            {"promo_codes": ["FROST20"], "categories": ["jackets", "backpacks"], "cart_weight": ["heavy"]},
            "Revenue and conversion improve before the hidden Android bug.",
            "This promo interacts with BUG-1772 in the generated data.",
        ),
        (
            "BUG-1772",
            "bug",
            "Android checkout_v2 promo validation bug",
            timeline.hidden_bug,
            "Generated hidden bug: Android checkout_v2 treatment users with FROST20, 3+ item heavy carts hit promo validation and payment errors.",
            {
                "platform": "android_app",
                "checkout_variant": "checkout_v2_treatment",
                "promo_code": "FROST20",
                "cart_size_bucket": "3_plus_items",
                "cart_weight_bucket": "heavy",
            },
            "Narrow slice conversion drops sharply; global conversion dips only slightly.",
            "Internal data-generation note, not known to the app user unless discovered through breakdowns.",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO business_events (
            id, event_type, name, start_date, end_date, description,
            affected_dimensions_json, expected_impact, demo_hint
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                event_id,
                event_type,
                name,
                event_date(window.start),
                event_date(window.end),
                description,
                json.dumps(dimensions, sort_keys=True),
                expected_impact,
                demo_hint,
            )
            for (
                event_id,
                event_type,
                name,
                window,
                description,
                dimensions,
                expected_impact,
                demo_hint,
            ) in events
        ],
    )

    experiment_rows = [
        (
            "EXP-001",
            "Bigger checkout CTA",
            event_date(timeline.bigger_cta.start),
            event_date(timeline.bigger_cta.end),
            "completed",
            "A larger Continue to Payment button improves mobile checkout progression.",
            json.dumps(
                {
                    "control": "checkout_v2_control",
                    "treatment": "checkout_v2_treatment",
                    "holdout": "classic_checkout",
                },
                sort_keys=True,
            ),
            "Runs around days 35-65 with mobile-weighted exposure.",
            "checkout_conversion",
            "payment_error_rate, promo_error_rate, average_order_value",
        ),
        (
            "EXP-002",
            "Shipping estimator",
            event_date(timeline.shipping_estimator.start),
            event_date(timeline.shipping_estimator.end),
            "completed",
            "Showing shipping estimates earlier reduces checkout abandonment.",
            json.dumps(
                {
                    "control": "checkout_v2_control",
                    "treatment": "checkout_v2_treatment",
                    "holdout": "classic_checkout",
                },
                sort_keys=True,
            ),
            "Runs around days 80-115 with stable exposure.",
            "checkout_conversion",
            "shipping_completion_rate, average_order_value, payment_error_rate",
        ),
        (
            "EXP-003",
            "checkout_v2 rollout",
            event_date(timeline.checkout_v2_rollout.start),
            None,
            "active",
            "New checkout flow improves checkout conversion and reduces payment friction.",
            json.dumps(
                {
                    "control": "checkout_v2_control",
                    "treatment": "checkout_v2_treatment",
                    "legacy": "classic_checkout",
                },
                sort_keys=True,
            ),
            "Starts around day 130 and ramps treatment toward the end of the dataset.",
            "checkout_conversion",
            "payment_error_rate, promo_error_rate, revenue, average_order_value",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO experiments (
            experiment_id, name, start_date, end_date, status, hypothesis,
            variants_json, rollout_notes, success_metric, guardrail_metrics
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        experiment_rows,
    )

    ui_rows = [
        ("sessions", "Browse", "Homepage/category/product pages", "User visits the site or app."),
        (
            "product_views",
            "Product discovery",
            "Product detail page",
            "User views a product page.",
        ),
        (
            "add_to_cart",
            "Product detail",
            "Add to Cart button",
            "User adds an item to cart.",
        ),
        (
            "checkout_started",
            "Cart",
            "Checkout button",
            "User starts checkout from the cart.",
        ),
        (
            "shipping_submitted",
            "Shipping",
            "Shipping form",
            "User submits delivery address and shipping method.",
        ),
        (
            "promo_attempts",
            "Promo",
            "Promo code field",
            "User attempts to apply a promo code.",
        ),
        (
            "promo_success",
            "Promo",
            "Promo code validation",
            "Promo code applies successfully.",
        ),
        ("payment_started", "Payment", "Payment form", "User starts payment."),
        (
            "payment_errors",
            "Payment",
            "Payment form / promo validation / gateway",
            "Payment or validation error occurs.",
        ),
        (
            "purchases",
            "Confirmation",
            "Order confirmation",
            "User completes purchase.",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO ui_metric_mapping (metric_id, ui_step, ui_component, description)
        VALUES (?, ?, ?, ?)
        """,
        ui_rows,
    )

    dashboards = [
        (
            "dash_revenue_overview",
            "org",
            "Revenue Overview",
            "Revenue, sessions, AOV, channel mix, and platform purchase trends.",
            "revenue,overview,org",
            [
                {"title": "Revenue over time", "view": "v_daily_overview", "metric": "revenue_cents"},
                {"title": "Sessions over time", "view": "v_daily_overview", "metric": "sessions"},
                {
                    "title": "Average order value over time",
                    "view": "v_daily_overview",
                    "metric": "average_order_value_cents",
                },
                {
                    "title": "Revenue by channel",
                    "table": "metric_facts_daily",
                    "metric": "revenue_cents",
                    "breakdown": "channel",
                },
                {
                    "title": "Purchases by platform",
                    "table": "metric_facts_daily",
                    "metric": "purchases",
                    "breakdown": "platform",
                },
            ],
        ),
        (
            "dash_checkout_funnel",
            "org",
            "Checkout Funnel",
            "Checkout conversion, payment errors, and promo health across the funnel.",
            "checkout,funnel,org",
            [
                {
                    "title": "Sessions to purchases",
                    "view": "v_daily_overview",
                    "metrics": [
                        "sessions",
                        "product_views",
                        "add_to_cart",
                        "checkout_started",
                        "purchases",
                    ],
                },
                {
                    "title": "Checkout conversion by platform",
                    "view": "v_checkout_by_platform",
                    "metric": "checkout_conversion",
                },
                {
                    "title": "Payment error rate by platform",
                    "view": "v_checkout_by_platform",
                    "metric": "payment_error_rate",
                },
                {
                    "title": "Promo success rate by promo code",
                    "view": "v_promo_performance",
                    "metric": "promo_success_rate",
                },
            ],
        ),
        (
            "dash_campaign_performance",
            "org",
            "Campaign Performance",
            "Channel, conversion, and promo performance for current and historical campaigns.",
            "campaign,promo,org",
            [
                {
                    "title": "Revenue by channel",
                    "table": "metric_facts_daily",
                    "metric": "revenue_cents",
                    "breakdown": "channel",
                },
                {
                    "title": "Sessions by channel",
                    "table": "metric_facts_daily",
                    "metric": "sessions",
                    "breakdown": "channel",
                },
                {
                    "title": "Conversion by channel",
                    "table": "metric_facts_daily",
                    "formula": "SUM(purchases) / SUM(sessions)",
                    "breakdown": "channel",
                },
                {
                    "title": "Promo performance by code",
                    "view": "v_promo_performance",
                    "breakdown": "promo_code",
                },
            ],
        ),
    ]
    connection.executemany(
        """
        INSERT INTO seed_dashboards (id, space, title, description, tags, panels_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (dashboard_id, space, title, description, tags, json.dumps(panels, sort_keys=True))
            for dashboard_id, space, title, description, tags, panels in dashboards
        ],
    )


def create_views(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE VIEW v_daily_overview AS
        SELECT
            date,
            SUM(sessions) AS sessions,
            SUM(product_views) AS product_views,
            SUM(add_to_cart) AS add_to_cart,
            SUM(checkout_started) AS checkout_started,
            SUM(purchases) AS purchases,
            SUM(revenue_cents) AS revenue_cents,
            SUM(payment_errors) AS payment_errors,
            SUM(promo_errors) AS promo_errors,
            CASE WHEN SUM(checkout_started) = 0 THEN 0.0
                 ELSE CAST(SUM(purchases) AS REAL) / SUM(checkout_started) END AS checkout_conversion,
            CASE WHEN SUM(sessions) = 0 THEN 0.0
                 ELSE CAST(SUM(purchases) AS REAL) / SUM(sessions) END AS overall_conversion,
            CASE WHEN SUM(purchases) = 0 THEN 0.0
                 ELSE CAST(SUM(revenue_cents) AS REAL) / SUM(purchases) END AS average_order_value_cents,
            CASE WHEN SUM(payment_started) = 0 THEN 0.0
                 ELSE CAST(SUM(payment_errors) AS REAL) / SUM(payment_started) END AS payment_error_rate
        FROM metric_facts_daily
        GROUP BY date;

        CREATE VIEW v_checkout_by_platform AS
        SELECT
            date,
            platform,
            SUM(checkout_started) AS checkout_started,
            SUM(purchases) AS purchases,
            SUM(payment_errors) AS payment_errors,
            SUM(promo_errors) AS promo_errors,
            SUM(revenue_cents) AS revenue_cents,
            CASE WHEN SUM(checkout_started) = 0 THEN 0.0
                 ELSE CAST(SUM(purchases) AS REAL) / SUM(checkout_started) END AS checkout_conversion,
            CASE WHEN SUM(payment_started) = 0 THEN 0.0
                 ELSE CAST(SUM(payment_errors) AS REAL) / SUM(payment_started) END AS payment_error_rate,
            CASE WHEN SUM(promo_attempts) = 0 THEN 0.0
                 ELSE CAST(SUM(promo_errors) AS REAL) / SUM(promo_attempts) END AS promo_error_rate
        FROM metric_facts_daily
        GROUP BY date, platform;

        CREATE VIEW v_experiment_rollout AS
        SELECT
            date,
            platform,
            checkout_variant,
            SUM(sessions) AS sessions,
            SUM(checkout_started) AS checkout_started,
            SUM(purchases) AS purchases,
            SUM(revenue_cents) AS revenue_cents,
            SUM(payment_errors) AS payment_errors,
            SUM(promo_errors) AS promo_errors,
            CASE WHEN SUM(checkout_started) = 0 THEN 0.0
                 ELSE CAST(SUM(purchases) AS REAL) / SUM(checkout_started) END AS checkout_conversion,
            CASE WHEN SUM(payment_started) = 0 THEN 0.0
                 ELSE CAST(SUM(payment_errors) AS REAL) / SUM(payment_started) END AS payment_error_rate
        FROM metric_facts_daily
        GROUP BY date, platform, checkout_variant;

        CREATE VIEW v_promo_performance AS
        SELECT
            date,
            platform,
            promo_code,
            cart_size_bucket,
            cart_weight_bucket,
            checkout_variant,
            SUM(checkout_started) AS checkout_started,
            SUM(promo_attempts) AS promo_attempts,
            SUM(promo_success) AS promo_success,
            SUM(promo_errors) AS promo_errors,
            SUM(payment_errors) AS payment_errors,
            SUM(purchases) AS purchases,
            SUM(revenue_cents) AS revenue_cents,
            CASE WHEN SUM(checkout_started) = 0 THEN 0.0
                 ELSE CAST(SUM(purchases) AS REAL) / SUM(checkout_started) END AS checkout_conversion,
            CASE WHEN SUM(promo_attempts) = 0 THEN 0.0
                 ELSE CAST(SUM(promo_success) AS REAL) / SUM(promo_attempts) END AS promo_success_rate,
            CASE WHEN SUM(promo_attempts) = 0 THEN 0.0
                 ELSE CAST(SUM(promo_errors) AS REAL) / SUM(promo_attempts) END AS promo_error_rate,
            CASE WHEN SUM(payment_started) = 0 THEN 0.0
                 ELSE CAST(SUM(payment_errors) AS REAL) / SUM(payment_started) END AS payment_error_rate
        FROM metric_facts_daily
        GROUP BY date, platform, promo_code, cart_size_bucket, cart_weight_bucket, checkout_variant;

        CREATE VIEW v_hidden_bug_slice AS
        SELECT *
        FROM v_promo_performance
        WHERE platform = 'android_app'
          AND checkout_variant = 'checkout_v2_treatment'
          AND promo_code = 'FROST20'
          AND cart_size_bucket = '3_plus_items'
          AND cart_weight_bucket = 'heavy';
        """
    )


def weighted_rates(
    connection: sqlite3.Connection,
    table_or_view: str,
    where_clause: str,
    params: tuple[Any, ...],
) -> dict[str, float]:
    row = connection.execute(
        f"""
        SELECT
            SUM(sessions) AS sessions,
            SUM(checkout_started) AS checkout_started,
            SUM(payment_started) AS payment_started,
            SUM(promo_attempts) AS promo_attempts,
            SUM(purchases) AS purchases,
            SUM(payment_errors) AS payment_errors,
            SUM(promo_errors) AS promo_errors,
            SUM(revenue_cents) AS revenue_cents
        FROM {table_or_view}
        WHERE {where_clause}
        """,
        params,
    ).fetchone()
    if row is None:
        raise AssertionError(f"No rows found for {table_or_view} WHERE {where_clause}")
    sessions = row["sessions"] or 0
    checkout_started = row["checkout_started"] or 0
    payment_started = row["payment_started"] or 0
    promo_attempts = row["promo_attempts"] or 0
    purchases = row["purchases"] or 0
    return {
        "sessions": float(sessions),
        "checkout_started": float(checkout_started),
        "checkout_conversion": ratio(purchases, checkout_started),
        "payment_error_rate": ratio(row["payment_errors"] or 0, payment_started),
        "promo_error_rate": ratio(row["promo_errors"] or 0, promo_attempts),
        "overall_conversion": ratio(purchases, sessions),
        "revenue_cents": float(row["revenue_cents"] or 0),
    }


def period_dates(start: date, first_day: int, last_day: int) -> tuple[str, str]:
    return (
        (start + timedelta(days=first_day)).isoformat(),
        (start + timedelta(days=last_day)).isoformat(),
    )


def run_smoke_checks(
    connection: sqlite3.Connection, *, start: date, end: date, total_days: int, timeline: Timeline
) -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    row_count = connection.execute("SELECT COUNT(*) AS count FROM metric_facts_daily").fetchone()[
        "count"
    ]
    if row_count <= 20_000:
        raise AssertionError(f"Expected more than 20,000 fact rows, got {row_count}")

    date_row = connection.execute(
        "SELECT MIN(date) AS min_date, MAX(date) AS max_date FROM metric_facts_daily"
    ).fetchone()
    if date_row["min_date"] != start.isoformat() or date_row["max_date"] != end.isoformat():
        raise AssertionError(
            f"Unexpected date range {date_row['min_date']} to {date_row['max_date']}"
        )

    revenue_row = connection.execute(
        """
        SELECT MIN(revenue_cents) AS min_revenue, MAX(revenue_cents) AS max_revenue
        FROM v_daily_overview
        """
    ).fetchone()
    revenue_spread = ratio(
        revenue_row["max_revenue"] - revenue_row["min_revenue"], revenue_row["min_revenue"]
    )
    if revenue_spread < 0.18:
        raise AssertionError(f"Revenue is too flat; spread was {revenue_spread:.2%}")

    weekend_row = connection.execute(
        """
        SELECT
            AVG(CASE WHEN strftime('%w', date) IN ('0', '6') THEN sessions END) AS weekend_sessions,
            AVG(CASE WHEN strftime('%w', date) NOT IN ('0', '6') THEN sessions END) AS weekday_sessions
        FROM v_daily_overview
        """
    ).fetchone()
    weekend_lift = ratio(weekend_row["weekend_sessions"], weekend_row["weekday_sessions"]) - 1.0
    if weekend_lift < 0.04:
        raise AssertionError(f"Weekend session pattern is too weak; lift was {weekend_lift:.2%}")

    incident_date = (start + timedelta(days=timeline.payment_incident.start)).isoformat()
    incident_row = connection.execute(
        """
        SELECT payment_error_rate
        FROM v_daily_overview
        WHERE date = ?
        """,
        (incident_date,),
    ).fetchone()
    prev_start = max(0, timeline.payment_incident.start - 7)
    prev_end = max(0, timeline.payment_incident.start - 1)
    prev_dates = period_dates(start, prev_start, prev_end)
    baseline_errors = weighted_rates(
        connection, "metric_facts_daily", "date BETWEEN ? AND ?", prev_dates
    )["payment_error_rate"]
    incident_lift = ratio(incident_row["payment_error_rate"], baseline_errors) - 1.0
    if incident_lift < 1.0:
        raise AssertionError(f"Payment incident lift too weak; lift was {incident_lift:.2%}")

    pre_bug_dates = period_dates(
        start, timeline.checkout_v2_rollout.start, max(timeline.hidden_bug.start - 1, 0)
    )
    treatment_pre = weighted_rates(
        connection,
        "metric_facts_daily",
        "date BETWEEN ? AND ? AND checkout_variant = 'checkout_v2_treatment'",
        pre_bug_dates,
    )["checkout_conversion"]
    control_pre = weighted_rates(
        connection,
        "metric_facts_daily",
        "date BETWEEN ? AND ? AND checkout_variant = 'checkout_v2_control'",
        pre_bug_dates,
    )["checkout_conversion"]
    treatment_lift = ratio(treatment_pre, control_pre) - 1.0
    if treatment_lift < 0.025:
        raise AssertionError(
            f"checkout_v2 treatment should be healthier before bug; lift was {treatment_lift:.2%}"
        )

    hidden_prior_dates = period_dates(
        start, max(timeline.hidden_bug.start - 9, 0), max(timeline.hidden_bug.start - 1, 0)
    )
    hidden_bug_dates = period_dates(start, timeline.hidden_bug.start, timeline.hidden_bug.end)
    hidden_where = """
        date BETWEEN ? AND ?
        AND platform = 'android_app'
        AND checkout_variant = 'checkout_v2_treatment'
        AND promo_code = 'FROST20'
        AND cart_size_bucket = '3_plus_items'
        AND cart_weight_bucket = 'heavy'
    """
    hidden_prior = weighted_rates(connection, "metric_facts_daily", hidden_where, hidden_prior_dates)
    hidden_bug = weighted_rates(connection, "metric_facts_daily", hidden_where, hidden_bug_dates)
    hidden_conversion_drop = 1.0 - ratio(
        hidden_bug["checkout_conversion"], hidden_prior["checkout_conversion"]
    )
    hidden_promo_error_lift = ratio(
        hidden_bug["promo_error_rate"], hidden_prior["promo_error_rate"]
    ) - 1.0
    hidden_payment_error_lift = ratio(
        hidden_bug["payment_error_rate"], hidden_prior["payment_error_rate"]
    ) - 1.0
    if hidden_conversion_drop < 0.40:
        raise AssertionError(
            f"Hidden bug conversion drop too weak; drop was {hidden_conversion_drop:.2%}"
        )
    if hidden_promo_error_lift < 2.0:
        raise AssertionError(
            f"Hidden bug promo error lift too weak; lift was {hidden_promo_error_lift:.2%}"
        )
    if hidden_payment_error_lift < 1.0:
        raise AssertionError(
            f"Hidden bug payment error lift too weak; lift was {hidden_payment_error_lift:.2%}"
        )

    global_prior_dates = period_dates(
        start, max(total_days - 14, 0), max(total_days - 8, 0)
    )
    global_last_dates = period_dates(start, max(total_days - 7, 0), total_days - 1)
    global_prior = weighted_rates(connection, "metric_facts_daily", "date BETWEEN ? AND ?", global_prior_dates)
    global_last = weighted_rates(connection, "metric_facts_daily", "date BETWEEN ? AND ?", global_last_dates)
    global_conversion_dip = 1.0 - ratio(
        global_last["checkout_conversion"], global_prior["checkout_conversion"]
    )
    if not 0.01 <= global_conversion_dip <= 0.05:
        raise AssertionError(
            "Global checkout conversion dip should be subtle; "
            f"dip was {global_conversion_dip:.2%}"
        )

    android_where = """
        date BETWEEN ? AND ?
        AND platform = 'android_app'
        AND checkout_variant = 'checkout_v2_treatment'
    """
    android_prior = weighted_rates(connection, "metric_facts_daily", android_where, global_prior_dates)
    android_last = weighted_rates(connection, "metric_facts_daily", android_where, global_last_dates)
    android_treatment_dip = 1.0 - ratio(
        android_last["checkout_conversion"], android_prior["checkout_conversion"]
    )
    if android_treatment_dip < 0.07:
        raise AssertionError(
            f"Android checkout_v2 treatment dip too weak; dip was {android_treatment_dip:.2%}"
        )

    ios_where = """
        date BETWEEN ? AND ?
        AND platform = 'ios_app'
        AND checkout_variant = 'checkout_v2_treatment'
    """
    ios_prior = weighted_rates(connection, "metric_facts_daily", ios_where, global_prior_dates)
    ios_last = weighted_rates(connection, "metric_facts_daily", ios_where, global_last_dates)
    ios_treatment_change = 1.0 - ratio(
        ios_last["checkout_conversion"], ios_prior["checkout_conversion"]
    )
    if abs(ios_treatment_change) > 0.05:
        raise AssertionError(
            f"iOS checkout_v2 treatment should be mostly stable; change was {ios_treatment_change:.2%}"
        )

    return {
        "row_count": row_count,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "revenue_spread": revenue_spread,
        "weekend_session_lift": weekend_lift,
        "payment_incident_error_lift": incident_lift,
        "checkout_v2_pre_bug_treatment_lift": treatment_lift,
        "hidden_bug_checkout_conversion_drop": hidden_conversion_drop,
        "hidden_bug_promo_error_lift": hidden_promo_error_lift,
        "hidden_bug_payment_error_lift": hidden_payment_error_lift,
        "global_checkout_conversion_dip": global_conversion_dip,
        "android_checkout_v2_treatment_dip": android_treatment_dip,
        "ios_checkout_v2_treatment_change": ios_treatment_change,
    }


def generate_database(
    out_path: Path,
    *,
    days: int,
    seed: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    start, end, total_days = resolve_date_range(days=days, start_date=start_date, end_date=end_date)
    timeline = build_timeline(total_days)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    rows = generate_fact_rows(start=start, total_days=total_days, seed=seed, timeline=timeline)
    with sqlite3.connect(out_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        create_schema(connection)
        insert_metadata(connection, start, timeline)
        placeholders = ", ".join("?" for _ in FACT_COLUMNS)
        connection.executemany(
            f"""
            INSERT INTO metric_facts_daily ({", ".join(FACT_COLUMNS)})
            VALUES ({placeholders})
            """,
            rows,
        )
        create_views(connection)
        summary = run_smoke_checks(
            connection, start=start, end=end, total_days=total_days, timeline=timeline
        )
        summary["out_path"] = str(out_path)
        summary["seed"] = seed
        summary["days"] = total_days
        if total_days < 120:
            summary["event_schedule_note"] = "Event windows were scaled because --days is below 120."
        return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the ChartDex demo metrics SQLite database.")
    parser.add_argument("--days", type=int, default=180, help="Number of inclusive days to generate.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic output.")
    parser.add_argument("--start-date", type=parse_iso_date, help="Optional YYYY-MM-DD start date.")
    parser.add_argument("--end-date", type=parse_iso_date, help="Optional YYYY-MM-DD end date.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/chartdex_demo.sqlite"),
        help="Output SQLite database path.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = generate_database(
        args.out,
        days=args.days,
        seed=args.seed,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(f"Generated ChartDex demo metrics database: {summary['out_path']}")
    print(f"Seed: {summary['seed']}")
    print(f"Date range: {summary['start_date']} to {summary['end_date']} ({summary['days']} days)")
    print(f"Fact rows: {summary['row_count']:,}")
    print(f"Revenue spread: {summary['revenue_spread']:.1%}")
    print(f"Weekend session lift: {summary['weekend_session_lift']:.1%}")
    print(f"Payment incident error lift: {summary['payment_incident_error_lift']:.1%}")
    print(
        "checkout_v2 treatment lift before hidden bug: "
        f"{summary['checkout_v2_pre_bug_treatment_lift']:.1%}"
    )
    print(
        "Hidden bug slice checkout conversion drop: "
        f"{summary['hidden_bug_checkout_conversion_drop']:.1%}"
    )
    print(f"Hidden bug promo error lift: {summary['hidden_bug_promo_error_lift']:.1%}")
    print(f"Hidden bug payment error lift: {summary['hidden_bug_payment_error_lift']:.1%}")
    print(f"Global checkout conversion dip: {summary['global_checkout_conversion_dip']:.1%}")
    print(
        "Android checkout_v2 treatment dip: "
        f"{summary['android_checkout_v2_treatment_dip']:.1%}"
    )
    print(
        "iOS checkout_v2 treatment change: "
        f"{summary['ios_checkout_v2_treatment_change']:.1%}"
    )
    if "event_schedule_note" in summary:
        print(summary["event_schedule_note"])
    print("Smoke checks passed.")


if __name__ == "__main__":
    main()
