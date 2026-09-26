from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from dto import AvitoConfig

_CURRENT_DIR = Path(__file__).resolve().parent

# python-dotenv не входит в requirements парсера: без него переменные
# берутся только из окружения процесса.
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    for parent in [_CURRENT_DIR, *_CURRENT_DIR.parents]:
        env_file = parent / ".env"
        if env_file.is_file():
            load_dotenv(env_file, override=False)
            break

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")


def _substitute_env(val: Any) -> Any:
    """Подставляет значения переменных окружения для строк вида ${VAR} или ${VAR:-default}."""
    if isinstance(val, str):
        def _repl(match: re.Match) -> str:
            var_name = match.group(1)
            default_val = match.group(2) if match.group(2) is not None else ""
            return os.environ.get(var_name, default_val)

        return _ENV_PATTERN.sub(_repl, val)
    if isinstance(val, list):
        return [_substitute_env(item) for item in val]
    return val


def _parse_urls(raw: Any) -> list[str]:
    """Приводит строковое или списковое представление URL к списку строк."""
    if isinstance(raw, list):
        result = []
        for item in raw:
            item_str = str(_substitute_env(item)).strip()
            if item_str.startswith("[") and item_str.endswith("]"):
                try:
                    result.extend(json.loads(item_str))
                    continue
                except Exception:
                    pass
            if item_str:
                result.append(item_str)
        return result

    if isinstance(raw, str):
        val = _substitute_env(raw).strip()
        if val.startswith("[") and val.endswith("]"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                pass
        if "\n" in val:
            return [x.strip() for x in val.split("\n") if x.strip()]
        if "," in val:
            return [x.strip() for x in val.split(",") if x.strip()]
        if val:
            return [val]

    return []


def _parse_bool(raw: Any, default: bool = False) -> bool:
    """Безопасное приведение к булеву типу."""
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    val = str(_substitute_env(raw)).strip().lower()
    return val in ("true", "1", "yes", "on", "t")


def _parse_int(raw: Any, default: int = 10) -> int:
    """Безопасное приведение к целому числу."""
    if isinstance(raw, int):
        return raw
    try:
        val = str(_substitute_env(raw)).strip()
        return int(val)
    except (ValueError, TypeError):
        return default


def _parse_str_or_none(raw: Any) -> str | None:
    """Приведение к строке или None при пустом значении."""
    if raw is None:
        return None
    val = str(_substitute_env(raw)).strip()
    return val if val else None


def load_avito_config(path: str = "config.toml") -> AvitoConfig:
    """
    Загружает конфигурацию парсера Avito.
    Поддерживает:
      1. Чтение config.toml.
      2. Разрешение плейсхолдеров ${VAR:-default} внутри значений TOML.
      3. Прямое переопределение ключевых полей (urls, use_bypass_api,
         cookies_api_key, proxy_string, count) из основного .env проекта / переменных окружения.
    """
    p = Path(path)
    if not p.is_file():
        candidates = [
            _CURRENT_DIR / p.name,
            _CURRENT_DIR / path,
        ]
        for cand in candidates:
            if cand.is_file():
                p = cand
                break

    with open(p, "rb") as f:
        data = tomllib.load(f)

    avito = data.get("avito", {})

    # Рекурсивная подстановка ${ENV:-default} во всех полях секции
    for key, val in list(avito.items()):
        avito[key] = _substitute_env(val)

    # Приоритетная подгрузка и типизация 5 ключевых полей из основного .env / окружения:
    # 1. urls
    if "AVITO_URLS" in os.environ:
        avito["urls"] = _parse_urls(os.environ["AVITO_URLS"])
    elif "AVITO_URL" in os.environ:
        avito["urls"] = _parse_urls(os.environ["AVITO_URL"])
    else:
        avito["urls"] = _parse_urls(avito.get("urls", []))

    # 2. use_bypass_api
    if "AVITO_USE_BYPASS_API" in os.environ:
        avito["use_bypass_api"] = _parse_bool(os.environ["AVITO_USE_BYPASS_API"])
    else:
        avito["use_bypass_api"] = _parse_bool(avito.get("use_bypass_api", False))

    # 3. cookies_api_key
    if "AVITO_COOKIES_API_KEY" in os.environ:
        avito["cookies_api_key"] = _parse_str_or_none(os.environ["AVITO_COOKIES_API_KEY"])
    else:
        avito["cookies_api_key"] = _parse_str_or_none(avito.get("cookies_api_key"))

    # 4. proxy_string
    if "AVITO_PROXY_STRING" in os.environ:
        avito["proxy_string"] = _parse_str_or_none(os.environ["AVITO_PROXY_STRING"])
    else:
        avito["proxy_string"] = _parse_str_or_none(avito.get("proxy_string"))

    # 5. count
    if "AVITO_COUNT" in os.environ:
        avito["count"] = _parse_int(os.environ["AVITO_COUNT"], default=10)
    else:
        avito["count"] = _parse_int(avito.get("count", 10), default=10)

    return AvitoConfig(**avito)


def save_avito_config(config: dict, path: str = "config.toml"):
    p = Path(path)
    if not p.is_file() and (_CURRENT_DIR / p.name).is_file():
        p = _CURRENT_DIR / p.name
    with p.open("wb") as f:
        tomli_w.dump(config, f)
