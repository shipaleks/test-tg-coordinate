# Use Python 3.12 slim as base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY requirements.txt ./
COPY src/ ./src/
COPY docs/*.gif ./docs/
COPY docs/*.mp4 ./docs/
COPY docs/*.PNG ./docs/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -e .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app

# Pre-create data directory with correct permissions for volume mount
RUN mkdir -p /data && chown app:app /data && chmod 755 /data

USER app

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "src.main"] 