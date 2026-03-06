# Build context: backend/ directory
# docker build -f scraper_service/Dockerfile -t lawmate-scraper .

FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium + all OS-level dependencies for Playwright
RUN playwright install chromium --with-deps

# Copy entire backend codebase (scraper_service imports from app.*)
COPY . .

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uvicorn", "scraper_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
