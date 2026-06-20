#!/usr/bin/env python3
"""Distribute keywords across product categories."""

import json
import re
from collections import defaultdict

from rapidfuzz import fuzz, process

INPUT_PATH = "/home/ubuntu/.cursor/projects/workspace/uploads/categories_14ca.json"
OUTPUT_PATH = "/workspace/keywords_by_category.json"

# Keyword fragment -> category name fragments to include as extra candidates
TYPE_ALIASES = {
    "вальц": ["валков"],
    "листогиб": ["листогибочн"],
    "пресс-ножниц": ["пресс-ножниц"],
    "сверлильн": ["сверлильн"],
    "токарн": ["токарн"],
    "лазерн": ["лазерн"],
    "резьбонакатн": ["резьбонакатн"],
    "оптово": ["лазерн"],
    "кабель": ["кабел"],
    "провод": ["провод"],
    "труб": ["труб"],
    "винт": ["винт"],
    "болт": ["болт"],
    "гайк": ["гайк"],
    "шайб": ["шайб"],
    "фрез": ["фрез"],
    "тройник": ["тройник"],
    "муфт": ["муфт"],
    "фланц": ["фланц"],
    "отвод": ["отвод"],
    "заглуш": ["заглуш"],
    "переход": ["переход"],
    "крестовин": ["крестовин"],
    "заклеп": ["заклеп"],
    "втулк": ["втулк"],
    "кольц": ["кольц"],
    "ниппел": ["ниппел"],
    "угольник": ["угольник"],
    "задвиж": ["задвиж"],
    "реле": ["реле"],
    "лент": ["лент"],
    "проволок": ["проволок"],
    "опор": ["опор"],
    "прокат": ["прокат"],
    "детал": ["детал"],
    "шпильк": ["шпильк"],
    "штифт": ["штифт"],
    "резц": ["резц"],
    "подшипник": ["подшипник"],
    "профил": ["профил"],
    "наконечник": ["наконечник"],
    "шланг": ["шланг"],
    "кран": ["кран"],
    "клапан": ["клапан"],
    "насос": ["насос"],
    "электрод": ["электрод"],
    "контактор": ["контактор"],
    "пускател": ["пускател"],
    "датчик": ["датчик"],
    "манометр": ["манометр"],
    "термометр": ["термометр"],
}

PHRASE_BONUSES = [
    (["магистральн", "промыслов"], ["нефтегазопроводн"], 25),
    (["магистральн", "промыслов"], ["магистральн"], 20),
    (["газопровод"], ["нефтегазопроводн"], 15),
    (["обсадн"], ["обсадн"], 20),
    (["бурильн"], ["бурильн"], 20),
    (["колонков"], ["колонков"], 20),
    (["насосно", "компрессорн"], ["насосно-компрессорн"], 20),
    (["котельн"], ["котельн"], 15),
    (["холоднодеформированн"], ["холоднодеформированн"], 15),
    (["горячедеформированн"], ["горячедеформированн"], 15),
    (["электросварн", "прямошовн"], ["электросварн", "прямошовн"], 15),
    (["профильн"], ["профильн"], 20),
    (["четырехвалков"], ["четырехвалков", "валков"], 20),
    (["лазерн", "резк"], ["лазерн", "резк"], 15),
    (["сверлильн"], ["сверлильн"], 15),
    (["токарн"], ["токарн"], 15),
    (["листогиб"], ["листогибочн"], 20),
    (["пресс-ножниц"], ["пресс-ножниц"], 20),
]

ATTRIBUTE_TERMS = [
    ("нефтегазопроводн", 15), ("магистральн", 12), ("промыслов", 12),
    ("газопровод", 10), ("нефтепровод", 10), ("обсадн", 15), ("бурильн", 15),
    ("колонков", 12), ("насосно-компрессорн", 15), ("котельн", 12),
    ("холоднодеформированн", 12), ("горячедеформированн", 12),
    ("теплодеформированн", 10), ("электросварн", 10), ("прямошовн", 10),
    ("профильн", 10), ("бесшовн", 8), ("сварн", 6), ("атомн", 10),
    ("хладостойк", 8), ("сероводород", 8), ("подводн", 8),
    ("гидравлическ", 8), ("вертикально-сверлильн", 12),
    ("радиально-сверлильн", 12), ("четырехвалков", 15), ("трехвалков", 12),
    ("лазерн", 12), ("оптово", 10), ("резьбонакатн", 12), ("листогиб", 12),
    ("сверлильн", 10), ("токарн", 10), ("пресс-ножниц", 12), ("вальц", 12),
    ("пластмассов", 8), ("стальн", 4),
]


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def attribute_bonus(kw: str, cat: str) -> float:
    bonus = 0.0
    for term, weight in ATTRIBUTE_TERMS:
        if term in kw and term in cat:
            bonus += weight
    for kw_terms, cat_terms, weight in PHRASE_BONUSES:
        if all(t in kw for t in kw_terms) and all(t in cat for t in cat_terms):
            bonus += weight
    # Penalize category attributes absent from keyword
    if "профильн" in cat and "профильн" not in kw:
        bonus -= 15
    if "кругл" in cat and "профильн" in kw:
        bonus -= 10
    return bonus


def score_match(keyword: str, category: str, is_original: bool = False) -> float:
    kw = normalize(keyword)
    cat = normalize(category)
    if not kw or not cat:
        return 0.0

    token_set = fuzz.token_set_ratio(kw, cat)
    partial = fuzz.partial_ratio(kw, cat)
    ratio = fuzz.ratio(kw, cat)

    kw_tokens = set(kw.split())
    cat_tokens = set(cat.split())
    overlap = len(kw_tokens & cat_tokens) / max(len(kw_tokens), 1) * 100

    # Root word match bonus
    root_bonus = 0.0
    for key, aliases in TYPE_ALIASES.items():
        if key in kw:
            for alias in aliases:
                if alias in cat:
                    root_bonus = 25.0
                    break

    specificity = min(len(cat.split()), 12) * 1.0

    original_bonus = 10.0 if is_original else 0.0

    return (
        token_set * 0.35
        + partial * 0.2
        + ratio * 0.1
        + overlap * 0.2
        + root_bonus
        + attribute_bonus(kw, cat)
        + specificity
        + original_bonus
    )


def build_alias_index(categories: list[str]) -> dict[str, list[str]]:
    """Map alias fragment -> matching category names."""
    index: dict[str, list[str]] = defaultdict(list)
    for cat in categories:
        cat_lower = cat.lower()
        for key, aliases in TYPE_ALIASES.items():
            for alias in aliases:
                if alias in cat_lower:
                    index[key].append(cat)
                    break
    return index


def get_candidates(
    keyword: str,
    original_cats: list[str],
    alias_index: dict[str, list[str]],
    categories: list[str],
) -> list[str]:
    candidates: list[str] = list(original_cats)
    kw_lower = keyword.lower()

    for key, cats in alias_index.items():
        if key in kw_lower:
            candidates.extend(cats)

    # Deduplicate
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    return unique if unique else categories


def main() -> None:
    with open(INPUT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    categories = [item["Name"] for item in data]
    alias_index = build_alias_index(categories)

    original_assignments: dict[str, list[str]] = defaultdict(list)
    for item in data:
        for kw in item.get("Keywords", []):
            original_assignments[kw].append(item["Name"])

    result: dict[str, list[str]] = defaultdict(list)

    for keyword in sorted(original_assignments.keys()):
        orig_cats = original_assignments[keyword]
        candidates = get_candidates(keyword, orig_cats, alias_index, categories)
        orig_set = set(orig_cats)
        best_cat = max(
            candidates,
            key=lambda c: score_match(keyword, c, is_original=c in orig_set),
        )
        result[best_cat].append(keyword)

    output = {cat: sorted(kws) for cat, kws in sorted(result.items())}

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    checks = [
        "Вальцы четырехвалковые гидравлические AKYAPAK. Серия AHS",
        "Оптоволоконный лазерный станок для резки металла",
        "Пресс-ножницы гидравлические",
        "Листогиб",
        "Сверлильные станки",
        "Трубы стальные бесшовные горячедеформированные для магистральных и промысловых трубопроводов",
    ]
    print("=== Validation ===")
    for kw in checks:
        for cat, kws in output.items():
            if kw in kws:
                print(f"  [{cat}]")
                print(f"    {kw}")
                break

    print(f"\nKeywords: {len(original_assignments)}")
    print(f"Categories used: {len(output)}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
