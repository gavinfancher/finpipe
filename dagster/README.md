# finpy-dagster

## Structure

```
dagster/
├── setup.sh
├── env.example
├── pyproject.toml
│
└── pipelines/
    ├── definitions.py    # Entry point
    ├── resources.py      # Connections
    ├── jobs.py
    ├── sensors.py
    ├── schedules.py
    └── assets/
        ├── bronze.py
        ├── silver.py
        └── gold.py
```

## Quick Start

```bash
chmod +x setup.sh
./setup.sh
vim .env
source .venv/bin/activate
dagster dev
```
