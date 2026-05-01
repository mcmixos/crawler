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
examples/
  demo.py          - пример с замером времени
tests/
  test_client.py   - pytest + aioresponses
```
