# BugTrack Pro

BugTrack Pro is a portfolio-ready full-stack issue-tracking application built with Python and FastAPI. It demonstrates REST API development, authentication, relational database design, validation, testing, Docker deployment, CI, logging, and production health checks.

## Run locally

```powershell
cd bugtrack-pro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The API documentation is available at http://127.0.0.1:8000/docs.

The default database is SQLite, so no external database is required. To use PostgreSQL, set `DATABASE_URL`, for example:

```text
postgresql+psycopg://user:password@localhost:5432/bugtrack
```

For a real deployment, set a long random `SECRET_KEY` environment variable and use HTTPS.

## Run tests

```powershell
pytest -q
```

## Run with Docker

```powershell
docker build -t bugtrack-pro .
docker run --rm -p 8000:8000 bugtrack-pro
```

## Portfolio checklist

- Add screenshots and an architecture diagram to this README.
- Include a live demo link after deployment.
- Add a short API example from `/docs`.
- Record a small demo showing registration, issue creation, status updates, and comments.
