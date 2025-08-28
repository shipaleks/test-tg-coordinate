# Use Python 3.12 slim as base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# No system packages required (all deps use prebuilt wheels)

# Copy project files
COPY pyproject.toml ./
COPY requirements.txt ./
COPY src/ ./src/
# Copy full docs directory (avoids lstat issues with globs on some builders)
COPY docs/ ./docs/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -e .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app

# Pre-create data directory with correct permissions for volume mount
RUN mkdir -p /data && chown app:app /data && chmod 755 /data

USER app

# Expose port (Cloud Run expects 8080 by default, but we honor $PORT)
EXPOSE 8080

# Run the application
CMD ["python", "-m", "src.main"] 