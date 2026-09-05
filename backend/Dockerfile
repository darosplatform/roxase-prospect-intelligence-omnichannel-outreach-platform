# Pinned to the exact patch version this codebase is developed and tested
# against (verified via `python3.12 --version` in the dev/CI environment),
# not a guessed patch — avoid bumping it without re-running the full suite.
FROM python:3.12.3-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
