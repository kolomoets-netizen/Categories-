# Данные каталога франчайзи 1С

Скачано со страницы:

`https://1c.ru/rus/partners/franch-citylist.jsp?...&pageNumber_inp=1`

## Сайты

| Файл | Описание |
|------|----------|
| `franch-citylist-page1.html` | Исходный HTML (карта + список) |
| `partner_sites.txt` | Уникальные сайты партнёров (~1519) |
| `source_url.txt` | URL источника |

## Emails

Собрано парсером по `partner_sites.txt` (главная + страницы контактов).

| Файл | Описание |
|------|----------|
| `partner_emails.txt` | Все уникальные email (~1803) |
| `partner_emails_domain.txt` | Только email на домене сайта партнёра (~1322) |
| `partner_emails.csv` | Сайт → email |
| `partner_emails.json` | Полный отчёт по каждому сайту |
| `partner_emails_summary.json` | Краткая статистика |

## Аутрич (отфильтровано)

| Файл | Описание |
|------|----------|
| `partners_large_skip.txt` | Крупные сети/бренды — **не писать** (66) |
| `partners_outreach.txt` | Кандидаты: сайт + email (**1024** сайтов) |
| `partners_outreach_emails.txt` | Только email для рассылки (**1524**) |
| `partners_outreach.csv` | сайт → email |
| `partners_outreach_no_email.txt` | Не крупные, но email не найден (429) |
| `partners_outreach_summary.json` | Статистика фильтра |

Крупных отсечено: Первый БИТ (~46 URL), Koderline, Рарус, 1АБ, Gendalf, Axelot, WiseAdvice, RDV, Астрал, SoftBalance и др.
