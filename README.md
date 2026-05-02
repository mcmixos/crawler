# crawler

Асинхронный HTTP-клиент для загрузки веб-страниц на базе aiohttp. Альфа-версия - пока только базовый клиент с ограничением конкурентности, таймаутами и обработкой ошибок.

## Требования

Python 3.10+

## Установка

В активированном venv:

```
pip install -e .
pip install -r requirements-dev.txt
```

Первая команда ставит сам пакет в editable-режиме вместе с runtime-зависимостями (aiohttp, aiofiles), вторая - dev-зависимости для тестов.

## Использование

```python
import asyncio
from crawler import AsyncCrawler

async def main():
    async with AsyncCrawler(max_concurrent=10) as crawler:
        html = await crawler.fetch_url("https://example.com")
        print(len(html))

        urls = [
            "https://example.com",
            "https://httpbin.org/html",
        ]
        results = await crawler.fetch_urls(urls)
        print(f"Загружено: {len(results)}")

asyncio.run(main())
```

`fetch_urls` возвращает `dict[str, str]` - упавшие URL в результат не попадают, но пишутся в лог с типом ошибки.

Параметры конструктора:

- `max_concurrent` - лимит одновременных запросов (по умолчанию 10)
- `connect_timeout` - таймаут установки соединения, сек (10)
- `read_timeout` - таймаут чтения ответа, сек (30)
- `user_agent` - заголовок User-Agent

## Парсинг HTML

`fetch_and_parse(url)` загружает страницу и возвращает структуру `{url, title, text, links, metadata}`:

```python
async with AsyncCrawler() as crawler:
    result = await crawler.fetch_and_parse("https://example.com")
    print(result["title"])
    print(len(result["links"]), "ссылок")
```

Парсер также доступен напрямую как `HTMLParser` - полезно, если HTML уже есть на руках:

```python
from crawler import HTMLParser

parser = HTMLParser()
data = await parser.parse_html(html_string, "https://example.com")
```

У парсера есть дополнительные методы для конкретных типов данных: `extract_images`, `extract_headings`, `extract_tables`, `extract_lists`.

## Crawl

Метод `crawl()` обходит сайт целиком: ставит стартовые URL в очередь, забирает HTML, парсит, извлекает ссылки, кладёт их обратно в очередь. Поддерживает контроль глубины, фильтры по доменам/паттернам, лимит страниц.

```python
async with AsyncCrawler(
    max_concurrent=10,
    max_per_host=3,
    max_depth=2,
) as crawler:
    results = await crawler.crawl(
        start_urls=["https://example.com"],
        max_pages=50,
        same_domain_only=True,
        exclude_patterns=[r"\.(jpg|png|pdf)$"],
    )
```

Возвращает `{url: parsed_data}` для всех успешно обработанных страниц. Прогресс пишется в логи раз в секунду.

Конкурентность управляется `SemaphoreManager`: глобальный лимит (`max_concurrent`) и per-host (`max_per_host`). Используется внутри AsyncCrawler автоматически - все вызовы fetch_url проходят через него.

`CrawlerQueue` - очередь с приоритетами, отслеживанием глубины и состояний (visited / processed / failed). Доступна как самостоятельный класс через `from crawler import CrawlerQueue`.

## Polite crawling: rate limit, robots.txt, retries

`AsyncCrawler` поддерживает контроль скорости и соблюдение robots.txt:

```python
async with AsyncCrawler(
    requests_per_second=2.0,    # лимит частоты
    min_delay=0.5,               # минимум 0.5с между запросами
    jitter=0.2,                  # +случайно [0, 0.2с] для имитации человека
    respect_robots=True,         # читать и соблюдать robots.txt
    max_retries=3,               # ретраи на 5xx, 429, timeout, connection error
    backoff_base=1.0,            # exp backoff: 1с, 2с, 4с, ...
    user_agent="MyBot/1.0",      # либо list[str] для ротации
) as crawler:
    results = await crawler.crawl(
        start_urls=["https://example.com"],
        max_pages=50,
        same_domain_only=True,
    )
    print(crawler.get_stats())
```

`get_stats()` возвращает `{requests, rate_per_sec, avg_interval_ms, avg_request_ms, blocked_by_robots, retries}`.

При `respect_robots=True`:
- robots.txt подгружается перед первым запросом к домену (один раз, кэшируется)
- запрещённые URL пропускаются (raise `RobotsBlocked` из `fetch_url`)
- `Crawl-delay` из robots.txt применяется поверх настроенного rate limit'а

`RateLimiter` и `RobotsParser` доступны как самостоятельные классы через `from crawler import ...`.

## Демо

```
python examples/demo.py
```

Загружает 8 URL последовательно и параллельно, выводит время и speedup.

## Тесты

```
pytest
```

Используется aioresponses, реальная сеть не нужна.

## Структура

```
src/crawler/
  client.py        - AsyncCrawler
  parser.py        - HTMLParser
  queue.py         - CrawlerQueue
  concurrency.py   - SemaphoreManager
  rate_limiter.py  - RateLimiter
  robots.py        - RobotsParser, RobotsBlocked
examples/
  demo.py          - параллель vs последовательно (день 1)
  parse_demo.py    - парсинг страниц + JSON (день 2)
  crawl_demo.py    - обход с очередью и глубиной (день 3)
  polite_demo.py   - rate limit + robots.txt + retries (день 4)
tests/
  test_client.py
  test_parser.py
  test_queue.py
  test_concurrency.py
  test_crawl.py
  test_rate_limiter.py
  test_robots.py
```
