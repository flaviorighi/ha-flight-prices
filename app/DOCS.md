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

## The page

**Open Web UI**, or **Flight Prices** in the sidebar, shows what the app is doing: every search, when
each source last searched and its errors, the Google Flights requests of the last 24 hours against the
limit, and the trips of each week. It only shows: searches are set up and changed in the integration.

## Google Flights limit

Every search reads Google Flights from the same connection, so the app counts them together: it refuses
a new or larger search that would bring all of them over 300 requests a day. A search sent again as it
was, for example after a restart, is never refused.

## Options

- **Log level**: `debug` writes every request in the app's log.
- **Password**: only needed if you open the port. The page and the API then ask for it. Home Assistant
  gets it from the app by itself, and the page in the sidebar never asks for it.

## Network

Home Assistant on this machine reaches the app on the internal network, so the port stays closed.
Open it only for a Home Assistant on another machine, or to open the page without Home Assistant, and
set a password first: without one, anyone who can reach the port can start searches, and too many
Google Flights searches get your connection a captcha.

## Without Home Assistant OS

The same image runs with Docker or Podman, next to a Home Assistant in a container:

```sh
docker run -d --name flight-prices --restart unless-stopped \
  -p 8765:8765 -v flight-prices:/data \
  -e FLIGHT_PRICES_PASSWORD=choose-a-password \
  ghcr.io/flaviorighi/flight-prices-app:1.0.0b0
```

Then add the integration with the address `http://<host>:8765` and the password. The same address in
a browser opens the app's page; the browser asks for the password, with any user name.
