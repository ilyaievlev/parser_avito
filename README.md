# parser_avito (fork)

## About this fork

This repository is a fork of [Duff89/parser_avito](https://github.com/Duff89/parser_avito).

The original project provides an Avito parser with proxy, anti-blocking,
filtering and export functionality.

This fork is adapted for use as a data collector in my **Estate Intelligence**
ML/MLOps project.

### My changes

- Added `apartment_ml.py` — normalize Avito listings (`Item`) into flat `dict`s for ML
- Added `fetch_ml_data.py` — collect listings and return `list[dict]` (no Excel dependency)
- Kept the upstream parser core untouched; ML helpers sit on top of it
- Left GUI / Excel / notifications available, but the primary path for Estate Intelligence is programmatic collection

Original project: [Duff89/parser_avito](https://github.com/Duff89/parser_avito)

---

## Quick start (ML data)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

1. Put apartment search URLs into `config.toml` (`urls`, `count`, proxy/cookies if needed).
2. Collect data:

```bash
python fetch_ml_data.py
```

Or in code:

```python
from load_config import load_avito_config
from parser_cls import AvitoParse
from fetch_ml_data import collect_ads
from apartment_ml import to_ml_dicts

parser = AvitoParse(load_avito_config("config.toml"))
rows = to_ml_dicts(collect_ads(parser))  # list[dict] for Postgres / training
```

Each row includes fields useful for price estimation, e.g. `price`, `rooms`,
`area_m2`, `floor`, `floors_total`, `lat` / `lng`, `metro_nearest`, `address`,
`description`, plus `params_raw` when Avito exposes them.

---

## Upstream docs

- [Developer docs](docs/DOCS.md)
- [Anti-blocking](docs/ANTIBLOCK.md)
- [Notifications](docs/NOTIFICATIONS.md)
- [Docker](docs/DOCKER.md)
