FROM python:3.10-slim

# Add labels for better container management
LABEL maintainer="VideoCatcher"
LABEL description="Video download service supporting multiple platforms"
LABEL version="1.0"

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set Python environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Install dependencies
RUN apt-get update && \
    apt-get install -y \
    chromium \
    chromium-driver \
    ffmpeg \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create necessary directories with correct permissions
RUN mkdir -p /app/downloads /app/cookies /app/chrome_data && \
    chown -R appuser:appuser /app && \
    chmod -R 777 /app/downloads /app/cookies /app/chrome_data

# Set Chrome paths
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
RUN chown -R appuser:appuser /app

USER appuser

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

EXPOSE 5000

CMD ["python", "app.py"]