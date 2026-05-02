# crawler

![tests](https://github.com/USER/REPO/actions/workflows/test.yml/badge.svg)

Асинхронный веб-краулер на Python: HTTP, парсинг HTML, обход по ссылкам с приоритетной очередью, rate limiting, robots.txt, retry с exp backoff, circuit breaker, сохранение в JSON/CSV/SQLite, sitemap, статистика и HTML-отчёты.

> Замени `USER/REPO` в badge'е на реальный путь после первого пуша на GitHub.

## Требования

Python 3.10+

## Установка

```
pip install -e .
pip install -r requirements-dev.txt
```

Первая команда ставит сам пакет в editable-режиме вместе с runtime-зависимостями. Вторая - тестовые либы.

## Quick start

Минимальный пример - краулим один сайт с дефолтами:

```python
import asyncio
from crawler import AsyncCrawler

async def main():
    async with AsyncCrawler(max_depth=2) as crawler:
        results = await crawler.crawl(
            start_urls=["https://example.com"],
            max_pages=20,
            same_domain_only=True,
        )
    print(f"Обработано: {len(results)}")

asyncio.run(main())
```

Полный краулер с конфигом, robots, rate limit, SQLite и HTML-отчётом:

```python
import asyncio
from crawler import AdvancedCrawler

async def main():
    async with AdvancedCrawler.from_config("examples/example_config.yaml") as crawler:
        await crawler.crawl()
        crawler.export_to_html_report("output/report.html")

asyncio.run(main())
```

## CLI

```
crawler --urls https://example.com --max-pages 50 --max-depth 2 --respect-robots
crawler --config examples/example_config.yaml
crawler --config examples/example_config.yaml --max-pages 200   # CLI > config
```

Параметры:

| Флаг | Назначение |
|---|---|
| `--config PATH` | YAML-конфиг |
| `--urls URL [URL ...]` | стартовые URL |
| `--max-pages N` | лимит страниц |
| `--max-depth N` | глубина обхода |
| `--rate-limit N` | requests per second |
| `--respect-robots` | включить robots.txt |
| `--same-domain-only` | не уходить с домена |
| `--output PATH` | JSON со статистикой |
| `--report PATH` | HTML-отчёт |
| `--log-level LEVEL` | DEBUG/INFO/WARNING/ERROR |

CLI-флаги переопределяют значения из конфига.

## Конфигурация (YAML)

Полный пример - см. [`examples/example_config.yaml`](examples/example_config.yaml). Все секции опциональны.

```yaml
start_urls:
  - https://example.com
sitemap_urls:
  - https://example.com/sitemap.xml

max_pages: 100

crawler:
  max_concurrent: 10
  max_per_host: 3
  max_depth: 2
  requests_per_second: 2.0
  min_delay: 0.0
  jitter: 0.0
  respect_robots: true
  max_retries: 2
  backoff_base: 1.0
  user_agent: "MyBot/1.0"
  connect_timeout: 10.0
  read_timeout: 30.0
  total_timeout: null

filters:
  same_domain_only: true
  include_patterns: []
  exclude_patterns:
    - "\\.(jpg|png|pdf)$"

storage:
  type: sqlite              # json | csv | sqlite | none
  path: output/pages.db
  batch_size: 100           # только для sqlite

logging:
  level: INFO
  file: output/crawler.log  # null = только консоль
  max_bytes: 10485760
  backup_count: 5
```

## Компоненты

| Класс | Назначение |
|---|---|
| `AsyncCrawler` | основной HTTP-краулер; всё, что нужно для базового обхода |
| `AdvancedCrawler` | фасад: конфиг + sitemap + статистика + экспорт |
| `HTMLParser` | парсинг HTML: links, text, metadata, images, headings, tables, lists |
| `CrawlerQueue` | приоритетная очередь URL с дедупом и tracking'ом глубины |
| `SemaphoreManager` | global + per-host лимит параллелизма |
| `RateLimiter` | per-domain или global rate limit с jitter |
| `RobotsParser` + `RobotsBlocked` | парсинг и проверка robots.txt |
| `RetryStrategy` | повторы по типу ошибки с exp backoff |
| `CircuitBreaker` | временная блокировка проблемных доменов |
| `DataStorage` (+ `JSONStorage`/`CSVStorage`/`SQLiteStorage`) | сохранение результатов |
| `SitemapParser` | загрузка URL из sitemap.xml (рекурсивно для index) |
| `CrawlerStats` | статистика + JSON/HTML экспорт |
| `CrawlerConfig` | YAML/dict конфигурация |

Иерархия ошибок: `CrawlerError` → `TransientError` / `NetworkError` / `PermanentError` / `ParseError` / `CircuitOpenError`.

## Архитектура

`AsyncCrawler` - ядро. Координирует:
1. Circuit breaker (если задан) - проверка перед запросом
2. Robots.txt (если включён) - lazy load на первый URL домена
3. Rate limiter (если задан) - sleep до следующего разрешённого слота
4. Semaphore manager - лимит параллелизма global + per-host
5. RetryStrategy - повторы на TransientError/NetworkError по умолчанию
6. Storage (если задан) - автоматический save после успешного fetch_and_parse

`AdvancedCrawler` поверх этого добавляет YAML-конфиг, sitemap-обнаружение URL, агрегированную статистику и HTML-отчёты.

## Использование напрямую (без AdvancedCrawler)

Любой компонент можно использовать standalone:

```python
from crawler import HTMLParser, RetryStrategy, TransientError

parser = HTMLParser()
data = await parser.parse_html(html_string, "https://example.com")

retry = RetryStrategy(max_retries=3, retry_on=[TransientError])
result = await retry.execute_with_retry(some_async_func, arg)
```

## Cookies

Параметр `cookies: dict | None` в `AsyncCrawler` принимает начальные cookies для всех запросов:

```python
async with AsyncCrawler(cookies={"session_id": "abc123"}) as crawler:
    data = await crawler.fetch_and_parse("https://protected.example.com/page")
```

aiohttp дальше держит cookie jar автоматически в рамках сессии: cookies из `Set-Cookie` сохраняются и переотправляются при последующих запросах к тому же домену. Это покрывает типичную авторизацию по сессии. Сохранение cookies в файл между запусками не реализовано (можно поверх через `aiohttp.CookieJar.save/load`).

## Редиректы

`fetch_and_parse(url)` корректно обрабатывает HTTP-редиректы (3xx + Location): aiohttp следует за редиректом, относительные ссылки парсятся **относительно финального URL**. В возвращаемом dict:
- `url` - исходный запрошенный URL (identity для очереди и storage)
- `final_url` - URL после всех редиректов (используется как base для парсинга ссылок)

Это важно при cross-path/cross-host редиректах - без этого относительные `<a href="...">` разрешались бы относительно неправильной базы.

## CI

`.github/workflows/test.yml` запускает `pytest` на push/PR в main/master, матрица Python 3.10 / 3.11 / 3.12 на ubuntu-latest. Достаточно запушить - тесты погонятся автоматически. Бейдж в шапке README отражает статус последнего запуска (после первого пуша подмени `USER/REPO`).

## Демо

```
python examples/demo.py            # параллель vs последовательно (день 1)
python examples/parse_demo.py      # парсинг страниц + JSON
python examples/crawl_demo.py      # обход с очередью
python examples/polite_demo.py     # rate limit + robots
python examples/resilient_demo.py  # ошибки + circuit breaker
python examples/storage_demo.py    # JSON/CSV/SQLite + readback
python examples/full_demo.py       # AdvancedCrawler с YAML-конфигом
```

## Тесты

```
pytest
```

Используется aioresponses - реальная сеть для тестов не нужна.

## Структура проекта

```
src/crawler/
  client.py          - AsyncCrawler
  advanced.py        - AdvancedCrawler
  parser.py          - HTMLParser
  queue.py           - CrawlerQueue
  concurrency.py     - SemaphoreManager
  rate_limiter.py    - RateLimiter
  robots.py          - RobotsParser, RobotsBlocked
  errors.py          - CrawlerError + classify_exception
  retry.py           - RetryStrategy, CircuitBreaker
  storage.py         - DataStorage, JSONStorage, CSVStorage, SQLiteStorage
  sitemap.py         - SitemapParser
  stats.py           - CrawlerStats
  config.py          - CrawlerConfig (YAML)
  logging_setup.py   - setup_logging() с RotatingFileHandler
  cli.py             - CLI entry point
  _utils.py          - BoundedDict (LRU-like для внутренних кэшей)
.github/workflows/
  test.yml           - GitHub Actions: pytest на 3 версиях Python
examples/
  demo.py
  parse_demo.py
  crawl_demo.py
  polite_demo.py
  resilient_demo.py
  storage_demo.py
  full_demo.py
  example_config.yaml
tests/
  test_client.py / test_parser.py / test_queue.py / test_concurrency.py
  test_crawl.py / test_rate_limiter.py / test_robots.py
  test_errors.py / test_retry.py / test_circuit.py
  test_storage.py / test_sitemap.py / test_stats.py
  test_config.py / test_advanced.py / test_utils.py
  test_config.py / test_advanced.py
```
