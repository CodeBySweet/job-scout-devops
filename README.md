# Job Scout (DevOps/Cloud) – 24h

Small FastAPI service + CLI that aggregates job posts from RSS/Atom feeds,
filters to DevOps/Cloud/SRE roles, and returns only the last N hours (24h by default).

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# CLI (one-off)
KEYWORDS="devops,cloud engineer,sre" HOURS=24 python app.py --once
# API
uvicorn app:app --host 0.0.0.0 --port 8000
# then open http://localhost:8000/jobs