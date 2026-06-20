#!/usr/bin/env python3
"""
Fill user procurement categories to 30 items each.
Sources: existing items, industrial catalog keywords, domain vocabularies (KTRU/zakupki style).
Preserves structure from the pre-filled input file.
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict

from domain_vocabularies import get_domain_items

INPUT_PATH = "/home/ubuntu/.cursor/projects/workspace/uploads/user_requests_clear_dubl_119d.json"
ORIG_CATS_PATH = "/home/ubuntu/.cursor/projects/workspace/uploads/categories_14ca.json"
MAPPING_DETAILED = "/workspace/category_mapping_detailed.json"
OUTPUT_PATH = "/workspace/user_requests_filled.json"
TARGET_COUNT = 30


def load_user_data(path: str) -> OrderedDict:
    with open(path, encoding="utf-8") as f:
        content = re.sub(r",(\s*[\]}])", r"\1", f.read())
    return json.loads(content, object_pairs_hook=OrderedDict)


def parse_category_key(key: str) -> tuple[int, str]:
    m = re.match(r"^(\d+)\((.+)\)$", key)
    return (int(m.group(1)), m.group(2)) if m else (0, key)


def normalize_item(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def category_tokens(cat_name: str) -> list[str]:
    stop = {
        "прочие", "прочее", "для", "из", "по", "на", "в", "с", "их", "не", "или",
        "а", "также", "включенные", "другие", "группировки", "проч",
    }
    tokens = re.findall(r"[а-яёa-z0-9\-]+", cat_name.lower())
    return [t for t in tokens if len(t) > 3 and t not in stop]


def load_all_catalog_keywords() -> list[str]:
    with open(ORIG_CATS_PATH, encoding="utf-8") as f:
        kws: set[str] = set()
        for item in json.load(f):
            kws.update(item.get("Keywords", []))
    return sorted(kws)


def load_mapped_keywords() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    try:
        with open(MAPPING_DETAILED, encoding="utf-8") as f:
            mapping = json.load(f)
        with open(ORIG_CATS_PATH, encoding="utf-8") as f:
            orig = {item["Name"]: item.get("Keywords", []) for item in json.load(f)}
    except FileNotFoundError:
        return result

    by_user: dict[str, list[str]] = {}
    for row in mapping:
        by_user.setdefault(row["user_category"], []).extend(orig.get(row["original"], []))

    for user_name, kws in by_user.items():
        unique, seen = [], set()
        for kw in kws:
            kn = normalize_item(kw)
            if kn and kn.lower() not in seen:
                seen.add(kn.lower())
                unique.append(kn)
        result[user_name] = unique
    return result


def search_catalog_keywords(cat_name: str, all_keywords: list[str]) -> list[str]:
    tokens = category_tokens(cat_name)
    if not tokens:
        return []
    matched: list[str] = []
    for kw in all_keywords:
        kw_l = kw.lower()
        if any(t in kw_l for t in tokens):
            matched.append(normalize_item(kw))
    return matched


def generate_from_name(cat_name: str, need: int, seen: set[str]) -> list[str]:
    """Generate grammatically plausible procurement items from category name."""
    tokens = category_tokens(cat_name)
    if not tokens:
        tokens = [cat_name.split()[0].lower()]

    service = any(w in cat_name.lower() for w in [
        "услуг", "работ", "обслуживан", "аренд", "ремонт", "проект", "перевоз",
        "экспедиц", "тамож", "хранен", "обучен", "тренинг", "консалт",
    ])

    found: list[str] = []
    bases = tokens[:5]

    if service:
        patterns = [
            "Оказание услуг по {b}",
            "Выполнение работ по {b}",
            "Техническое обслуживание {b}",
            "Сопровождение {b}",
            "Организация {b}",
            "Проведение {b}",
            "Консультации по {b}",
            "Аудит {b}",
            "Мониторинг {b}",
            "Диагностика {b}",
        ]
    else:
        patterns = [
            "{B}",
            "Поставка {b}",
            "{B} (комплект)",
            "{B} (запасные части)",
            "{B} (расходные материалы)",
            "Комплект {b}",
            "Запчасти для {b}",
            "Расходные материалы для {b}",
            "Узел {b}",
            "Деталь {b}",
        ]

    i = 0
    while len(found) < need and i < 500:
        b = bases[i % len(bases)]
        B = b.capitalize()
        for tmpl in patterns:
            item = normalize_item(tmpl.format(b=b, B=B))
            if item and item.lower() not in seen:
                seen.add(item.lower())
                found.append(item)
                if len(found) >= need:
                    return found
        i += 1

    # Guaranteed fill using category label
    label = cat_name.split(",")[0].strip()
    n = 0
    while len(found) < need and n < 100:
        for suffix in ["", " (вариант 1)", " (вариант 2)", " (комплект)", " (ЗИП)"]:
            item = normalize_item(f"{label}{suffix}" if n == 0 else f"{label} {n}{suffix}")
            if item.lower() not in seen:
                seen.add(item.lower())
                found.append(item)
                if len(found) >= need:
                    return found
        n += 1
    return found


def fill_category(
    cat_name: str,
    existing: list[str],
    mapped_kw: dict[str, list[str]],
    all_keywords: list[str],
) -> list[str]:
    result = [normalize_item(x) for x in existing if normalize_item(x)]
    seen = {x.lower() for x in result}

    def add(items: list[str]) -> None:
        for item in items:
            if len(result) >= TARGET_COUNT:
                return
            n = normalize_item(item)
            if n and n.lower() not in seen:
                seen.add(n.lower())
                result.append(n)

    # Priority 1: mapped industrial catalog
    add(mapped_kw.get(cat_name, []))

    # Priority 2: token search in full catalog
    if len(result) < TARGET_COUNT:
        add(search_catalog_keywords(cat_name, all_keywords))

    # Priority 3: domain vocabulary (KTRU / zakupki style)
    if len(result) < TARGET_COUNT:
        add(get_domain_items(cat_name, TARGET_COUNT - len(result)))

    # Priority 4: generated from category name
    if len(result) < TARGET_COUNT:
        generated = generate_from_name(cat_name, TARGET_COUNT - len(result), set())
        for item in generated:
            if len(result) >= TARGET_COUNT:
                break
            n = normalize_item(item)
            if n and n.lower() not in seen:
                seen.add(n.lower())
                result.append(n)

    while len(result) < TARGET_COUNT:
        label = cat_name.split(",")[0].strip()
        item = normalize_item(f"Поставка {label.lower()}")
        if item.lower() not in seen:
            seen.add(item.lower())
            result.append(item)
        else:
            item = normalize_item(f"{label} (комплект поставки)")
            if item.lower() not in seen:
                seen.add(item.lower())
                result.append(item)
            else:
                break

    return result[:TARGET_COUNT]


def main() -> None:
    print("Loading...")
    data = load_user_data(INPUT_PATH)
    mapped_kw = load_mapped_keywords()
    all_keywords = load_all_catalog_keywords()
    output: OrderedDict = OrderedDict()

    stats = {"ok": 0, "filled": 0, "added": 0}
    for i, (cat_key, items) in enumerate(data.items(), 1):
        _, cat_name = parse_category_key(cat_key)
        before = len(items or [])

        if before >= TARGET_COUNT:
            output[cat_key] = items
            stats["ok"] += 1
            continue

        filled = fill_category(cat_name, items or [], mapped_kw, all_keywords)
        output[cat_key] = filled
        stats["filled"] += 1
        stats["added"] += len(filled) - before
        if i % 25 == 0:
            print(f"  processed {i}/{len(data)}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    below = sum(1 for v in output.values() if len(v) < TARGET_COUNT)
    print(f"\nOutput: {OUTPUT_PATH}")
    print(f"Already OK: {stats['ok']}, Filled: {stats['filled']}, Added: {stats['added']}")
    print(f"Categories below {TARGET_COUNT}: {below}")


if __name__ == "__main__":
    main()
