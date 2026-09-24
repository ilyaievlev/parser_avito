"""
Преобразование объявления Avito (models.Item) в dict признаков для ML-оценки стоимости квартиры.

Использование в своём проекте:
    from apartment_ml import to_ml_dict, to_ml_dicts

    features = to_ml_dict(ad)          # один Item -> dict
    rows = to_ml_dicts(ads)            # list[Item] -> list[dict]
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from tzlocal import get_localzone

from models import Item

# Типичный заголовок: "2-к. квартира, 54 м², 3/9 эт." / "Студия, 28,5 м², 5/17 эт."
_ROOMS_RE = re.compile(r"(\d+)\s*-?\s*к(?:\.|омн)", re.IGNORECASE)
_STUDIO_RE = re.compile(r"студи", re.IGNORECASE)
_AREA_RE = re.compile(r"(\d+[.,]?\d*)\s*м(?:²|2)", re.IGNORECASE)
_FLOOR_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*эт", re.IGNORECASE)


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def _parse_title_realty(title: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rooms": None,
        "is_studio": False,
        "area_m2": None,
        "floor": None,
        "floors_total": None,
    }
    if not title:
        return result

    if _STUDIO_RE.search(title):
        result["is_studio"] = True
        result["rooms"] = 0

    rooms_match = _ROOMS_RE.search(title)
    if rooms_match:
        result["rooms"] = int(rooms_match.group(1))
        result["is_studio"] = False

    area_match = _AREA_RE.search(title)
    if area_match:
        result["area_m2"] = _parse_float(area_match.group(1))

    floor_match = _FLOOR_RE.search(title)
    if floor_match:
        result["floor"] = int(floor_match.group(1))
        result["floors_total"] = int(floor_match.group(2))

    return result


def _extract_coords(ad: Item) -> tuple[float | None, float | None, str | None]:
    if not ad.coords or not isinstance(ad.coords, dict):
        return None, None, None
    lat = _parse_float(ad.coords.get("lat"))
    lng = _parse_float(ad.coords.get("lng"))
    address_user = ad.coords.get("address_user")
    return lat, lng, address_user if isinstance(address_user, str) else None


def _extract_metro(ad: Item) -> list[dict[str, Any]]:
    metros: list[dict[str, Any]] = []
    if not ad.geo or not ad.geo.geoReferences:
        return metros

    for ref in ad.geo.geoReferences:
        if not isinstance(ref, dict):
            continue
        name = ref.get("content") or ref.get("title") or ref.get("name")
        if not name:
            continue
        metros.append(
            {
                "name": name,
                "after": ref.get("after"),
                "colors": ref.get("colors"),
            }
        )
    return metros


def _walk_iva_params(ad: Item) -> dict[str, Any]:
    """Собирает пары параметр→значение из iva (если Avito их отдал в каталоге)."""
    params: dict[str, Any] = {}
    if not ad.iva:
        return params

    for steps in ad.iva.values():
        if not steps:
            continue
        for step in steps:
            payload = step.payload or {}
            raw_params = payload.get("params") or payload.get("list") or []
            if isinstance(raw_params, list):
                for item in raw_params:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("title") or item.get("name") or item.get("attribute")
                    value = (
                        item.get("description")
                        or item.get("value")
                        or item.get("text")
                        or item.get("content")
                    )
                    if key and value is not None:
                        params[str(key)] = value

            # иногда параметры лежат плоско в payload
            for key in ("title", "text", "description", "name"):
                if key in payload and isinstance(payload[key], str) and payload[key]:
                    # не дублируем служебные поля без пары
                    pass

    return params


def _apply_known_params(features: dict[str, Any], params: dict[str, Any]) -> None:
    """Маппинг частых названий характеристик Avito → поля фичей."""
    aliases = {
        "количество комнат": "rooms",
        "комнат": "rooms",
        "общая площадь": "area_m2",
        "площадь": "area_m2",
        "жилая площадь": "living_area_m2",
        "площадь кухни": "kitchen_area_m2",
        "этаж": "floor_raw",
        "этажей в доме": "floors_total",
        "тип дома": "house_type",
        "материал стен": "house_type",
        "год постройки": "year_built",
        "ремонт": "renovation",
        "балкон или лоджия": "balcony",
        "санузел": "bathroom",
        "высота потолков": "ceiling_height",
        "мебель": "furniture",
        "техника": "appliances",
        "вид сделки": "deal_type",
        "тип жилья": "property_type",
        "застройщик": "developer",
        "жк": "residential_complex",
        "срок сдачи": "delivery_date",
    }

    normalized = {str(k).strip().lower(): v for k, v in params.items()}

    for src, dst in aliases.items():
        if src not in normalized:
            continue
        value = normalized[src]
        if dst == "rooms" and features.get("rooms") is None:
            if isinstance(value, str) and _STUDIO_RE.search(value):
                features["rooms"] = 0
                features["is_studio"] = True
            else:
                num = re.search(r"\d+", str(value))
                if num:
                    features["rooms"] = int(num.group(0))
        elif dst == "area_m2" and features.get("area_m2") is None:
            features["area_m2"] = _parse_float(re.sub(r"[^\d.,]", "", str(value)))
        elif dst in {"living_area_m2", "kitchen_area_m2", "ceiling_height"}:
            features[dst] = _parse_float(re.sub(r"[^\d.,]", "", str(value)))
        elif dst == "floors_total" and features.get("floors_total") is None:
            num = re.search(r"\d+", str(value))
            if num:
                features["floors_total"] = int(num.group(0))
        elif dst == "year_built":
            num = re.search(r"\d{4}", str(value))
            if num:
                features["year_built"] = int(num.group(0))
        elif dst == "floor_raw":
            # "3 из 9" / "3/9"
            floor_match = re.search(r"(\d+)\s*(?:из|/)\s*(\d+)", str(value))
            if floor_match:
                if features.get("floor") is None:
                    features["floor"] = int(floor_match.group(1))
                if features.get("floors_total") is None:
                    features["floors_total"] = int(floor_match.group(2))
            else:
                num = re.search(r"\d+", str(value))
                if num and features.get("floor") is None:
                    features["floor"] = int(num.group(0))
        else:
            features[dst] = value


def _published_at(ad: Item) -> str | None:
    if not ad.sortTimeStamp:
        return None
    return (
        datetime.fromtimestamp(ad.sortTimeStamp / 1000, tz=get_localzone())
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def to_ml_dict(ad: Item) -> dict[str, Any]:
    """
    Item -> dict признаков для ML.

    price — целевая переменная; остальные поля — признаки / метаданные.
    """
    title_parts = _parse_title_realty(ad.title)
    lat, lng, address_user = _extract_coords(ad)
    metros = _extract_metro(ad)
    iva_params = _walk_iva_params(ad)

    price = ad.priceDetailed.value if ad.priceDetailed else None
    area = title_parts["area_m2"]
    price_per_m2 = None
    if price is not None and area:
        price_per_m2 = round(price / area, 2)

    record: dict[str, Any] = {
        # идентификаторы / мета
        "id": ad.id,
        "url": f"https://www.avito.ru{ad.urlPath}" if ad.urlPath else None,
        "title": ad.title,
        "description": ad.description,
        "published_at": _published_at(ad),
        "category_id": ad.categoryId,
        "category_name": ad.category.name if ad.category else None,
        "location_id": ad.locationId,
        "location_name": ad.location.name if ad.location else None,
        "seller_id": ad.sellerId,
        "is_promotion": bool(ad.isPromotion),
        "is_reserved": bool(ad.isReserved) if ad.isReserved is not None else None,
        "total_views": ad.total_views,
        "today_views": ad.today_views,
        # целевая переменная и производные
        "price": price,
        "price_per_m2": price_per_m2,
        # признаки квартиры
        "rooms": title_parts["rooms"],
        "is_studio": title_parts["is_studio"],
        "area_m2": area,
        "living_area_m2": None,
        "kitchen_area_m2": None,
        "floor": title_parts["floor"],
        "floors_total": title_parts["floors_total"],
        "house_type": None,
        "year_built": None,
        "renovation": None,
        "balcony": None,
        "bathroom": None,
        "ceiling_height": None,
        "furniture": None,
        "appliances": None,
        "deal_type": None,
        "property_type": None,
        "developer": None,
        "residential_complex": None,
        "delivery_date": None,
        # гео
        "address": ad.geo.formattedAddress if ad.geo else None,
        "address_user": address_user,
        "lat": lat,
        "lng": lng,
        "metro": metros,
        "metro_nearest": metros[0]["name"] if metros else None,
        "metro_nearest_after": metros[0].get("after") if metros else None,
        # сырые параметры из карточки (на случай новых полей Avito)
        "params_raw": iva_params,
    }

    _apply_known_params(record, iva_params)

    # пересчёт цены за м², если площадь уточнилась из params
    if record["price"] is not None and record.get("area_m2"):
        record["price_per_m2"] = round(record["price"] / record["area_m2"], 2)

    return record


def to_ml_dicts(ads: list[Item]) -> list[dict[str, Any]]:
    """list[Item] -> list[dict] признаков для ML."""
    return [to_ml_dict(ad) for ad in ads]
