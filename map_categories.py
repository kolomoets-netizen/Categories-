#!/usr/bin/env python3
"""Map original product categories to user's high-level category taxonomy."""

import json
import re
from collections import defaultdict

from rapidfuzz import fuzz, process

USER_CATS_PATH = "/home/ubuntu/.cursor/projects/workspace/uploads/___________1__8b75.txt"
ORIG_CATS_PATH = "/home/ubuntu/.cursor/projects/workspace/uploads/categories_14ca.json"
OUTPUT_MAPPING = "/workspace/category_mapping.json"
OUTPUT_UNMATCHED = "/workspace/unmatched_categories.json"

# (patterns in original category name, user category slug)
RULES: list[tuple[list[str], str]] = [
    # Fasteners
    (["винты", "болты", "гайки", "шайбы", "шпильки", "штифты", "анкеры",
      "заклепки", "шпонки", "хомуты", "гвозди", "шурупы", "шплинты", "зажимы"], "fastener_products"),
    # Wires, cables, ropes
    (["кабели", "провода", "проволока", "канаты"], "wires_and_cables"),
    # Pipes and pipeline fittings
    (["трубы", "тройники", "муфты", "фланцы", "отводы", "переходы", "заглушки",
      "крестовины", "угольники", "ниппели", "штуцера", "проходники", "переходники",
      "задвижки", "затворы", "краны шаровые", "клапаны", "вентили", "фильтр",
      "прокладки", "крышки", "колена", "патрубки", "футорки", "пробки",
      "манжеты", "butterfly valve", "gate valve", "control fitting",
      "pressure control", "fitting", "coupling", "valve", "appliance"], "valves_pipeline_components"),
    (["опоры"], "valves_pipeline_components"),
    # Metal rolling / metal products
    (["прокат", "профили", "уголки", "двутавры", "швеллеры", "рельсы",
      "плиты", "листы", "полосы", "круги", "квадраты", "шестигранники",
      "заготовки"], "metal_rolling"),
    # Machines and machine tools
    (["станки", "токарные", "сверлильные", "листогибочные", "пресс-ножницы",
      "резьбонакатные", "валковые", "лазерн", "фрезерные", "шлифовальные",
      "долбежные", "строгальные", "зубообрабатывающие", "прессовое",
      "кузнечно-прессовое", "электроэрозионные", "пильные"], "machines_their_parts_and_accessories"),
    # Cutting tools / tooling
    (["фрезы", "сверла", "резцы", "державки", "пластины", "оправки",
      "метчики", "развертки", "зенкеры", "протяжки", "пилы", "сверла",
      "пуансоны", "матрицы", "штамп", "прихваты", "упоры для штампов"], "machines_their_parts_and_accessories"),
    # Welding
    (["сварочн", "электроды"], "welding_equipment"),
    # Electrical distribution
    (["реле", "контакторы", "пускатели", "автоматические выключатели",
      "предохранители", "трансформаторы", "шинопровод", "щиты",
      "клеммы", "клеммные"], "electricity_distribution_and_control_equipment"),
    # Electric motors, generators
    (["электродвигатели", "генераторы", "серводвигатели"], "electric_motors_generators_transformers"),
    # Lighting
    (["светильники", "лампы"], "lighting_equipment_electric_lamps"),
    # Electronic components
    (["микросхемы", "диоды", "транзисторы", "конденсаторы", "резисторы", "платы"], "electronic_components"),
    # Bearings, springs, machine parts
    (["подшипники", "пружины", "втулки", "кольца", "блоки", "наконечники",
      "соединения", "пальцы", "хвостовики", "прижимы", "ограничители",
      "корпуса", "стойки"], "machine_parts_and_units"),
    # Handles, levers (English)
    (["handle", "hand wheel", "lever", "knob", "cam lever", "crank", "coupling (rigid)"], "machine_parts_and_units"),
    # Pumps, compressors
    (["насосы", "компрессоры"], "pumps_and_compressor_equipment"),
    # Boilers, heat exchange
    (["котлы", "теплообмен"], "heat_exchangers"),
    # Oilfield / drilling (pipes with these attributes already covered by трубы, but equipment too)
    (["бурильн", "обсадн", "колонков"], "oilfield_and_drilling_equipment"),
  # Wire/pipe production equipment
    (["оборудование для подготовки", "волочения проволоки", "трубопрокатное",
      "прокатное оборудование", "металлургическ"], "metallurgy_machinery_and_spare_parts"),
    # Hydraulics/pneumatics
    (["гидравлич", "пневматич", "пневмо", "гидро"], "hydraulic_and_pneumatic_automation_devices"),
    # Motors, turbines
    (["турбины", "двигатели"], "motors_turbines_and_spare_parts"),
    # Hoses
    (["шланги", "рукава"], "hoses_conveyor_belts_belts_rubberized_fabric_ebonite"),
    # Conveyor belts / tapes
    (["ленты конвейерные", "ленты пильные", "ленты полировальные"], "hoses_conveyor_belts_belts_rubberized_fabric_ebonite"),
    (["ленты"], "metal_rolling"),
    # Measuring instruments
    (["манометр", "термометр", "датчик", "измерител", "счетчик"], "control_and_measuring_devices"),
    (["испытательное оборудование"], "testing_equipment"),
    # Lubrication
    (["смазочн"], "oils_and_lubricants"),
    # Logistics / misc codes
    (["logistics", "service"], "machinery_and_equipment_their_components_and_spare_parts_(excluding_other_groups)"),
    # Building materials (ceramic pipes, etc.)
    (["трубы чугунные канализационные", "трубы полимерные"], "building_materials"),
    (["трубы керамические"], "ceramic_pipes"),
    # Plumbing
    (["сантехник"], "plumbing"),
    # Insulation
    (["изоляци", "утеплител", "теплоизолирован"], "insulation"),
    # Ventilation
    (["вентиляц", "воздуховод"], "ventilation"),
    # Instruments (building)
    (["инструмент"], "instruments"),
    # Polymer pipes
    (["полимерн"], "plastic_materials_and_products"),
]

# Top-level user slugs that are relevant for industrial product catalog
INDUSTRIAL_ROOTS = {
    "machinery_and_equipment", "metal_working_equipment_metal_products",
    "metallurgical_products", "electrical_equipment_electronics",
    "rubber_products", "building", "fastener_products", "polymer_materials",
    "chemical_and_pharmaceutical_substances_chemical_and_laboratory_supplies",
    "oil_and_gas_products_fuels_and_lubricants", "telecommunications_communication_equipment_internet_security",
    "paper_containers_packaging",
}


def parse_user_categories(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    user_cats = []
    pattern = re.compile(
        r'id:\s*(\d+),\s*parentId:\s*(\d+|null),\s*name:\s*"([^"]+)",\s*text:\s*\{\s*ru:\s*(?:"([^"]*)"|(?:\n\s*//[^\n]*\n\s*"([^"]*)"))',
        re.DOTALL,
    )
    for m in pattern.finditer(content):
        user_cats.append({
            "id": int(m.group(1)),
            "parentId": None if m.group(2) == "null" else int(m.group(2)),
            "slug": m.group(3),
            "ru": (m.group(4) or m.group(5) or "").strip(),
        })
    return user_cats


def build_paths(user_cats: list[dict]) -> dict[int, str]:
    by_id = {c["id"]: c for c in user_cats}
    paths: dict[int, str] = {}

    def path_for(cat_id: int) -> str:
        if cat_id in paths:
            return paths[cat_id]
        parts: list[str] = []
        current: int | None = cat_id
        seen: set[int] = set()
        while current and current in by_id and current not in seen:
            seen.add(current)
            parts.insert(0, by_id[current]["ru"])
            current = by_id[current]["parentId"]
        paths[cat_id] = " > ".join(parts)
        return paths[cat_id]

    for c in user_cats:
        path_for(c["id"])
    return paths


def get_root_slug(cat: dict, by_id: dict[int, dict]) -> str:
    current = cat
    while current["parentId"] and current["parentId"] in by_id:
        current = by_id[current["parentId"]]
    return current["slug"]


def normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


def rule_match(orig_name: str, slug_by_name: dict[str, dict]) -> dict | None:
    norm = normalize(orig_name)
    best_slug = None
    best_len = 0
    for patterns, slug in RULES:
        for p in patterns:
            if p in norm:
                if len(p) > best_len and slug in slug_by_name:
                    best_len = len(p)
                    best_slug = slug
    return slug_by_name.get(best_slug) if best_slug else None


def fuzzy_match(
    orig_name: str,
    candidates: list[dict],
    paths: dict[int, str],
) -> tuple[dict | None, float]:
    if not candidates:
        return None, 0.0
    choices = {c["id"]: f"{c['ru']} | {paths[c['id']]}" for c in candidates}
    result = process.extractOne(orig_name, choices, scorer=fuzz.token_set_ratio)
    if not result:
        return None, 0.0
    score = result[1]
    cat_id = result[2]
    cat = next(c for c in candidates if c["id"] == cat_id)
    return cat, score


def main() -> None:
    user_cats = parse_user_categories(USER_CATS_PATH)
    by_id = {c["id"]: c for c in user_cats}
    paths = build_paths(user_cats)
    slug_by_name = {c["slug"]: c for c in user_cats}

    # Prefer leaf categories for fuzzy matching
    parent_ids = {c["parentId"] for c in user_cats if c["parentId"]}
    leaf_cats = [c for c in user_cats if c["id"] not in parent_ids]
    industrial_leaves = [
        c for c in leaf_cats
        if get_root_slug(c, by_id) in INDUSTRIAL_ROOTS
        or c["slug"] in {s for _, s in RULES}
    ]

    with open(ORIG_CATS_PATH, encoding="utf-8") as f:
        orig_data = json.load(f)

    mapping: dict[str, list[str]] = defaultdict(list)
    unmatched_orig: list[dict] = []
    match_stats: dict[str, int] = defaultdict(int)
    match_details: list[dict] = []

    for item in orig_data:
        orig_name = item["Name"]
        user_cat = rule_match(orig_name, slug_by_name)
        method = "rule"
        score = 100.0

        if not user_cat:
            user_cat, score = fuzzy_match(orig_name, industrial_leaves, paths)
            method = "fuzzy"
            if score < 70:
                user_cat = None

        if user_cat:
            key = user_cat["ru"]
            mapping[key].append(orig_name)
            match_stats[method] += 1
            match_details.append({
                "original": orig_name,
                "user_category": user_cat["ru"],
                "user_slug": user_cat["slug"],
                "user_path": paths[user_cat["id"]],
                "method": method,
                "score": score,
            })
        else:
            unmatched_orig.append({
                "original_category": orig_name,
                "keywords_count": len(item.get("Keywords", [])),
            })

    matched_slugs = {d["user_slug"] for d in match_details}
    unmatched_user = [
        {
            "id": c["id"],
            "slug": c["slug"],
            "ru": c["ru"],
            "path": paths[c["id"]],
        }
        for c in user_cats
        if c["slug"] not in matched_slugs
    ]

    output = {cat: sorted(origs) for cat, origs in sorted(mapping.items())}

    with open(OUTPUT_MAPPING, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    unmatched_report = {
        "unmatched_original_categories": sorted(unmatched_orig, key=lambda x: -x["keywords_count"]),
        "unmatched_user_categories": sorted(unmatched_user, key=lambda x: x["path"]),
        "stats": {
            "original_total": len(orig_data),
            "original_matched": len(orig_data) - len(unmatched_orig),
            "original_unmatched": len(unmatched_orig),
            "user_total": len(user_cats),
            "user_with_matches": len(matched_slugs),
            "user_without_matches": len(unmatched_user),
            "match_methods": dict(match_stats),
        },
    }

    with open(OUTPUT_UNMATCHED, "w", encoding="utf-8") as f:
        json.dump(unmatched_report, f, ensure_ascii=False, indent=2)

    # Detailed mapping with paths
    with open("/workspace/category_mapping_detailed.json", "w", encoding="utf-8") as f:
        json.dump(match_details, f, ensure_ascii=False, indent=2)

    print(json.dumps(unmatched_report["stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
