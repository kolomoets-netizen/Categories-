#!/usr/bin/env python3
"""
Remove cross-category duplicates from user_requests_training.json.
Keeps all category keys unchanged; each product name appears in exactly one category.
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict, defaultdict

from rapidfuzz import fuzz

from merge_training_dataset import (
    build_slug_to_ru,
    category_tokens,
    normalize_item,
    parse_category_key,
    rule_match_text,
)

INPUT_PATH = "/workspace/user_requests_training.json"
OUTPUT_PATH = "/workspace/user_requests_training.json"
STATS_PATH = "/workspace/training_dedupe_stats.json"

# (patterns in item text, preferred user category name)
ITEM_CATEGORY_HINTS: list[tuple[list[str], str]] = [
    (["канат", "кабел", "провод", "проволок", "hdmi", "usb"], "Провода и кабели"),
    (["болт", "винт", "гайк", "шайб", "шпильк", "штифт", "заклеп", "крепеж"], "Крепежные изделия"),
    (["труб", "фланц", "задвиж", "клапан", "арматур", "отвод", "муфт"], "Трубопроводная арматура, детали трубопроводов"),
    (["станок", "фрез", "сверл", "резц", "токарн"], "Станки, их детали и принадлежности"),
    (["подшипник", "втулк", "пружин", "шестерн", "вал ", "валы"], "Детали и узлы машин и механизмов"),
    (["испытательн"], "Испытательное оборудование"),
    (["утеплит", "изоляц"], "Утеплители"),
    (["свароч", "электрод"], "Сварочное оборудование"),
    (["насос", "компрессор"], "Компрессоры, насосное и водонапорное оборудование"),
    (["манометр", "термометр", "датчик", "измерител"], "Контрольно-измерительные приборы (КИП)"),
]


def norm_key(text: str) -> str:
    return normalize_item(text).lower()


def score_category(item: str, cat_name: str, slug_to_ru: dict[str, str]) -> float:
    item_l = item.lower()
    cat_l = cat_name.lower()
    score = 0.0

    if item_l == cat_l:
        score += 250
    elif cat_l in item_l:
        score += 120
    elif item_l in cat_l:
        score += 90

    score += fuzz.token_set_ratio(item, cat_name) * 0.9

    item_tokens = category_tokens(item)
    cat_tokens = category_tokens(cat_name)
    if item_tokens and cat_tokens:
        overlap = len(item_tokens & cat_tokens)
        score += overlap / max(len(item_tokens), len(cat_tokens)) * 70

    rule_cat = rule_match_text(item, slug_to_ru)
    if rule_cat == cat_name:
        score += 110

    item_l_spaced = f" {item_l} "
    for patterns, preferred in ITEM_CATEGORY_HINTS:
        if preferred == cat_name and any(p in item_l_spaced or item_l.startswith(p) or item_l.endswith(p) for p in patterns):
            score += 130

    # Prefer shorter, more specific category names when scores tie
    score -= len(cat_name) * 0.01
    return score


def dedupe_cross_category(data: OrderedDict) -> tuple[OrderedDict, dict]:
    slug_to_ru = build_slug_to_ru()

    # norm_key -> list of (cat_key, cat_name, item_text)
    occurrences: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for cat_key, items in data.items():
        _, cat_name = parse_category_key(cat_key)
        for item in items:
            nk = norm_key(item)
            if nk:
                occurrences[nk].append((cat_key, cat_name, item))

    # Decide winning category for each duplicated item
    winner: dict[str, tuple[str, str]] = {}  # norm_key -> (cat_key, item_text)
    cross_removed = 0
    reassignment_samples: list[dict] = []

    for nk, occs in occurrences.items():
        unique_cats = {o[0] for o in occs}
        if len(unique_cats) == 1:
            winner[nk] = (occs[0][0], occs[0][2])
            continue

        best_cat_key = None
        best_item = occs[0][2]
        best_score = -1.0
        for cat_key, cat_name, item in occs:
            s = score_category(item, cat_name, slug_to_ru)
            if s > best_score:
                best_score = s
                best_cat_key = cat_key
                best_item = item

        winner[nk] = (best_cat_key, best_item)
        cross_removed += len(occs) - 1

        if len(reassignment_samples) < 20:
            reassignment_samples.append({
                "item": best_item,
                "kept_in": parse_category_key(best_cat_key)[1],
                "removed_from": [
                    parse_category_key(o[0])[1]
                    for o in occs
                    if o[0] != best_cat_key
                ][:5],
                "score": round(best_score, 1),
            })

    # Rebuild per category
    output: OrderedDict = OrderedDict()
    within_removed = 0

    for cat_key in data:
        seen_norm: set[str] = set()
        merged: list[str] = []

        for item in data[cat_key]:
            nk = norm_key(item)
            if not nk:
                continue
            if winner.get(nk, (cat_key, item))[0] != cat_key:
                continue
            if nk in seen_norm:
                within_removed += 1
                continue

            canonical = winner[nk][1]
            seen_norm.add(nk)
            merged.append(canonical)

        output[cat_key] = merged

    stats = {
        "categories": len(output),
        "items_before": sum(len(v) for v in data.values()),
        "items_after": sum(len(v) for v in output.values()),
        "cross_category_removed": cross_removed,
        "within_category_removed": within_removed,
        "unique_items_global": len(winner),
        "categories_unchanged": list(data.keys()) == list(output.keys()),
        "reassignment_samples": reassignment_samples,
        "smallest_categories": sorted(
            [{"category": parse_category_key(k)[1], "count": len(v)} for k, v in output.items()],
            key=lambda x: x["count"],
        )[:10],
    }
    return output, stats


def main() -> None:
    with open(INPUT_PATH, encoding="utf-8") as f:
        data = json.loads(f.read(), object_pairs_hook=OrderedDict)

    print(f"Input: {sum(len(v) for v in data.values())} items in {len(data)} categories")
    output, stats = dedupe_cross_category(data)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"Output: {stats['items_after']} items ({stats['cross_category_removed']} cross-cat removed)")
    print(f"Unique items: {stats['unique_items_global']}")
    print(f"Categories unchanged: {stats['categories_unchanged']}")


if __name__ == "__main__":
    main()
