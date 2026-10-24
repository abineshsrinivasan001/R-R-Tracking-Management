# ---------- Base Image ----------
FROM python:3.12-slim

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Kolkata

# Set working directory
WORKDIR /app

# Install system dependencies + cron
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Copy dependency file first (for docker caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create cron jobs (Runs daily at 08:00 AM)
RUN echo "0 8 * * * cd /app && /usr/local/bin/python manage.py run_daily_server_check >> /app/cron_server_check.log 2>&1" > /etc/cron.d/app-cron && \
    chmod 0644 /etc/cron.d/app-cron && \
    crontab /etc/cron.d/app-cron

# Expose Django port
EXPOSE 8056

# Start cron and Django
# 1. Export env vars so cron can see database and app environment
# 2. Touch log file so tail -f doesn't fail
# 3. Start cron daemon
# 4. Run database migrations
# 5. Start Django development server
CMD printenv | grep -v "no_proxy" > /etc/environment && \
    touch /app/cron_server_check.log && \
    cron && \
    python manage.py migrate --noinput && \
    python manage.py runserver 0.0.0.0:8056

