# Flight Prices

This app does the searching. Settings, sensors and the dashboard card come from the **Flight Prices
integration**, which needs the app.

## Setup

1. Start the app. Home Assistant finds it: **Settings → Devices & services** shows Flight Prices as
   discovered.
2. Add it and set up a search: departure airports, destinations, days and hours. Every search you add
   later uses the same app.

Searches that existed before the app keep what they had found: they move to the app the first time
the integration connects, without searching again.

## Options

- **Log level**: `debug` writes every request in the app's log.

## Network

Home Assistant on this machine reaches the app on the internal network, so the port stays closed.
Open it only for a Home Assistant on another machine: anyone who can reach it can start searches, and
too many Google Flights searches get your connection a captcha.

## Without Home Assistant OS

The same image runs with Docker or Podman, next to a Home Assistant in a container:

```sh
docker run -d --name flight-prices --restart unless-stopped \
  -p 8765:8765 -v flight-prices:/data \
  ghcr.io/flaviorighi/flight-prices-app:1.0.0b0
```

Then add the integration and enter `http://<host>:8765`.
