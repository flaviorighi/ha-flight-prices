# Configuration guide

A search has many options, and most of them have a sensible default. This guide goes through them in the order of the form, says what each one changes, and ends with a few ready-made setups. The images come from a test instance with a made-up search, "Weekends from Berlin".

- [Before you start](#before-you-start)
- [Where from, where to](#where-from-where-to)
- [Sources](#sources)
- [When](#when)
- [Before saving: the requests](#before-saving-the-requests)
- [After saving](#after-saving)
- [Changing a search](#changing-a-search)
- [How many requests](#how-many-requests)
- [Ready-made setups](#ready-made-setups)
- [The dashboard card](#the-dashboard-card)
- [When something looks wrong](#when-something-looks-wrong)

## Before you start

**One entry is one search**: the same departure airports, days and hours every week. Two different trips, such as weekends from home and a week by the sea in summer, are two entries: add the integration again. Two entries with the same airports, destinations and days are refused as duplicates.

**Codes, not names.** Airports, cities and countries are typed as codes, one per field: press **Add** for another. Lower case and spaces are fine, duplicates are dropped.

| What | Code | Examples |
|---|---|---|
| Airport | 3 letters, IATA | `BER` Berlin Brandenburg, `STN` London Stansted, `BGY` Milan Bergamo |
| City with several airports | 3 letters, IATA city code | `LON` every London airport, `PAR` Paris, `MIL` Milan, `ROM` Rome, `NYC` New York |
| Country | 2 letters, ISO | `DE` Germany, `IT` Italy, `GB` United Kingdom |

The airport code is on boarding passes and on the airport's page in any search engine. City codes work for destinations; for departure airports use the airports themselves, since each trip comes back to the airport it left from.

Prices are for **one adult**, return, in the currency of Home Assistant.

## Where from, where to

![The first half of the form: airports, destinations, countries and sources](images/setup-where.png)

**Name** is the name of the device and the start of every sensor's name: "Weekends from Berlin" gives `sensor.weekends_from_berlin_week_1`. It is not in **Configure**: rename the entry or the device from their pages, as for any integration.

**Departure airports** (required): one or more airports. Ryanair is searched from each of them; every trip found comes back to the airport it left from, so with `BER` and `LEJ` a trip leaving from Leipzig returns to Leipzig. The card has a filter by departure airport.

**Destinations**: what to search for.

- **Empty** means **anywhere**: every destination Ryanair flies to from your airports, in the hours you choose. This is the most useful setting for "where can I go this weekend?". Only Ryanair can do it.
- **A list** limits the search to those airports or cities. Ryanair then searches only them too, and each one gets its own sensor with its lowest price over the weeks.

**Leave out countries**: countries you are not interested in, usually your own (`DE` from Berlin, so no Munich or Hamburg). They are taken out of what was found, not of the searches, so changing this list shows the new result at once without searching again.

## Sources

**Ryanair** reads the fare finder of ryanair.com: one request per departure airport and week returns the cheapest return fare to every destination. It is fast and light, and the only source that can search anywhere, but it covers Ryanair group flights only.

**Google Flights** covers every airline, but it has to be searched route by route, one way at a time, and the requests are spaced 20 to 30 seconds apart. So it needs a list of destinations, and a long list takes a long time (see [How many requests](#how-many-requests)).

The two lists for Google let you combine them well:

- **Google Flights destinations**: searched only on Google Flights. With destinations empty above, **Ryanair keeps searching anywhere** while Google checks a short list of places that Ryanair does not fly to, or flies to from another airport. Empty: Google uses the destinations above.
- **Google Flights departure airports**: the departure airports Google searches from, for example only the big airport when the small one is all Ryanair. Empty: all of them.

Google needs some destinations: in its own list or in the one above. With both sources, each week keeps the cheapest trip per destination and airport, whichever source found it.

> [!CAUTION]
> **Google Flights can block your home's internet connection.** It is read without an API, and an address that makes too many automatic searches gets a captcha from Google, for every device at home: on Google Flights and possibly on other Google pages, until Google lifts it. Google publishes no limit, so the integration sets its own, well on the safe side:
>
> | Limit | Value | Enforced |
> |---|---|---|
> | Google requests a day, at most | **300** | yes: the form refuses a search over it and says how many it would make; from 200 it saves with a warning |
> | Google interval, at least | **12 hours** | yes: the field goes no lower |
> | Google interval, recommended | **24 hours**, the default | |
> | Pause between two requests | 20 to 30 seconds | yes, not an option |
>
> The 300 come from what has run for weeks without a single block: up to 224 requests a day, once a day. They are not a promise: other searches from your home count too (a busy household, a VPN exit shared with others). If you ever get a block, the round stops at once and waits for the next interval; make the search smaller rather than more frequent.

A search over the limit is refused, with the number of requests it would make:

![The form refusing a Google setup over 300 requests a day](images/google-limit.png)

The requests of a setting are counted in [How many requests](#how-many-requests).

## When

![The second half of the form: weeks, days and hours](images/setup-when.png)

**Weeks**: how many weeks ahead, from 1 to 12. The first is the coming one: the week whose outbound day is today or later. Every week has its own sensor (`week_1`, `week_2`…), which moves on by a week as the days go by.

**Outbound day** and **Return day**: the weekdays of the trip.

- A return day **after** the outbound day is the same week: Friday to Sunday.
- A return day **before** it is the week after: Saturday to Monday, Sunday to Tuesday.
- The **same** day means a whole week: Saturday to Saturday.

**Departure from / until**: the window in which the flight **leaves**, in hours from 0 to 24, where 24 is midnight. "From 19 until 24" on Friday means take-off between 19:00 and 23:59; the landing can be after midnight. The end must come after the start. Narrow windows find fewer trips: if a week stays empty, widen them first.

**Direct flights only**: for Google Flights, which can also find flights with stops. Ryanair always flies direct.

## Before saving: the requests

There is nothing to count by hand. With Google Flights among the sources, **Submit** does not save yet: it shows how many requests the search makes, then **Save** or **Change the search** (back to the form, as you filled it in). A form in Home Assistant cannot count while it is being filled in, so the numbers come after Submit.

![The summary before saving, with the warning of a search close to the limit](images/summary.png)

- **Up to 200 Google requests a day**: just the numbers.
- **200 to 300**: the numbers and a warning that the search is close to the limit. It can be saved; make it smaller unless you need all of it.
- **Over 300**: the form refuses it and says how many it would make (see [Sources](#sources)).

With Ryanair only there is no summary: one request per airport and week is nothing to worry about.

## After saving

- **Ryanair** searches at once, in a few seconds: the week sensors have values right away.
- **Google Flights** searches in the background, one week after the other. Its trips appear week by week; the whole round takes some minutes per destination. The diagnostic sensor *Google Flights search* has `running: true` meanwhile.
- After that, Ryanair searches every 3 hours and Google every 24 hours. Results are saved: a restart of Home Assistant shows them at once and does not search again.

Each week sensor has the cheapest price as its state and up to 30 trips in its attributes (cheapest first, one per destination and departure airport), with times, flight numbers, airline, country and booking link. The diagnostic sensors show when each source last succeeded and the error of the last attempt.

![The sensors of a search](images/device.png)

## Changing a search

Everything but the name can be changed from **Settings → Devices & services → Flight Prices → Configure**. At the top it says how many Google requests a day the saved search makes:

![The top of Configure, with the requests of the saved search](images/configure-requests.png)

The form is the same as for a new search, with the same summary before saving, and two more options at the bottom:

![The intervals, at the bottom of Configure](images/options-intervals.png)

- **Ryanair search every**: 1 to 24 hours, 3 by default.
- **Google Flights search every**: 12 to 168 hours, **24 by default and recommended**. Going below a day is rarely worth it, since prices of flights weeks ahead move slowly, and it doubles the requests: a search of 160 requests a round is fine once a day and refused every 12 hours (320 a day, over the limit of 300). Raise it, rather than cutting destinations, if you want a longer list.

After saving, the search reloads. A source searches again **only if what it searches changed**: airports, destinations, days, hours, direct flights, or more weeks than its last search covered. Otherwise the saved trips stay: fewer weeks, other countries left out, other intervals and a change for Google only (Ryanair keeps its trips) need no new search.

## How many requests

| Source | Requests per round | Time |
|---|---|---|
| Ryanair | departure airports × weeks | about a second each |
| Google Flights | weeks × Google destinations × Google departure airports × 2 | 20 to 30 seconds each |

The [summary before saving](#before-saving-the-requests) does this count for you; the table is for planning. Google searches the return only when the outbound found something, so real rounds are often shorter; the limit counts the most a round can make. **Google requests a day** are the requests of a round × 24 / the interval in hours: ✅ saved, ⚠️ saved with a warning (200 to 300), ❌ refused (over 300). Some examples with 8 weeks:

| Google setup | Requests a round | Round | Once a day (24 h) | Twice a day (12 h) |
|---|---|---|---|---|
| 3 destinations, 1 airport | up to 48 | about 20 minutes | ✅ 48 | ✅ 96 |
| 5 destinations, 1 airport | up to 80 | about 35 minutes | ✅ 80 | ✅ 160 |
| 14 destinations, 1 airport | up to 224 | about an hour and a half | ⚠️ 224 | ❌ 448 |
| 10 destinations, 2 airports | up to 320 | about two hours and a quarter | ❌ 320 (⚠️ every 36 h: 214) | ❌ 640 |
| 14 destinations, 2 airports | up to 448 | about three hours | ❌ 448 (⚠️ every 48 h: 224) | ❌ 896 |

With 12 weeks instead of 8 every figure grows by half. When the form refuses a search, it says how many requests it would make: take out destinations, a Google departure airport or some weeks, or lengthen the interval.

All the requests come from your home's internet connection (see the [caution above](#sources)). A Google round stops at the first sign of a block (cookie consent, captcha, too many requests) or after 5 errors in a row, and is tried again at the next interval. **Keep the Google list short**, a handful of places that Ryanair does not cover, rather than every city you might like. Ryanair is light (one request per airport and week, a second apart) and has no limit of its own beyond its interval of 1 to 24 hours.

## Ready-made setups

**Weekend anywhere from home**, the defaults:
Departure airports your one or two nearest airports · Destinations empty · Leave out your country · Sources Ryanair · Weeks 8 · Friday from 19 until 24 · Sunday from 14 until 24.

**The same, plus a few cities on other airlines:**
as above, with Sources Ryanair and Google Flights · Google Flights destinations `PAR`, `AMS`, `LON` · Google Flights departure airports your main airport.

**Long weekend:**
Thursday from 17 until 24 · Monday from 15 until 24.

**A week away:**
Saturday from 6 until 14 · Saturday from 12 until 24 (same day: the week after) · Weeks 12 · Destinations a few beach places, or empty.

**Watching one trip:**
Destinations `LIS` · Sources both · Weeks 4: the sensor `sensor.<name>_lis` has the lowest price over the weeks, handy for an automation that tells you when it drops below a figure (examples in the [README](../README.md#automations)).

## The dashboard card

The integration comes with a card: edit a dashboard, **Add card**, search for **Flight Prices**. It works best in a section that takes the whole width.

![The editor of the card](images/card-editor.png)

- **Search**: which search to show. With only one, the card finds it by itself.
- **Title**: by default, the name of the search.
- **Destinations per week**: how many each week shows before "Show the other destinations". A tap on a week's title shows them all.
- **Each destination only once on the page**: on by default. Destinations are shared out in rounds from the cheapest, so each sits in its cheapest week when there is room and no week is left empty; a trip cheaper in another week says so. Turned off, every week shows its own cheapest destinations, and the same city can come back week after week.

The filter by departure airport at the top is remembered on each device. A tap on a trip opens the booking page; trips that pair two airlines on Google Flights are two tickets, with an **Outbound** and a **Return** button.

## When something looks wrong

**A week shows "No flights found".** Nothing leaves in the windows you chose, or nothing goes back in time: widen the hours, allow flights with stops for Google, or check the airports. Christmas and other holidays often have few flights.

**Google Flights trips do not appear.** Look at the *Google Flights search* sensor: `running: true` means a round is still going; an `error` says why the last one stopped. A block (captcha, too many requests) waits for the next interval. If it happens again, make the search smaller and the interval longer, and check that nothing else at home searches Google automatically: a block is for the whole connection.

**A destination appears in some weeks only.** With "Each destination only once on the page" the card shows it in one week; tap the week's title to see the whole list.

**The prices on the booking page are different.** Prices change all the time, and the integration's are as old as the last search (up to 3 hours for Ryanair, a day for Google). A Google trip with two airlines is two separate tickets: open both links. For a trip with one airline, Google may show a lower return fare than the two one-way prices added up.

**The card says "Configuration error".** Reload the page; if it stays, check that the integration is loaded in **Settings → Devices & services**.
