#!/usr/bin/env python3
"""Fill empty training categories with appropriate items (no cross-category duplicates)."""

from __future__ import annotations

import json
import re
from collections import OrderedDict

INPUT_PATH = "/workspace/user_requests_training.json"
OUTPUT_PATH = "/workspace/user_requests_training.json"
STATS_PATH = "/workspace/training_fill_empty_stats.json"

KEY_RENTAL = "290(Услуги по аренде техники, оборудования, бытовых товаров и предметов личного пользования)"
KEY_FOOD = "114(Прочие пищевые продукты, не включенные в другие группировки)"
KEY_REALTY = "199(Аренда и лизинг недвижимости, обмен, приватизация)"
KEY_TRANSPORT_RENTAL = "296(Аренда, лизинг транспорта)"
KEY_VEGETABLES = "113(Овощи, фрукты, ягоды, зелень, грибы)"

# Equipment / household rental — move from realty rental bucket
RENTAL_FROM_REALTY = [
    "Аренда бытовки",
    "Аренда автотранспорта",
    "Аренда спецтехники",
    "Аренда крана",
    "Аренда экскаватора",
    "Аренда погрузчика",
    "Аренда генератора",
    "Аренда компрессора",
    "Аренда подъемника",
    "Аренда бытовок для персонала",
    "Аренда контейнера",
    "Аренда вагончика",
    "Аренда опалубки",
    "Аренда лесов",
    "Аренда бытовой техники",
    "Аренда серверного оборудования",
    "Аренда оргтехники",
    "Аренда мебели",
    "Аренда холодильной камеры",
    "Аренда автовышки",
]

# Construction / industrial equipment — move from transport rental bucket
RENTAL_FROM_TRANSPORT = [
    "Аренда башенного крана",
    "Аренда автокрана",
    "Аренда экскаватора-погрузчика",
]

RENTAL_NEW = [
    "Аренда манипулятора",
    "Аренда катка дорожного",
    "Аренда асфальтоукладчика",
    "Аренда проекционного оборудования",
    "Аренда звукового оборудования",
    "Аренда строительных лесов",
    "Аренда бетономешалки",
]

FOOD_MOVE_FROM_VEGETABLES = ["Паприка копченая"]

FOOD_NEW = [
    "Куркума молотая",
    "Корица молотая",
    "Перец красный молотый",
    "Приправа универсальная",
    "Уксус столовый 9%",
    "Горчица столовая",
    "Кетчуп томатный",
    "Майонез провансаль",
    "Соевый соус",
    "Мед натуральный цветочный",
    "Варенье малиновое",
    "Крахмал картофельный",
    "Дрожжи сухие хлебопекарные",
    "Желатин пищевой",
    "Бульонные кубики куриные",
    "Паста томатная",
    "Изюм",
    "Курага",
    "Кокосовая стружка",
    "Сироп кленовый",
    "Хрен столовый",
    "Кисель в пакетиках",
    "Желе фруктовое",
    "Укроп сушеный",
    "Базилик сушеный",
    "Орегано сушеный",
    "Тимьян сушеный",
    "Розмарин сушеный",
    "Смесь перцев горошком",
]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def remove_item(items: list[str], target: str) -> list[str]:
    key = norm(target)
    return [x for x in items if norm(x) != key]


def add_item(items: list[str], item: str) -> list[str]:
    if norm(item) in {norm(x) for x in items}:
        return items
    return [*items, item]


def move_items(
    data: OrderedDict,
    items: list[str],
    source_key: str,
    target_key: str,
) -> int:
    moved = 0
    for item in items:
        source_items = data[source_key]
        if not any(norm(x) == norm(item) for x in source_items):
            continue
        if any(norm(x) == norm(item) for x in data[target_key]):
            data[source_key] = remove_item(source_items, item)
            continue
        data[source_key] = remove_item(source_items, item)
        data[target_key] = add_item(data[target_key], item)
        moved += 1
    return moved


def verify(data: OrderedDict) -> dict:
    item_cats: dict[str, list[str]] = {}
    within = 0
    for key, items in data.items():
        seen: set[str] = set()
        for item in items:
            n = norm(item)
            if n in seen:
                within += 1
            seen.add(n)
            item_cats.setdefault(n, []).append(key)
    cross = sum(1 for cats in item_cats.values() if len(cats) > 1)
    empty = [k for k, v in data.items() if len(v) == 0]
    return {
        "within_duplicates": within,
        "cross_duplicates": cross,
        "empty_categories": empty,
        "total_items": sum(len(v) for v in data.values()),
    }


def main() -> None:
    with open(INPUT_PATH, encoding="utf-8") as f:
        data = json.loads(f.read(), object_pairs_hook=OrderedDict)

    before = verify(data)
    stats = {
        "before": before,
        "moves": {},
        "added": {},
    }

    stats["moves"]["rental_from_realty"] = move_items(
        data, RENTAL_FROM_REALTY, KEY_REALTY, KEY_RENTAL
    )
    stats["moves"]["rental_from_transport"] = move_items(
        data, RENTAL_FROM_TRANSPORT, KEY_TRANSPORT_RENTAL, KEY_RENTAL
    )
    stats["moves"]["food_from_vegetables"] = move_items(
        data, FOOD_MOVE_FROM_VEGETABLES, KEY_VEGETABLES, KEY_FOOD
    )

    added_rental = 0
    for item in RENTAL_NEW:
        if not any(norm(item) == norm(x) for cats in data.values() for x in cats):
            data[KEY_RENTAL] = add_item(data[KEY_RENTAL], item)
            added_rental += 1
    stats["added"]["rental"] = added_rental

    added_food = 0
    for item in FOOD_NEW:
        if not any(norm(item) == norm(x) for cats in data.values() for x in cats):
            data[KEY_FOOD] = add_item(data[KEY_FOOD], item)
            added_food += 1
    stats["added"]["food"] = added_food

    stats["after"] = verify(data)
    stats["filled_counts"] = {
        KEY_RENTAL: len(data[KEY_RENTAL]),
        KEY_FOOD: len(data[KEY_FOOD]),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
