# Flight Prices for Home Assistant

[![Downloads](https://img.shields.io/github/downloads/flaviorighi/ha-flight-prices/total?label=downloads)](https://github.com/flaviorighi/ha-flight-prices/releases)
[![Installations](https://img.shields.io/badge/dynamic/json?label=installations&query=%24.flight_prices.total&url=https%3A%2F%2Fanalytics.home-assistant.io%2Fcustom_integrations.json)](https://analytics.home-assistant.io/)

Cheapest return flights for the coming weeks that fit around your working week, as Home Assistant sensors.

Flight sites let you search "Friday to Sunday", but most of what they find leaves on Friday morning or comes back on Sunday morning, and that costs two days off. Flight Prices searches by **departure hours** as well as days: out on Friday after 19:00, back on Sunday after 14:00, for each of the next 8 weekends, from one or more airports to anywhere or to a list of places. Any other pattern works too, such as out on Thursday evening and back on Monday. Add as many searches as you like; all of it can be changed later from **Configure**.

Because the prices are sensors, the rest of your home can act on them: a notification when a weekend drops under a price, a trip pencilled into the family calendar (see [Automations](#automations)).

![The dashboard card of the integration, with made-up data](https://raw.githubusercontent.com/flaviorighi/ha-flight-prices/main/docs/images/card.png)

*The card that comes with the integration, with made-up data.*

Prices come from two sources, both read without an API key:

- **Ryanair**, through the fare finder behind ryanair.com. One request per departure airport and week returns the cheapest return fare to every destination, so this is the source that can search **anywhere**. Ryanair group flights only.
- **Google Flights**, read from its search page with [fast-flights](https://github.com/AWeirdDev/flights) building the search: every airline, but only for a list of destinations, one one-way search per request. Outbound and return are searched separately and added up: exact for low-cost airlines, an upper bound for airlines that price return trips lower. The booking links open Google Flights with the same hours and stops: a return search when one airline flies both ways (it may show a lower return fare), two one-way searches when the trip pairs two airlines.

> Neither source is an official API. They can change or stop answering at any time, and reading Google Flights automatically is against Google's terms of service. The integration keeps the requests few and spread out (see below) and stops at the first sign of a block. Use it for personal use, at your own risk.

## What you get

One device per search, with these sensors (prices for one adult, return trip):

| Sensor | State | Attributes |
|---|---|---|
| Week 1 … Week N | Cheapest trip of that week | `outbound_date`, `return_date`, the search (`origins`, `outbound_hours` and `return_hours` as `[from, to]`), `destinations_found`, `trips`: up to 30 trips, cheapest first, one per destination and departure airport, with city, country, country code, departure airport, price, airline, source, outbound and return flights (times, flight numbers, stops) and a booking link (`link`; with two airlines on Google Flights the trip is two tickets, so `link` is the outbound search and `return_link` the return one) |
| Cheapest trip | Cheapest trip of all the weeks | `outbound_date`, `return_date`, `city`, `trip` |
| One per destination, with a list | Cheapest trip to it over the weeks | `city`, `outbound_date`, `weeks` (price per week), `trip` |
| Ryanair search, Google Flights search (diagnostic) | Last successful search | `last_attempt`, `error`, `trips`, `running` |

![The sensors of one search](https://raw.githubusercontent.com/flaviorighi/ha-flight-prices/main/docs/images/device.png)

Each week keeps one trip per destination and departure airport, the cheapest across sources, so a dashboard can filter by airport. Every trip comes back to the airport it left from. The lists in the attributes are not recorded in the history.

## Dashboard card

The integration ships a card, **Flight Prices**, already in the card picker: nothing to install or add as a resource. It shows one search:

- a summary with the cheapest trip, how many destinations were found and when each source last searched (red when a source keeps failing);
- a filter by departure airport, remembered on each device;
- one block per week with its cheapest destinations, each destination only once on the page: in rounds from the cheapest, every week gets its first, then its second and so on, so each destination sits in its cheapest week when there is room and no week is left empty. A trip that is cheaper in another week says so;
- the whole list of a week on a tap on its title;
- a tap on a trip opens the booking page; trips that are two tickets have an outbound and a return button.

```yaml
type: custom:flight-prices-card
device_id: <the search>   # optional with only one search
title: Weekends           # optional, the search's name by default
per_week: 3               # destinations per week before "show the others"
unique: true              # false: every week shows its own cheapest destinations
```

It reads the sensors of the search, so it follows the options: change the weeks, airports or hours and the card follows. In a sections view it takes the whole width and lays the weeks out in columns.

## Automations

The sensors work like any other in Home Assistant, so a price can trigger whatever you like. In these examples the search is called *Weekends from Milan*; entity IDs follow the name of your search and the language of Home Assistant, so check yours in the search's device.

**A notification when a weekend gets cheap**, with the booking page on a tap:

```yaml
automation:
  - alias: Cheap weekend
    triggers:
      - trigger: numeric_state
        entity_id: sensor.weekends_from_milan_cheapest_trip
        below: 60
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: >-
            {{ trigger.to_state.attributes.city }} for
            {{ trigger.to_state.state | round }} {{ trigger.to_state.attributes.unit_of_measurement }}
          message: >-
            {{ trigger.to_state.attributes.outbound_date }} to {{ trigger.to_state.attributes.return_date }},
            {{ trigger.to_state.attributes.trip.airline }}
          data:
            clickAction: "{{ trigger.to_state.attributes.trip.link }}"  # Android; url on iOS
```

**A trip pencilled into the family calendar** when one place you watch drops under a price, so everyone at home sees it. The destination sensors (one per place in the list) hold the cheapest trip to it over all the weeks:

```yaml
automation:
  - alias: Lisbon weekend in the calendar
    triggers:
      - trigger: numeric_state
        entity_id: sensor.weekends_from_milan_lis
        below: 80
    actions:
      - variables:
          trip: "{{ trigger.to_state.attributes.trip }}"
      - action: calendar.create_event
        target:
          entity_id: calendar.family
        data:
          summary: "Lisbon? {{ trip.price | round }} {{ trigger.to_state.attributes.unit_of_measurement }}, {{ trip.airline }}"
          description: "{{ trip.link }}"
          start_date: "{{ as_datetime(trip.outbound.departure).date() }}"
          end_date: "{{ (as_datetime(trip['return'].departure) + timedelta(days=1)).date() }}"
```

Both trigger when the price goes under the figure, not again at every search while it stays there. The attributes of each sensor are in [What you get](#what-you-get).

## Requests

| Source | Requests per search | Default interval |
|---|---|---|
| Ryanair | airports × weeks (2 × 8 = 16), one second apart | 3 hours |
| Google Flights | weeks × Google destinations × Google departure airports × 2 (8 × 5 × 1 × 2 = 80), 20 to 30 seconds apart, about half an hour in all | 24 hours |

The Google search runs in the background. Its round stops at the first block (consent page, captcha, HTTP 429) or after 5 errors in a row, and is tried again at the next interval. A return is not searched when the outbound found nothing. Results are saved, so a restart of Home Assistant or a change of options shows them at once without searching again, unless the search itself changed.

> [!CAUTION]
> Too many automatic searches get your home's internet connection a captcha from Google, for every device at home. Before saving, the form shows how many requests a Google setup makes, with a warning from 200 a day; it refuses a setup over **300 requests a day** and an interval under **12 hours**. Once a day (the default) is recommended. See the [configuration guide](https://github.com/flaviorighi/ha-flight-prices/blob/main/docs/configuration.md#how-many-requests) for the numbers.

## Installation

Flight Prices has two parts: the **app** searches, outside Home Assistant, and the **integration** brings what it finds into Home Assistant as sensors, with the dashboard card. Install the app first.

**The app, on Home Assistant OS**: **Settings → Apps → Install app**, then **⋮ → Repositories**, add `https://github.com/flaviorighi/ha-flight-prices`, install **Flight Prices** and start it. Home Assistant finds it by itself: Flight Prices shows up as discovered in **Settings → Devices & services**.

**The app, with Docker** (Home Assistant in a container, or another machine):

```sh
docker run -d --name flight-prices --restart unless-stopped   -p 8765:8765 -v flight-prices:/data   ghcr.io/flaviorighi/flight-prices-app:1.0.0b0
```

The integration then asks for its address, such as `http://192.168.1.10:8765`. Anyone who can reach the port can start searches from your connection: keep it inside your network.

**The integration**, from the **Marketplace**, which replaced HACS in Home Assistant 2026.11: **Settings → Marketplace → Add from link**, paste `https://github.com/flaviorighi/ha-flight-prices`, install **Flight Prices** and restart Home Assistant. Updates then appear in **Settings** like those of Home Assistant. With HACS, on Home Assistant 2026.10: add this repository as a custom repository (category Integration), install **Flight Prices** and restart. By hand: copy `custom_components/flight_prices` into your `config/custom_components` and restart.

**From version 0.x**: the searches you have wait for the app (a repair says so). Once the app runs they move to it by themselves, with what they had found, so nothing is searched again before its time.

Then add the integration in **Settings → Devices & services**. The options can be changed later from the integration's **Configure** button. The **[configuration guide](https://github.com/flaviorighi/ha-flight-prices/blob/main/docs/configuration.md)** explains each option, with images and ready-made setups.

| Option | What it is | Default |
|---|---|---|
| Departure airports | IATA codes; every trip comes back to the airport it left from | none, required |
| Destinations | IATA codes of airports or cities (`LON` is every London airport) | empty: anywhere (Ryanair only) |
| Leave out countries | ISO codes, such as `IT` for flights within Italy; applied to what was found, so changing it needs no new search | none |
| Sources | Ryanair, Google Flights or both | Ryanair |
| Google Flights destinations | Searched only on Google Flights, so Ryanair can keep searching anywhere | empty: the destinations above |
| Google Flights departure airports | Only these of the departure airports are searched on Google Flights, for example the ones Ryanair does not cover well | empty: all of them |
| Weeks | How many weeks ahead, from the coming one (1 to 12) | 8 |
| Outbound day and departure hours | Any weekday; hours from 0 to 24, 24 being midnight | Friday, 19 to 24 |
| Return day and departure hours | Any weekday; a return day before the outbound day means the week after (Saturday to Monday) | Sunday, 14 to 24 |
| Direct flights only | Google Flights only: Ryanair always flies direct | yes |
| Ryanair / Google Flights search every | Hours between two searches: Ryanair 1 to 24, Google Flights 12 to 168 | 3 / 24 |

## Development

```
pip install -r requirements_test.txt
pytest                                 # the integration, with the app faked
ruff check . && ruff format --check .
node --test "tests/card/*.test.mjs"    # the dashboard card, Node.js 24

cd app
pip install -r requirements_test.txt   # in another environment: the app needs no Home Assistant
pytest                                 # the search engine
python -m flight_prices_engine --data ./data --port 8765
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Roadmap

- An event when a price drops below the lowest seen so far, for a destination or a week
- More than one passenger
- Search only the weeks you are free, read from a Home Assistant calendar
- Destinations by region, such as "Europe only", instead of a list of airports

## Credits

Google Flights searches are built with [fast-flights](https://github.com/AWeirdDev/flights).

Built with the help of AI coding agents (Claude Code), under the author's direction.

## License

MIT. Ryanair and Google Flights are trademarks of their owners; this project is not affiliated with them.
