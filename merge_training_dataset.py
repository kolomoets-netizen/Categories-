#!/usr/bin/env python3
"""
Merge user_requests_filled.json with keywords from keywords_by_category.json
into an exhaustive training dataset for product category classification.
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict, defaultdict

from rapidfuzz import fuzz, process

from map_categories import RULES, normalize, parse_user_categories

INPUT_PATH = "/workspace/user_requests_filled.json"
KEYWORDS_PATH = "/workspace/keywords_by_category.json"
MAPPING_PATH = "/workspace/category_mapping_detailed.json"
USER_CATS_PATH = "/home/ubuntu/.cursor/projects/workspace/uploads/___________1__8b75.txt"
OUTPUT_PATH = "/workspace/user_requests_training.json"
STATS_PATH = "/workspace/training_merge_stats.json"

# Extra rules for catalog categories not covered by the original mapping
EXTRA_RULES: list[tuple[list[str], str]] = [
    (["болтокомплект", "болт", "гайк", "винт", "шайб", "шпильк", "штифт", "заклеп",
      "анкер", "хомут", "шуруп", "гвозд", "шплинт", "булавк", "шпонк"], "fastener_products"),
    (["амортизатор", "cardan", "shaft", "вал", "ось", "вариатор", "муфт"], "machine_parts_and_units"),
    (["motor", "двигател", "турбин"], "electric_motors_generators_transformers"),
    (["вольтметр", "амперметр", "омметр", "манометр", "термометр", "датчик", "измерител"], "control_and_measuring_devices"),
    (["бур", "сверл", "фрез", "резц", "метчик"], "instruments"),
    (["балк", "бандаж", "обечайк", "бобышк"], "metal_rolling"),
    (["бирк", "маркиров"], "paper_containers_packaging"),
    (["бумаг"], "paper_containers_packaging"),
    (["клемм", "аксессуар"], "electricity_distribution_and_control_equipment"),
    (["печатн", "плат"], "electronic_components"),
    (["приварк", "сварочн"], "welding_equipment"),
    (["аспирац", "вентиляц"], "ventilation"),
    (["пресс"], "machines_their_parts_and_accessories"),
    (["воротк", "ключ"], "instruments"),
    (["helicopter", "авиа"], "machinery_and_equipment_their_components_and_spare_parts_(excluding_other_groups)"),
    (["фильтр", "сетчат"], "valves_pipeline_components"),
    (["плавк", "предохранител", "держатель предохранител"], "electricity_distribution_and_control_equipment"),
    (["гильз", "кабел"], "wires_and_cables"),
    (["горелк", "амбразур"], "welding_equipment"),
    (["древесноволокнист", "плит"], "building_materials"),
    (["подогревател", "пароводян"], "heat_exchangers"),
    (["домкрат", "зубил", "воротк", "ключ"], "instruments"),
    (["замок", "замки", "цепочк", "звено"], "machine_parts_and_units"),
    (["жесть"], "metal_rolling"),
    (["handwheel", "hand wheel"], "machine_parts_and_units"),
    (["монтажн", "колодк"], "electricity_distribution_and_control_equipment"),
    (["цепочк", "коуш", "ушк"], "machine_parts_and_units"),
    (["катанк"], "metal_rolling"),
    (["зенкер", "разверт", "клинь", "насадн"], "machines_their_parts_and_accessories"),
    (["кнопк", "контакт", "коммутацион"], "electricity_distribution_and_control_equipment"),
    (["колпач", "резинов"], "machine_parts_and_units"),
    (["кондуктор"], "instruments"),
    (["люк", "сосуд", "аппарат"], "heat_exchangers"),
    (["магнитопровод"], "electric_motors_generators_transformers"),
    (["напильник", "надфил", "рашпил"], "instruments"),
    (["нож", "ножи"], "machines_their_parts_and_accessories"),
    (["станок", "пилорам", "плоттер", "плашк", "головк", "расточ"], "machines_their_parts_and_accessories"),
    (["бревнотаск", "эстакад", "стол для"], "machinery_and_equipment_their_components_and_spare_parts_(excluding_other_groups)"),
    (["перемычк", "металлизац"], "wires_and_cables"),
    (["полособульб"], "metal_rolling"),
    (["балансиров"], "machine_parts_and_units"),
    (["бородк"], "instruments"),
    (["пылеулавлив"], "ventilation"),
    (["адаптер", "вилк", "розетк", "разъем", "расцепител", "соединител"], "electricity_distribution_and_control_equipment"),
    (["ремн", "приводн", "клинов"], "hoses_conveyor_belts_belts_rubberized_fabric_ebonite"),
    (["лепестк", "штырьк"], "machine_parts_and_units"),
    (["рукоятк", "handle"], "machine_parts_and_units"),
    (["сканер"], "electronic_components"),
    (["стеклорез"], "instruments"),
    (["такелаж", "ролик"], "machine_parts_and_units"),
    (["подвеск", "траверс", "трубопровод"], "valves_pipeline_components"),
    (["трубк", "термоусаж"], "wires_and_cables"),
    (["тумблер", "штеккер"], "electricity_distribution_and_control_equipment"),
    (["тяга", "шарнир"], "machine_parts_and_units"),
    (["фанер"], "building_materials"),
    (["форматно-раскроеч", "раскроеч"], "machines_their_parts_and_accessories"),
    (["цанг"], "machines_their_parts_and_accessories"),
    (["цапф"], "machine_parts_and_units"),
    (["цеп", "тягов"], "machine_parts_and_units"),
    (["шнур", "асбест"], "insulation"),
]


def parse_category_key(key: str) -> tuple[int, str]:
    m = re.match(r"^(\d+)\((.+)\)$", key)
    return (int(m.group(1)), m.group(2)) if m else (0, key)


def normalize_item(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def category_tokens(text: str) -> set[str]:
    stop = {
        "прочие", "прочее", "для", "из", "по", "на", "в", "с", "их", "не", "или",
        "а", "также", "включенные", "другие", "группировки", "проч", "the", "and",
        "of", "for", "accessories",
    }
    return {
        t for t in re.findall(r"[а-яёa-z0-9\-]+", text.lower())
        if len(t) > 2 and t not in stop
    }


def build_slug_to_ru() -> dict[str, str]:
    return {c["slug"]: c["ru"] for c in parse_user_categories(USER_CATS_PATH)}


def build_name_to_key(data: OrderedDict) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in data:
        _, name = parse_category_key(key)
        result[name] = key
    return result


def resolve_user_category_name(
    user_name: str,
    name_to_key: dict[str, str],
) -> str | None:
    if user_name in name_to_key:
        return user_name
    choices = {i: n for i, n in enumerate(name_to_key)}
    result = process.extractOne(user_name, choices, scorer=fuzz.token_set_ratio)
    if result and result[1] >= 70:
        return choices[result[2]]
    return None


def rule_match_text(text: str, slug_to_ru: dict[str, str]) -> str | None:
    norm = normalize(text)
    best_slug = None
    best_len = 0
    for patterns, slug in [*RULES, *EXTRA_RULES]:
        if slug not in slug_to_ru:
            continue
        for pattern in patterns:
            if pattern in norm and len(pattern) > best_len:
                best_len = len(pattern)
                best_slug = slug
    return slug_to_ru.get(best_slug) if best_slug else None


def rule_match_orig(orig_name: str, slug_to_ru: dict[str, str]) -> str | None:
    return rule_match_text(orig_name, slug_to_ru)


def token_match_orig(orig_name: str, user_names: list[str]) -> str | None:
    orig_tokens = category_tokens(orig_name)
    if not orig_tokens:
        return None
    best_name = None
    best_score = 0.0
    for name in user_names:
        name_tokens = category_tokens(name)
        if not name_tokens:
            continue
        overlap = len(orig_tokens & name_tokens)
        if overlap == 0:
            continue
        score = overlap / max(len(orig_tokens), len(name_tokens)) * 100
        if orig_name.lower() in name.lower() or name.lower() in orig_name.lower():
            score += 20
        if score > best_score:
            best_score = score
            best_name = name
    return best_name if best_score >= 25 else None


def fuzzy_match_orig(orig_name: str, user_names: list[str], threshold: float = 55) -> str | None:
    if not user_names:
        return None
    choices = {i: n for i, n in enumerate(user_names)}
    result = process.extractOne(orig_name, choices, scorer=fuzz.token_set_ratio)
    if result and result[1] >= threshold:
        return choices[result[2]]
    return None


def fuzzy_match_keyword(keyword: str, user_names: list[str], threshold: float = 62) -> str | None:
    choices = {i: n for i, n in enumerate(user_names)}
    result = process.extractOne(keyword, choices, scorer=fuzz.partial_ratio)
    if result and result[1] >= threshold:
        return choices[result[2]]
    return None


def build_orig_to_user_name(
    keywords_by_cat: dict[str, list[str]],
    orig_mapped: dict[str, str],
    slug_to_ru: dict[str, str],
    user_names: list[str],
) -> tuple[dict[str, str], dict[str, int]]:
    """Map each original catalog category to a user category Russian name."""
    result: dict[str, str] = {}
    methods: dict[str, int] = defaultdict(int)

    for orig in keywords_by_cat:
        if orig in orig_mapped:
            resolved = resolve_user_category_name(orig_mapped[orig], {n: n for n in user_names})
            if resolved:
                result[orig] = resolved
                methods["detailed_mapping"] += 1
                continue

        matched = rule_match_orig(orig, slug_to_ru)
        if matched and matched in user_names:
            result[orig] = matched
            methods["rule"] += 1
            continue

        matched = fuzzy_match_orig(orig, user_names, threshold=55)
        if matched:
            result[orig] = matched
            methods["fuzzy_orig"] += 1
            continue

        matched = token_match_orig(orig, user_names)
        if matched:
            result[orig] = matched
            methods["token_orig"] += 1
            continue

        methods["unmapped_orig"] += 1

    return result, methods


def merge_keywords(
    base: OrderedDict,
    keywords_by_cat: dict[str, list[str]],
    orig_to_user: dict[str, str],
    user_names: list[str],
    slug_to_ru: dict[str, str],
) -> tuple[OrderedDict, dict]:
    output: OrderedDict = OrderedDict()
    for key, items in base.items():
        seen = {normalize_item(x).lower() for x in items if normalize_item(x)}
        merged = list(items)
        output[key] = merged

    additions_by_key: dict[str, list[str]] = defaultdict(list)
    keyword_methods: dict[str, int] = defaultdict(int)
    unmapped_keywords: list[str] = []

    for orig, keywords in keywords_by_cat.items():
        user_name = orig_to_user.get(orig)
        method = "category_map"

        if not user_name:
            for kw in keywords:
                user_name = rule_match_text(kw, slug_to_ru)
                if user_name and user_name in user_names:
                    additions_by_key[user_name].append(kw)
                    keyword_methods["rule_keyword"] += 1
                    continue
                user_name = fuzzy_match_keyword(kw, user_names)
                if user_name:
                    additions_by_key[user_name].append(kw)
                    keyword_methods["fuzzy_keyword"] += 1
                else:
                    unmapped_keywords.append(kw)
                    keyword_methods["unmapped_keyword"] += 1
            continue

        for kw in keywords:
            additions_by_key[user_name].append(kw)
            keyword_methods[method] += 1

    total_added = 0
    for user_name, new_items in additions_by_key.items():
        key = base_name_to_key.get(user_name)
        if not key:
            continue
        seen = {normalize_item(x).lower() for x in output[key]}
        for item in new_items:
            normalized = normalize_item(item)
            if not normalized:
                continue
            key_lower = normalized.lower()
            if key_lower in seen:
                continue
            seen.add(key_lower)
            output[key].append(normalized)
            total_added += 1

    stats = {
        "base_categories": len(base),
        "base_items": sum(len(v) for v in base.values()),
        "catalog_categories": len(keywords_by_cat),
        "catalog_keywords": sum(len(v) for v in keywords_by_cat.values()),
        "keywords_added": total_added,
        "output_items": sum(len(v) for v in output.values()),
        "unmapped_keywords": len(unmapped_keywords),
        "keyword_methods": dict(keyword_methods),
        "categories_with_additions": sum(
            1 for k, v in output.items() if len(v) > len(base.get(k, []))
        ),
        "top_growth": sorted(
            [
                {
                    "category": parse_category_key(k)[1],
                    "before": len(base.get(k, [])),
                    "after": len(v),
                    "added": len(v) - len(base.get(k, [])),
                }
                for k, v in output.items()
                if len(v) > len(base.get(k, []))
            ],
            key=lambda x: -x["added"],
        )[:15],
    }
    if unmapped_keywords:
        stats["unmapped_keyword_samples"] = unmapped_keywords[:30]

    return output, stats


def main() -> None:
    global base_name_to_key

    print("Loading data...")
    with open(INPUT_PATH, encoding="utf-8") as f:
        base = json.loads(f.read(), object_pairs_hook=OrderedDict)
    with open(KEYWORDS_PATH, encoding="utf-8") as f:
        keywords_by_cat = json.load(f)
    with open(MAPPING_PATH, encoding="utf-8") as f:
        mapping = json.load(f)

    base_name_to_key = build_name_to_key(base)
    user_names = list(base_name_to_key.keys())
    slug_to_ru = build_slug_to_ru()
    orig_mapped = {row["original"]: row["user_category"] for row in mapping}

    print("Building category mapping...")
    orig_to_user, orig_methods = build_orig_to_user_name(
        keywords_by_cat, orig_mapped, slug_to_ru, user_names
    )
    print("Orig mapping methods:", dict(orig_methods))

    print("Merging keywords...")
    output, stats = merge_keywords(base, keywords_by_cat, orig_to_user, user_names, slug_to_ru)
    stats["orig_mapping_methods"] = dict(orig_methods)
    stats["mapped_orig_categories"] = len(orig_to_user)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\nOutput: {OUTPUT_PATH}")
    print(f"Base items: {stats['base_items']}")
    print(f"Added keywords: {stats['keywords_added']}")
    print(f"Total items: {stats['output_items']}")
    print(f"Unmapped keywords: {stats['unmapped_keywords']}")
    print(f"Categories with additions: {stats['categories_with_additions']}")


if __name__ == "__main__":
    main()
