# Multi-purpose image: runs both the API and the worker (different CMD).
FROM python:3.12-slim

# Avoid .pyc files, unbuffered logs (important for k8s log capture).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a non-root user (security best practice / many clusters enforce it).
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Default = API. The worker Deployment overrides this command.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
