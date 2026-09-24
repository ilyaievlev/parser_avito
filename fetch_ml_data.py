"""
Разовый сбор объявлений → list[dict] для ML / Postgres.

Запуск:
  1) В config.toml укажи urls на поиск квартир, count = число страниц
  2) python fetch_ml_data.py

По умолчанию печатает первый dict и пишет всё в result/ml_sample.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from apartment_ml import to_ml_dicts
from load_config import load_avito_config
from models import ItemsResponse
from parser_cls import AvitoParse


def collect_ads(parser: AvitoParse) -> list:
    """Те же шаги, что в parse(), но возвращает list[Item] без save/notify."""
    collected = []

    api_urls = {}
    for source_url in parser.config.urls:
        try:
            api_urls[source_url] = parser.url_converter.convert(source_url)
        except Exception as err:
            logger.error(f"Не удалось преобразовать {source_url}: {err}")

    for source_url, api_url in api_urls.items():
        for page in range(1, parser.config.count + 1):
            logger.info(f"{source_url} page={page}")
            json_data = parser.fetch_api_data(api_url=api_url, page=page)
            if not json_data:
                time.sleep(parser.config.pause_between_links)
                continue

            catalog = parser._extract_api_catalog(json_data)
            try:
                ads_models = ItemsResponse(**catalog)
            except ValidationError as err:
                logger.error(f"Валидация: {err}")
                continue

            ads = parser._clean_null_ads(ads=ads_models.items)
            ads = parser._add_seller_to_ads(ads=ads)
            ads = parser._add_promotion_to_ads(ads=ads)
            if not ads:
                break

            # фильтры из конфига (цена, слова и т.д.)
            # для первой полной выгрузки удали database.db — иначе отсечёт «уже виденные»
            filtered = parser.filter_ads(ads=ads)
            collected.extend(filtered)

            time.sleep(parser.config.pause_between_links)

    return collected


def main():
    config = load_avito_config("config.toml")
    parser = AvitoParse(config)

    ads = collect_ads(parser)
    rows = to_ml_dicts(ads)

    print(f"Собрано объявлений: {len(rows)}")
    if rows:
        print("Пример первой записи:")
        print(json.dumps(rows[0], ensure_ascii=False, indent=2, default=str))

    out = Path("result") / "ml_sample.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Все данные → {out}")

    # дальше у себя:
    # for row in rows:
    #     cur.execute("INSERT INTO apartments (...) VALUES (...)", row)
    return rows


if __name__ == "__main__":
    main()
