FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FITPAY_DATABASE_URL=sqlite:////data/fitpay.db

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[postgres]"

# Run as a normal user, with a writable folder for the SQLite database.
RUN useradd --create-home fitpay && mkdir /data && chown fitpay /data
USER fitpay

EXPOSE 8000
CMD ["uvicorn", "fitpay.main:app", "--host", "0.0.0.0", "--port", "8000"]
