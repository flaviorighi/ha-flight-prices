# The same image runs as a Home Assistant app and with plain Docker or Podman.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLIGHT_PRICES_DATA=/data

WORKDIR /usr/src/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml README.md ./
COPY flight_prices_engine ./flight_prices_engine
RUN pip install --no-cache-dir --no-deps .

# Searches and what they found; with Docker, mount a volume here. Home Assistant mounts it
# owned by root, so the engine runs as root inside the container, like the other apps.
VOLUME /data
EXPOSE 8765

CMD ["python", "-m", "flight_prices_engine"]
