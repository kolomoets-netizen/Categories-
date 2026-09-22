# Partner Email & Site List Parser

Два инструмента в одном CLI:

1. **`sites`** — собрать ссылки на сайты со страницы с пагинацией  
2. **`emails`** — достать email-адреса с сайтов партнёров

## Установка

```bash
pip install -r email_parser/requirements.txt
```

### Docker (опционально)

Локальный Python не нужен — удобно, если Docker уже есть:

```bash
docker build -t partner-parser .

# список сайтов с пагинацией
docker run --rm -v "$PWD:/data" partner-parser sites \
  -u "https://YOUR_LISTING" \
  -o /data/partner_sites.txt

# email по списку
docker run --rm -v "$PWD:/data" partner-parser emails \
  -f /data/partner_sites.txt \
  -o /data/emails.json --csv /data/emails.csv
```

## 1. Парсер списка сайтов (пагинация)

```bash
PYTHONPATH=. python3 -m email_parser sites \
  -u "https://catalog.example/partners" \
  -o partner_sites.txt \
  --json partners.json
```

### Полезные флаги

| Флаг | Зачем |
|------|--------|
| `--link-selector` | CSS-селектор ссылок на сайты, напр. `a.partner-url` |
| `--next-selector` | CSS-селектор кнопки «следующая», напр. `a.next` |
| `--page-param page` | Пагинация вида `?page=2` |
| `--max-pages 100` | Лимит страниц листинга |
| `--include-internal` | Не отбрасывать ссылки на тот же домен |
| `-o file.txt` | Список сайтов (по одному на строку) |

Автоопределение пагинации:
- `rel="next"`
- текст «Следующая / Next / › / »»
- `?page=N`, `/page/N/`, нумерация страниц

## 2. Парсер email

```bash
PYTHONPATH=. python3 -m email_parser emails \
  -f partner_sites.txt \
  -o report.json --csv report.csv
```

Или напрямую:

```bash
PYTHONPATH=. python3 -m email_parser emails -u https://partner.ru
```

Старый синтаксис без подкоманды тоже работает (как `emails`).

## Конвейер

```bash
PYTHONPATH=. python3 -m email_parser sites -u "https://YOUR_LISTING_URL" -o partner_sites.txt
PYTHONPATH=. python3 -m email_parser emails -f partner_sites.txt -o emails.json --csv emails.csv
```

## Тесты

```bash
PYTHONPATH=. python3 email_parser/test_extractor.py
PYTHONPATH=. python3 email_parser/test_site_list.py
```

## Важно

Только для публичных страниц партнёров / каталогов. Соблюдайте правила сайта и robots.txt.
