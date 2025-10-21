# API Dockerfile for Podcastfy GUI Backend
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy API requirements
COPY apps/api/pyproject.toml apps/api/README.md ./apps/api/

# Install Python dependencies
WORKDIR /app/apps/api
RUN uv pip install --system -e .

# Copy API source code
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./

# Copy existing podcastfy CLI (for reuse)
WORKDIR /app
COPY podcastfy ./podcastfy
COPY pyproject.toml requirements.txt ./
RUN uv pip install --system -r requirements.txt

# Set working directory back to API
WORKDIR /app/apps/api

# Expose port
EXPOSE 8000

# Run FastAPI with uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
