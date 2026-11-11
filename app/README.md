# Flight Prices app

The search engine of [Flight Prices](https://github.com/flaviorighi/ha-flight-prices): it searches Ryanair
and Google Flights for the cheapest weekend trips and keeps what it found. The Flight Prices integration
connects Home Assistant to it, with the same sensors, card and settings as before.

The searches run outside Home Assistant: their libraries, and a Google Flights round that takes an hour,
stay away from the process that runs your home.
