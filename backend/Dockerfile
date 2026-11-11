FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/.env.example /app/backend/.env.example
RUN pip install --no-cache-dir \
    google-antigravity \
    gnani-vachana \
    google-genai \
    fastapi \
    uvicorn \
    pydantic \
    pydantic-settings \
    python-dotenv \
    websockets \
    httpx \
    pyjwt \
    pytest \
    pytest-asyncio

COPY backend /app/backend
COPY data /app/data

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

