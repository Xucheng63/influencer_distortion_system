# Playwright's official image ships Chromium + all system libs preinstalled,
# matching the pinned playwright==1.44.0 in requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Ensure the Chromium browser binary is present (image already has it, but this
# is a safe no-op that guarantees the version matches the pip package).
RUN playwright install chromium

# Copy the application code.
COPY . .

# SQLite lives in ./data by default (see app/core/database.py). Make sure it exists.
RUN mkdir -p /app/data

# Railway provides $PORT at runtime; default to 8000 for local runs.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
