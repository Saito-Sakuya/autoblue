FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/data/config.yaml \
    STATE_PATH=/data/state.sqlite

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends cron ca-certificates tzdata whiptail \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY scripts /app/scripts
COPY entrypoint.sh /app/entrypoint.sh

# daily housekeeping: prune sqlite
RUN echo "17 3 * * * root /app/scripts/cron_housekeeping" > /etc/cron.d/xrss_housekeeping \
 && chmod 0644 /etc/cron.d/xrss_housekeeping \
 && crontab /etc/cron.d/xrss_housekeeping

VOLUME ["/data"]

ENTRYPOINT ["/app/entrypoint.sh"]
