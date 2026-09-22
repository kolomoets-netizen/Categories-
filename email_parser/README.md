# Partner Email Parser

Парсер email-адресов с сайтов партнёров.

## Возможности

- обход главной страницы и страниц «Контакты / About / Impressum»
- извлечение из текста, `mailto:` и обфускаций (`info [at] site [dot] com`, `&#64;`)
- фильтр служебных адресов (`noreply`, трекеры, фейковые domain)
- отчёт JSON / CSV
- пометка адресов, совпадающих с доменом сайта

## Установка

```bash
pip install -r email_parser/requirements.txt
```

## Использование

Один или несколько сайтов:

```bash
python -m email_parser -u https://partner.ru -u partner2.com
```

Список из файла:

```bash
python -m email_parser -f email_parser/partners.example.txt -o report.json --csv report.csv
```

Через stdin:

```bash
echo "https://tilda.cc" | python -m email_parser --all-emails
```

### Параметры

| Флаг | Описание |
|------|----------|
| `-u / --url` | URL или домен (можно несколько раз) |
| `-f / --file` | Файл со списком сайтов |
| `-o` | JSON-отчёт |
| `--csv` | CSV-отчёт |
| `--max-pages` | Макс. страниц на сайт (по умолчанию 8) |
| `--delay` | Пауза между запросами, сек |
| `--all-emails` | Показать все найденные адреса, не только домен сайта |

## Тесты

```bash
python email_parser/test_extractor.py
```

## Важно

Используйте только для сайтов партнёров / публичных контактов, соблюдайте robots.txt и условия сайта. Не для массового спама.
