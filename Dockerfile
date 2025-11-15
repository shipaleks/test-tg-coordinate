# Use Python 3.12 slim as base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY pyproject.toml ./
COPY src/ ./src/
COPY docs/ ./docs/

# Install package in editable mode
RUN pip install --no-cache-dir -e .

# Expose port (must match PORT env var in Koyeb)
EXPOSE 8000

# Run the application (Koyeb will manage healthcheck via HTTP endpoints)
CMD ["python", "-m", "src.main"] 