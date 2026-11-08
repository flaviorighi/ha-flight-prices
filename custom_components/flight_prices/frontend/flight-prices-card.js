/*
 * Flight Prices card: the weeks of a search and their trips, shipped with the integration.
 *
 * No dependencies and no build step: Home Assistant loads this file as a module on every
 * dashboard (frontend.add_extra_js_url), so the card is in the card picker with nothing to
 * install. It reads the sensors of one search (a device of the integration) and shows:
 * - a summary: the cheapest trip, how many destinations, when each source last searched;
 * - a filter by departure airport, remembered on this device;
 * - one block per week, with each destination only once on the page: in rounds from the
 *   cheapest, the n-th round gives each week its n-th destination, so every week keeps
 *   some and each destination sits in its cheapest week when there is room;
 * - the whole list of a week on a tap on its title; booking links on the trips, two for
 *   trips that are two tickets (two airlines on Google Flights).
 */

const CARD = "flight-prices-card";
const DOMAIN = "flight_prices";
const ROUNDS_DEFAULT = 3;

const STRINGS = {
  en: {
    name: "Flight Prices",
    description: "The weeks of a flight search, their cheapest trips and the booking links.",
    weekend: "Weekend {dates}",
    cheapest: "Cheapest: {city} · {price}",
    cheapest_from: "Cheapest from {airport}: {city} · {price}",
    found_weekends: "{dates} · {count} destinations in {weeks} weekends.",
    found_weeks: "{dates} · {count} destinations in {weeks} weeks.",
    nothing: "No flights found",
    searched: "Searched: {list}",
    at: "{source} at {time}",
    on: "{source} on {date} at {time}",
    running: "{source} searching now",
    never: "{source} never succeeded",
    failed: "last attempt failed: {error}",
    all: "All",
    show_one: "Show the other destination",
    show_many: "Show the other {count} destinations",
    hide: "{count} destinations · hide",
    count_one: "1 destination",
    count_many: "{count} destinations",
    no_flights: "No flights found",
    no_flights_hours: "Nothing {from}within the hours: out {out}, back {back}",
    from_airport: "from {airport} ",
    elsewhere: "Destinations shown in other weeks",
    elsewhere_tap: "Tap to see them",
    cheaper_on: "cheaper on {date} ({price})",
    two_tickets: "Two tickets",
    outbound: "Outbound",
    return: "Return",
    no_search: "No Flight Prices search found. Add one in Settings → Devices & services.",
    device_id: "Search",
    title: "Title",
    per_week: "Destinations per week",
    unique: "Each destination only once on the page",
  },
  it: {
    name: "Flight Prices",
    description: "Le settimane di una ricerca di voli, i viaggi più economici e i link di prenotazione.",
    weekend: "Weekend {dates}",
    cheapest: "Il più economico: {city} · {price}",
    cheapest_from: "Il più economico da {airport}: {city} · {price}",
    found_weekends: "{dates} · {count} destinazioni in {weeks} weekend.",
    found_weeks: "{dates} · {count} destinazioni in {weeks} settimane.",
    nothing: "Nessun volo trovato",
    searched: "Ricerca {list}",
    at: "{source} alle {time}",
    on: "{source} il {date} alle {time}",
    running: "{source} in corso",
    never: "{source} mai riuscita",
    failed: "ultimo tentativo fallito: {error}",
    all: "Tutti",
    show_one: "Mostra l'altra destinazione",
    show_many: "Mostra le altre {count} destinazioni",
    hide: "{count} destinazioni · nascondi",
    count_one: "1 destinazione",
    count_many: "{count} destinazioni",
    no_flights: "Nessun volo trovato",
    no_flights_hours: "Nessun volo {from}nelle fasce: andata {out}, ritorno {back}",
    from_airport: "da {airport} ",
    elsewhere: "Destinazioni già mostrate in altre settimane",
    elsewhere_tap: "Tocca per vederle",
    cheaper_on: "meno cara il {date} ({price})",
    two_tickets: "Due biglietti",
    outbound: "Andata",
    return: "Ritorno",
    no_search: "Nessuna ricerca di Flight Prices. Aggiungine una da Impostazioni → Dispositivi e servizi.",
    device_id: "Ricerca",
    title: "Titolo",
    per_week: "Destinazioni per settimana",
    unique: "Ogni destinazione una sola volta nella pagina",
  },
  de: {
    name: "Flight Prices",
    description: "Die Wochen einer Flugsuche, ihre günstigsten Reisen und die Buchungslinks.",
    weekend: "Wochenende {dates}",
    cheapest: "Am günstigsten: {city} · {price}",
    cheapest_from: "Am günstigsten ab {airport}: {city} · {price}",
    found_weekends: "{dates} · {count} Ziele an {weeks} Wochenenden.",
    found_weeks: "{dates} · {count} Ziele in {weeks} Wochen.",
    nothing: "Keine Flüge gefunden",
    searched: "Suche: {list}",
    at: "{source} um {time}",
    on: "{source} am {date} um {time}",
    running: "{source} sucht gerade",
    never: "{source} noch nie erfolgreich",
    failed: "letzter Versuch fehlgeschlagen: {error}",
    all: "Alle",
    show_one: "Das andere Ziel anzeigen",
    show_many: "Die anderen {count} Ziele anzeigen",
    hide: "{count} Ziele · ausblenden",
    count_one: "1 Ziel",
    count_many: "{count} Ziele",
    no_flights: "Keine Flüge gefunden",
    no_flights_hours: "Keine Flüge {from}in den Zeitfenstern: hin {out}, zurück {back}",
    from_airport: "ab {airport} ",
    elsewhere: "Ziele schon in anderen Wochen angezeigt",
    elsewhere_tap: "Tippen, um sie zu sehen",
    cheaper_on: "günstiger am {date} ({price})",
    two_tickets: "Zwei Tickets",
    outbound: "Hinflug",
    return: "Rückflug",
    no_search: "Keine Flight-Prices-Suche gefunden. Lege eine unter Einstellungen → Geräte & Dienste an.",
    device_id: "Suche",
    title: "Titel",
    per_week: "Ziele pro Woche",
    unique: "Jedes Ziel nur einmal auf der Seite",
  },
  es: {
    name: "Flight Prices",
    description: "Las semanas de una búsqueda de vuelos, sus viajes más baratos y los enlaces de reserva.",
    weekend: "Fin de semana {dates}",
    cheapest: "El más barato: {city} · {price}",
    cheapest_from: "El más barato desde {airport}: {city} · {price}",
    found_weekends: "{dates} · {count} destinos en {weeks} fines de semana.",
    found_weeks: "{dates} · {count} destinos en {weeks} semanas.",
    nothing: "No se han encontrado vuelos",
    searched: "Búsqueda: {list}",
    at: "{source} a las {time}",
    on: "{source} el {date} a las {time}",
    running: "{source} buscando ahora",
    never: "{source} nunca ha funcionado",
    failed: "último intento fallido: {error}",
    all: "Todos",
    show_one: "Mostrar el otro destino",
    show_many: "Mostrar los otros {count} destinos",
    hide: "{count} destinos · ocultar",
    count_one: "1 destino",
    count_many: "{count} destinos",
    no_flights: "No se han encontrado vuelos",
    no_flights_hours: "Ningún vuelo {from}en las franjas: ida {out}, vuelta {back}",
    from_airport: "desde {airport} ",
    elsewhere: "Destinos ya mostrados en otras semanas",
    elsewhere_tap: "Toca para verlos",
    cheaper_on: "más barato el {date} ({price})",
    two_tickets: "Dos billetes",
    outbound: "Ida",
    return: "Vuelta",
    no_search: "No hay ninguna búsqueda de Flight Prices. Añade una en Ajustes → Dispositivos y servicios.",
    device_id: "Búsqueda",
    title: "Título",
    per_week: "Destinos por semana",
    unique: "Cada destino una sola vez en la página",
  },
  fr: {
    name: "Flight Prices",
    description: "Les semaines d'une recherche de vols, leurs voyages les moins chers et les liens de réservation.",
    weekend: "Week-end {dates}",
    cheapest: "Le moins cher : {city} · {price}",
    cheapest_from: "Le moins cher depuis {airport} : {city} · {price}",
    found_weekends: "{dates} · {count} destinations sur {weeks} week-ends.",
    found_weeks: "{dates} · {count} destinations sur {weeks} semaines.",
    nothing: "Aucun vol trouvé",
    searched: "Recherche : {list}",
    at: "{source} à {time}",
    on: "{source} le {date} à {time}",
    running: "{source} en cours",
    never: "{source} jamais réussie",
    failed: "dernière tentative échouée : {error}",
    all: "Tous",
    show_one: "Afficher l'autre destination",
    show_many: "Afficher les {count} autres destinations",
    hide: "{count} destinations · masquer",
    count_one: "1 destination",
    count_many: "{count} destinations",
    no_flights: "Aucun vol trouvé",
    no_flights_hours: "Aucun vol {from}dans les plages : aller {out}, retour {back}",
    from_airport: "depuis {airport} ",
    elsewhere: "Destinations déjà affichées dans d'autres semaines",
    elsewhere_tap: "Touchez pour les voir",
    cheaper_on: "moins cher le {date} ({price})",
    two_tickets: "Deux billets",
    outbound: "Aller",
    return: "Retour",
    no_search: "Aucune recherche Flight Prices. Ajoutez-en une dans Paramètres → Appareils et services.",
    device_id: "Recherche",
    title: "Titre",
    per_week: "Destinations par semaine",
    unique: "Chaque destination une seule fois sur la page",
  },
  pl: {
    name: "Flight Prices",
    description: "Tygodnie wyszukiwania lotów, ich najtańsze podróże i linki do rezerwacji.",
    weekend: "Weekend {dates}",
    cheapest: "Najtaniej: {city} · {price}",
    cheapest_from: "Najtaniej z {airport}: {city} · {price}",
    found_weekends: "{dates} · cele: {count} · weekendy: {weeks}.",
    found_weeks: "{dates} · cele: {count} · tygodnie: {weeks}.",
    nothing: "Nie znaleziono lotów",
    searched: "Wyszukiwanie: {list}",
    at: "{source} o {time}",
    on: "{source} dnia {date} o {time}",
    running: "{source} szuka teraz",
    never: "{source}: jeszcze bez udanego wyszukiwania",
    failed: "ostatnia próba nieudana: {error}",
    all: "Wszystkie",
    show_one: "Pokaż pozostały cel",
    show_many: "Pokaż pozostałe cele ({count})",
    hide: "Cele: {count} · zwiń",
    count_one: "1 cel",
    count_many: "Cele: {count}",
    no_flights: "Nie znaleziono lotów",
    no_flights_hours: "Brak lotów {from}w tych godzinach: wylot {out}, powrót {back}",
    from_airport: "z {airport} ",
    elsewhere: "Cele pokazane w innych tygodniach",
    elsewhere_tap: "Dotknij, aby je zobaczyć",
    cheaper_on: "taniej {date} ({price})",
    two_tickets: "Dwa bilety",
    outbound: "Wylot",
    return: "Powrót",
    no_search: "Nie znaleziono wyszukiwania Flight Prices. Dodaj je w Ustawienia → Urządzenia oraz usługi.",
    device_id: "Wyszukiwanie",
    title: "Tytuł",
    per_week: "Cele na tydzień",
    unique: "Każdy cel tylko raz na stronie",
  },
};

const SOURCES = { ryanair: "Ryanair", google: "Google Flights" };

function language(hass) {
  const lang = (hass?.locale?.language || hass?.language || "en").toLowerCase();
  return STRINGS[lang] ? lang : STRINGS[lang.split("-")[0]] ? lang.split("-")[0] : "en";
}

function t(hass, key, vars = {}) {
  const text = STRINGS[language(hass)][key] ?? STRINGS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? vars[name] : `{${name}}`));
}

function escape(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

// "2026-11-06" as a local date, without the time zone shift of Date.parse.
function day(text) {
  const [y, m, d] = String(text).slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

function locale(hass) {
  return hass?.locale?.language || hass?.language || "en";
}

function price(hass, value, currency) {
  try {
    return new Intl.NumberFormat(locale(hass), {
      style: "currency",
      currency: currency || "EUR",
      maximumFractionDigits: 0,
    }).format(value);
  } catch (_err) {
    return `${Math.round(value)} ${currency || ""}`.trim();
  }
}

function shortDate(hass, date) {
  return new Intl.DateTimeFormat(locale(hass), { day: "numeric", month: "short" }).format(date);
}

function dateRange(hass, from, to) {
  const format = new Intl.DateTimeFormat(locale(hass), { day: "numeric", month: "short" });
  try {
    // Some languages pad the days of a range ("06–08 nov" in Italian): days stay as days.
    return format.formatRange(from, to).replace(/(^|\D)0(\d)(?!\d)/g, "$1$2");
  } catch (_err) {
    return `${format.format(from)}–${format.format(to)}`;
  }
}

function weekday(hass, date) {
  return new Intl.DateTimeFormat(locale(hass), { weekday: "short" }).format(date);
}

function clock(text) {
  return String(text).slice(11, 16);
}

// Out on Thursday to Saturday and back on Saturday to Monday reads as a weekend.
function isWeekend(outbound, inbound) {
  return [4, 5, 6].includes(outbound.getDay()) && [6, 0, 1].includes(inbound.getDay());
}

/** The sensors of one search, found through the entity registry entries in hass. */
function readSearch(hass, deviceId) {
  const entries = Object.values(hass.entities || {}).filter((entry) => entry.platform === DOMAIN);
  const device = deviceId || entries.find((entry) => entry.device_id)?.device_id;
  if (!device) return null;
  const weeks = [];
  const searches = [];
  for (const entry of entries) {
    if (entry.device_id !== device) continue;
    const state = hass.states[entry.entity_id];
    if (!state) continue;
    const attrs = state.attributes;
    if (Array.isArray(attrs.trips) && attrs.outbound_date) {
      weeks.push(state);
    } else if ("last_attempt" in attrs && "error" in attrs) {
      const key = (entry.translation_key || "").replace(/_search$/, "");
      searches.push({ state, source: SOURCES[key] ? key : "running" in attrs ? "google" : "ryanair" });
    }
  }
  weeks.sort((a, b) => (a.attributes.outbound_date < b.attributes.outbound_date ? -1 : 1));
  searches.sort((a, b) => (a.source < b.source ? 1 : -1));
  return { device, name: hass.devices?.[device]?.name, weeks, searches };
}

/**
 * Which week shows which destination. Per destination its cheapest week; then in rounds,
 * from the cheapest pair: a destination goes to a week if it has none yet and the week has
 * fewer than `round` destinations.
 */
function assign(weeks, airport, perWeek, unique) {
  const lists = new Map();
  const best = new Map();
  const pairs = [];
  for (const week of weeks) {
    const date = week.attributes.outbound_date;
    const seen = new Set();
    const list = [];
    // Trips come cheapest first, so the first one of a destination is its cheapest airport.
    for (const trip of week.attributes.trips) {
      if ((airport && trip.origin !== airport) || seen.has(trip.destination)) continue;
      seen.add(trip.destination);
      list.push(trip);
      pairs.push([trip.price, date, trip.destination]);
      const current = best.get(trip.destination);
      if (!current || trip.price < current.price) best.set(trip.destination, { date, price: trip.price, trip });
    }
    lists.set(date, list);
  }
  const placed = new Map();
  if (unique) {
    const filled = new Map();
    pairs.sort((a, b) => a[0] - b[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0));
    for (let round = 1; round <= perWeek; round++) {
      for (const [, date, destination] of pairs) {
        if (!placed.has(destination) && (filled.get(date) || 0) < round) {
          placed.set(destination, date);
          filled.set(date, (filled.get(date) || 0) + 1);
        }
      }
    }
  }
  return { lists, best, placed };
}

const STYLE = `
  :host {
    --fp-green: var(--green-color, #4caf50);
    --fp-blue: var(--blue-color, #2196f3);
    --fp-muted: var(--blue-grey-color, #607d8b);
    --fp-red: var(--error-color, #f44336);
    --fp-grey: var(--grey-color, #9e9e9e);
    display: block;
  }
  .page { display: flex; flex-direction: column; gap: var(--ha-section-grid-row-gap, 8px); }
  .weeks {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 330px), 1fr));
    gap: var(--ha-section-grid-row-gap, 8px) var(--ha-section-grid-column-gap, 8px);
    align-items: start;
  }
  ha-card { overflow: hidden; }
  .header { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
  .title { font-size: 1.15em; font-weight: 500; display: flex; align-items: center; gap: 8px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    display: inline-flex; align-items: center; gap: 4px;
    border: 1px solid var(--divider-color); border-radius: 18px;
    padding: 4px 12px; font: inherit; font-size: 0.9em; cursor: pointer;
    background: none; color: var(--primary-text-color);
  }
  .chip ha-icon { --mdc-icon-size: 16px; color: var(--fp-grey); }
  .chip.on { border-color: color-mix(in srgb, var(--fp-green) 45%, transparent);
    background: color-mix(in srgb, var(--fp-green) 14%, transparent); }
  .chip.on ha-icon { color: var(--fp-green); }
  .row {
    display: flex; gap: 12px; align-items: flex-start; padding: 10px 12px;
    cursor: pointer; border-radius: var(--ha-card-border-radius, 12px);
    transition: background-color 0.3s;
  }
  .row:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
  .row.static { cursor: default; }
  .row.tinted { background: color-mix(in srgb, var(--c) 14%, transparent); }
  .shape {
    flex: none; width: 40px; height: 40px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    background: color-mix(in srgb, var(--c) 20%, transparent); color: var(--c);
  }
  .shape ha-icon { --mdc-icon-size: 22px; }
  .text { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 2px; }
  .primary { font-weight: 600; font-size: 1em; color: var(--primary-text-color); }
  .secondary { font-size: 0.85em; color: var(--secondary-text-color); line-height: 1.4; }
  .week-title { padding: 12px 12px 4px; cursor: pointer; }
  .week-title.static { cursor: default; }
  .week-title .name { font-size: 1.1em; font-weight: 500; }
  .week-title .sub { font-size: 0.85em; color: var(--secondary-text-color); }
  .week-title:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
  .trips { display: flex; flex-direction: column; gap: 2px; padding: 0 0 6px; }
  .tickets { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 6px; }
  .ticket {
    display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px;
    border-radius: 14px; border: 1px solid color-mix(in srgb, var(--c) 45%, transparent);
    background: none; color: var(--primary-text-color); font: inherit; font-size: 0.85em; cursor: pointer;
  }
  .ticket ha-icon { --mdc-icon-size: 15px; color: var(--c); }
  .error { padding: 16px; color: var(--secondary-text-color); }
`;

class FlightPricesCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._open = new Set();
    this._seen = [];
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("keydown", (ev) => {
      if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches?.("[role=button]")) {
        ev.preventDefault();
        this._onClick(ev);
      }
    });
  }

  static getConfigElement() {
    return document.createElement(`${CARD}-editor`);
  }

  static getStubConfig(hass) {
    const entry = Object.values(hass.entities || {}).find((e) => e.platform === DOMAIN && e.device_id);
    return entry ? { device_id: entry.device_id } : {};
  }

  setConfig(config) {
    this._config = { per_week: ROUNDS_DEFAULT, unique: true, ...config };
    this._airport = undefined;
    this._seen = [];
    this._search = this._hass ? readSearch(this._hass, this._config.device_id) : undefined;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const search = readSearch(hass, this._config?.device_id);
    // Draw again only when one of the search's states changed (they are replaced, not mutated).
    const seen = [locale(hass), ...(search ? [...search.weeks, ...search.searches.map((s) => s.state)] : [])];
    if (seen.length === this._seen.length && seen.every((item, i) => item === this._seen[i])) return;
    this._seen = seen;
    this._search = search;
    this._render();
  }

  getCardSize() {
    return 3 + 4 * (this._search?.weeks.length || 1);
  }

  getGridOptions() {
    return { columns: "full" };
  }

  get _storageKey() {
    return `${CARD}:${this._search?.device}:airport`;
  }

  _getAirport(origins) {
    if (this._airport === undefined) {
      try {
        this._airport = localStorage.getItem(this._storageKey) || "";
      } catch (_err) {
        this._airport = "";
      }
    }
    return origins.includes(this._airport) ? this._airport : "";
  }

  _setAirport(airport) {
    this._airport = airport;
    try {
      if (airport) localStorage.setItem(this._storageKey, airport);
      else localStorage.removeItem(this._storageKey);
    } catch (_err) {
      // Private windows and blocked storage: the filter lasts until the page is reloaded.
    }
    this._render();
  }

  _onClick(ev) {
    const target = ev.composedPath().find((node) => node.dataset?.action);
    if (!target) return;
    const { action } = target.dataset;
    if (action === "toggle") {
      const week = target.dataset.week;
      if (this._open.has(week)) this._open.delete(week);
      else this._open.add(week);
      this._render();
    } else if (action === "airport") {
      this._setAirport(target.dataset.airport);
    } else if (action === "link" && target.dataset.url) {
      window.open(target.dataset.url, "_blank", "noopener");
    } else if (action === "more-info") {
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          detail: { entityId: target.dataset.entity },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  _render() {
    const hass = this._hass;
    if (!hass || !this._config) return;
    const search = this._search ?? readSearch(hass, this._config.device_id);
    if (!search || !search.weeks.length) {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div class="error">${escape(
        t(hass, "no_search"),
      )}</div></ha-card>`;
      return;
    }
    const first = search.weeks[0].attributes;
    const origins = first.origins || [];
    const airport = this._getAirport(origins);
    const perWeek = Math.max(1, Number(this._config.per_week) || ROUNDS_DEFAULT);
    const unique = this._config.unique !== false;
    const result = assign(search.weeks, airport, perWeek, unique);
    const currency = search.weeks[0].attributes.unit_of_measurement;
    const weekend = isWeekend(day(first.outbound_date), day(first.return_date));
    const html = [
      `<style>${STYLE}</style><div class="page">`,
      this._header(search, result, { airport, origins, currency, weekend }),
      `<div class="weeks">`,
      ...search.weeks.map((week) => this._week(week, result, { airport, perWeek, unique, currency, weekend })),
      `</div></div>`,
    ];
    this.shadowRoot.innerHTML = html.join("");
  }

  _period(outbound, inbound, weekend) {
    const dates = dateRange(this._hass, day(outbound), day(inbound));
    return weekend ? t(this._hass, "weekend", { dates }) : dates;
  }

  _header(search, result, { airport, origins, currency, weekend }) {
    const hass = this._hass;
    const title = this._config.title ?? search.name ?? t(hass, "name");
    // Red when a source never succeeded, or failed and its last success is over a day old.
    const failing = search.searches.some(({ state }) => {
      if (!state.attributes.error) return false;
      const last = Date.parse(state.state);
      return Number.isNaN(last) || Date.now() - last > 86400000;
    });
    const ranked = [...result.best.values()].sort((a, b) => a.price - b.price);
    let primary = t(hass, "nothing");
    let found = "";
    if (ranked.length) {
      const top = ranked[0];
      const week = search.weeks.find((w) => w.attributes.outbound_date === top.date);
      primary = t(hass, airport ? "cheapest_from" : "cheapest", {
        airport,
        city: top.trip.city || top.trip.destination,
        price: price(hass, top.price, currency),
      });
      found = t(hass, weekend ? "found_weekends" : "found_weeks", {
        dates: this._period(top.date, week?.attributes.return_date || top.date, false),
        count: ranked.length,
        weeks: search.weeks.length,
      });
    }
    const sources = search.searches.map(({ state, source }) => this._sourceText(state, source)).join(" · ");
    const status = search.searches[0]?.state.entity_id;
    const color = failing ? "var(--fp-red)" : "var(--fp-green)";
    const chips =
      origins.length > 1
        ? `<div class="chips">${["", ...origins]
            .map((code) => {
              const on = code === airport;
              return `<button class="chip${on ? " on" : ""}" data-action="airport" data-airport="${escape(code)}">
                <ha-icon icon="${on ? "mdi:check" : "mdi:airplane-takeoff"}"></ha-icon>${escape(code || t(hass, "all"))}
              </button>`;
            })
            .join("")}</div>`
        : "";
    return `<ha-card><div class="header">
      <div class="title"><ha-icon icon="mdi:airplane-takeoff"></ha-icon>${escape(title)}</div>
      <div class="row${failing ? " tinted" : ""}" style="--c: ${color}" role="button" tabindex="0"
        ${status ? `data-action="more-info" data-entity="${escape(status)}"` : ""}>
        <div class="shape"><ha-icon icon="${failing ? "mdi:airplane-alert" : "mdi:airplane"}"></ha-icon></div>
        <div class="text">
          <div class="primary">${escape(primary)}</div>
          <div class="secondary">${escape(found)} ${escape(t(hass, "searched", { list: sources }))}</div>
        </div>
      </div>
      ${chips}
    </div></ha-card>`;
  }

  _sourceText(state, key) {
    const hass = this._hass;
    const source = SOURCES[key] || key;
    const { error, running } = state.attributes;
    const last = Date.parse(state.state);
    let text;
    if (running) {
      text = t(hass, "running", { source });
    } else if (Number.isNaN(last)) {
      return error ? `${t(hass, "never", { source })}: ${error}` : t(hass, "never", { source });
    } else {
      const when = new Date(last);
      const time = new Intl.DateTimeFormat(locale(hass), { hour: "2-digit", minute: "2-digit" }).format(when);
      const today = new Date().toDateString() === when.toDateString();
      text = today
        ? t(hass, "at", { source, time })
        : t(hass, "on", { source, time, date: shortDate(hass, when) });
    }
    return error ? `${text} (${t(hass, "failed", { error })})` : text;
  }

  _week(week, result, { airport, perWeek, unique, currency, weekend }) {
    const hass = this._hass;
    const attrs = week.attributes;
    const date = attrs.outbound_date;
    const all = result.lists.get(date) || [];
    const mine = unique ? all.filter((trip) => result.placed.get(trip.destination) === date) : all;
    const open = this._open.has(date);
    const shown = open ? all : mine.slice(0, perWeek);
    const others = all.length - shown.length;
    let sub;
    if (!all.length) sub = "";
    else if (open) sub = t(hass, "hide", { count: all.length });
    else if (others === 1) sub = t(hass, "show_one");
    else if (others > 1) sub = t(hass, "show_many", { count: others });
    else sub = all.length === 1 ? t(hass, "count_one") : t(hass, "count_many", { count: all.length });
    const toggle = all.length && (open || others > 0);
    const title = this._period(date, attrs.return_date, weekend && isWeekend(day(date), day(attrs.return_date)));
    const head = `<div class="week-title${toggle ? "" : " static"}" ${
      toggle ? `role="button" tabindex="0" data-action="toggle" data-week="${escape(date)}"` : ""
    }><div class="name">${escape(title)}</div>${sub ? `<div class="sub">${escape(sub)}</div>` : ""}</div>`;

    let rows;
    if (!all.length) {
      const hoursOut = attrs.outbound_hours || [0, 24];
      const hoursBack = attrs.return_hours || [0, 24];
      const text = t(hass, "no_flights_hours", {
        from: airport ? t(hass, "from_airport", { airport }) : "",
        out: `${weekday(hass, day(date))} ${hoursOut[0]}–${hoursOut[1]}`,
        back: `${weekday(hass, day(attrs.return_date))} ${hoursBack[0]}–${hoursBack[1]}`,
      });
      rows = this._row({ icon: "mdi:airplane-off", color: "var(--fp-grey)", primary: t(hass, "no_flights"), lines: [text] });
    } else if (!shown.length) {
      rows = this._row({
        icon: "mdi:airplane-clock",
        color: "var(--fp-grey)",
        primary: t(hass, "elsewhere"),
        lines: [t(hass, "elsewhere_tap")],
        action: `data-action="toggle" data-week="${escape(date)}"`,
      });
    } else {
      rows = shown
        .map((trip) => {
          const placedHere = !unique || result.placed.get(trip.destination) === date;
          const best = result.best.get(trip.destination);
          const isFirst = placedHere && trip === mine[0];
          return this._trip(trip, { best, date, currency, isFirst, placedHere });
        })
        .join("");
    }
    return `<ha-card>${head}<div class="trips">${rows}</div></ha-card>`;
  }

  _trip(trip, { best, date, currency, isFirst, placedHere }) {
    const hass = this._hass;
    const out = trip.outbound;
    const back = trip.return;
    const line1 = `${trip.origin} · ${weekday(hass, day(out.departure))} ${clock(out.departure)} → ${clock(
      out.arrival,
    )} · ${weekday(hass, day(back.departure))} ${clock(back.departure)} → ${clock(back.arrival)}`;
    const parts = [trip.airline];
    if (trip.country) parts.push(trip.country);
    if (trip.source && SOURCES[trip.source] && trip.source !== "ryanair") parts.push(SOURCES[trip.source]);
    if (best && best.date !== date) {
      parts.push(t(hass, "cheaper_on", { date: shortDate(hass, day(best.date)), price: price(hass, best.price, currency) }));
    }
    const color = isFirst ? "var(--fp-green)" : placedHere ? "var(--fp-blue)" : "var(--fp-muted)";
    const tickets = trip.return_link
      ? `<div class="tickets">
          <button class="ticket" data-action="link" data-url="${escape(trip.link)}"><ha-icon icon="mdi:airplane-takeoff"></ha-icon>${escape(
            t(hass, "outbound"),
          )}</button>
          <button class="ticket" data-action="link" data-url="${escape(trip.return_link)}"><ha-icon icon="mdi:airplane-landing"></ha-icon>${escape(
            t(hass, "return"),
          )}</button>
          <span class="secondary">${escape(t(hass, "two_tickets"))}</span>
        </div>`
      : "";
    return this._row({
      icon: "mdi:airplane",
      color,
      tinted: isFirst,
      primary: `${trip.city || trip.destination} · ${price(hass, trip.price, currency)}`,
      lines: [line1, parts.join(" · ")],
      action: trip.link ? `data-action="link" data-url="${escape(trip.link)}"` : "",
      extra: tickets,
    });
  }

  _row({ icon, color, primary, lines, action = "", tinted = false, extra = "" }) {
    return `<div class="row${tinted ? " tinted" : ""}${action ? "" : " static"}" style="--c: ${color}" ${
      action ? `role="button" tabindex="0" ${action}` : ""
    }>
      <div class="shape"><ha-icon icon="${icon}"></ha-icon></div>
      <div class="text"><div class="primary">${escape(primary)}</div>${lines
        .map((line) => `<div class="secondary">${escape(line)}</div>`)
        .join("")}${extra}</div>
    </div>`;
  }
}

/** The searches (devices of the integration) as options of a select selector. */
function searchOptions(hass) {
  const devices = new Set(
    Object.values(hass.entities || {})
      .filter((entry) => entry.platform === DOMAIN && entry.device_id)
      .map((entry) => entry.device_id),
  );
  return [...devices].map((id) => ({ value: id, label: hass.devices?.[id]?.name || id }));
}

class FlightPricesCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => t(this._hass, schema.name);
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...ev.detail.value };
        for (const key of Object.keys(config)) {
          if (config[key] === "" || config[key] === undefined || config[key] === null) delete config[key];
        }
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    const options = searchOptions(this._hass);
    // Without a search in the configuration the card shows the first one: the menu says which.
    this._form.data = { per_week: ROUNDS_DEFAULT, unique: true, device_id: options[0]?.value, ...this._config };
    this._form.schema = [
      // The device selector with an integration filter waits on data the editor may not have: a plain list.
      { name: "device_id", selector: { select: { mode: "dropdown", options } } },
      { name: "title", selector: { text: {} } },
      { name: "per_week", selector: { number: { min: 1, max: 10, mode: "box" } } },
      { name: "unique", selector: { boolean: {} } },
    ];
  }
}

// Home Assistant imports this file while its own code is still loading, and can then swap
// window.customElements for its own registry, which would not know a card defined before. So
// the card is defined on whatever registry is current, again once Home Assistant is up. The
// file can also be loaded twice (by the integration and by a resource added by hand).
function register() {
  const registry = window.customElements;
  if (!registry.get(CARD)) registry.define(CARD, FlightPricesCard);
  if (!registry.get(`${CARD}-editor`)) registry.define(`${CARD}-editor`, FlightPricesCardEditor);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === CARD)) {
    window.customCards.push({
      type: CARD,
      name: STRINGS.en.name,
      description: STRINGS.en.description,
      preview: true,
      documentationURL: "https://github.com/flaviorighi/ha-flight-prices",
    });
  }
}

register();
// Every 0.2 s for a minute: a new registry gets the card at once.
(async () => {
  let registry = window.customElements;
  for (let i = 0; i < 300; i++) {
    // unref: in Node (the tests) the wait does not keep the process alive.
    await new Promise((resolve) => setTimeout(resolve, 200)?.unref?.());
    if (window.customElements !== registry || !registry.get(CARD)) {
      registry = window.customElements;
      register();
    }
  }
})();

// For the tests (tests/card): Home Assistant loads this file as a module, so exports are harmless.
export {
  FlightPricesCard,
  FlightPricesCardEditor,
  STRINGS,
  assign,
  dateRange,
  escape,
  isWeekend,
  language,
  readSearch,
  register,
  searchOptions,
  t,
};
