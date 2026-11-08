// Tests of the dashboard card, with Node's own test runner and no dependencies:
//   node --test tests/card/
// The browser is replaced by the few globals the card touches; the card renders into a
// string (innerHTML of its shadow root), which the tests read.

import assert from "node:assert/strict";
import { beforeEach, describe, test } from "node:test";

class FakeShadowRoot {
  constructor() {
    this.innerHTML = "";
    this.listeners = {};
  }
  addEventListener(type, listener) {
    this.listeners[type] = listener;
  }
}

const defined = new Map();
const opened = [];
const storage = new Map();
globalThis.HTMLElement = class {
  attachShadow() {
    this.shadowRoot = new FakeShadowRoot();
    return this.shadowRoot;
  }
  dispatchEvent(event) {
    (this.events ||= []).push(event);
  }
  appendChild() {}
};
globalThis.customElements = { get: (name) => defined.get(name), define: (name, cls) => defined.set(name, cls) };
// Home Assistant is up: the card does not wait for it.
defined.set("home-assistant", class {});
globalThis.CustomEvent = class {
  constructor(type, init) {
    this.type = type;
    this.detail = init?.detail;
  }
};
globalThis.window = { open: (url) => opened.push(url), customElements: globalThis.customElements };
globalThis.localStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
};

const card = await import("../../custom_components/flight_prices/frontend/flight-prices-card.js");
const {
  FlightPricesCard,
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
} = card;

const DEVICE = "device1";

function trip(destination, origin, price, extra = {}) {
  return {
    destination,
    origin,
    price,
    city: { LIS: "Lisbona", PAR: "Parigi", TIA: "Tirana", BCN: "Barcellona" }[destination] || destination,
    country: "Paese",
    airline: "Ryanair",
    source: "ryanair",
    outbound: { departure: "2026-11-06T20:15", arrival: "2026-11-06T22:10" },
    return: { departure: "2026-11-08T20:00", arrival: "2026-11-08T22:05" },
    link: `https://book/${destination}/${origin}`,
    ...extra,
  };
}

function week(number, outbound, inbound, trips) {
  return {
    entity_id: `sensor.weekend_week_${number}`,
    state: trips.length ? String(trips[0].price) : "unknown",
    attributes: {
      outbound_date: outbound,
      return_date: inbound,
      origins: ["MXP", "BGY"],
      outbound_hours: [19, 24],
      return_hours: [14, 24],
      unit_of_measurement: "EUR",
      trips,
    },
  };
}

function search(source, state, attributes = {}) {
  return {
    entity_id: `sensor.weekend_${source}_search`,
    state,
    attributes: { last_attempt: state, error: null, ...attributes },
  };
}

function makeHass({ weeks, searches = [], language: lang = "it" }) {
  const states = {};
  const entities = {};
  for (const state of [...weeks, ...searches]) {
    states[state.entity_id] = state;
    const key = state.entity_id.endsWith("_search") ? state.entity_id.split("_").at(-2) + "_search" : "week";
    entities[state.entity_id] = {
      entity_id: state.entity_id,
      platform: "flight_prices",
      device_id: DEVICE,
      translation_key: key,
    };
  }
  // Another integration's sensor and another search's must be left alone.
  states["sensor.other"] = { entity_id: "sensor.other", state: "1", attributes: { trips: [], outbound_date: "x" } };
  entities["sensor.other"] = { entity_id: "sensor.other", platform: "other", device_id: DEVICE };
  return {
    states,
    entities,
    devices: { [DEVICE]: { name: "Weekend da Milano" } },
    locale: { language: lang },
    language: lang,
  };
}

const WEEKS = [
  week(2, "2026-11-13", "2026-11-15", [trip("LIS", "BGY", 40), trip("TIA", "MXP", 80), trip("PAR", "MXP", 90)]),
  week(1, "2026-11-06", "2026-11-08", [
    trip("LIS", "MXP", 50),
    trip("TIA", "BGY", 60),
    trip("BCN", "MXP", 70),
    trip("LIS", "BGY", 75),
  ]),
];

function render(hass, config = {}) {
  const element = new FlightPricesCard();
  element.setConfig({ type: "custom:flight-prices-card", ...config });
  element.hass = hass;
  return element;
}

function click(element, dataset) {
  element._onClick({ composedPath: () => [{ dataset }] });
}

beforeEach(() => {
  opened.length = 0;
  storage.clear();
});

test("the card and its editor are in the card picker", () => {
  assert.equal(defined.get("flight-prices-card"), FlightPricesCard);
  assert.ok(defined.get("flight-prices-card-editor"));
  assert.deepEqual(
    window.customCards.map((c) => c.type),
    ["flight-prices-card"],
  );
});

test("defined again on a registry that replaced the first one", () => {
  // Home Assistant swaps window.customElements while it starts: the card must be in the new one.
  const replaced = new Map();
  window.customElements = { get: (name) => replaced.get(name), define: (name, cls) => replaced.set(name, cls) };
  try {
    register();
    register();
    assert.equal(replaced.get("flight-prices-card"), FlightPricesCard);
    assert.equal(window.customCards.length, 1);
  } finally {
    window.customElements = globalThis.customElements;
  }
});

describe("texts", () => {
  test("every language has the same keys as English", () => {
    const keys = Object.keys(STRINGS.en).sort();
    for (const [lang, strings] of Object.entries(STRINGS)) {
      assert.deepEqual(Object.keys(strings).sort(), keys, lang);
    }
  });

  test("the language follows Home Assistant, with English as fallback", () => {
    assert.equal(language({ locale: { language: "de-AT" } }), "de");
    assert.equal(language({ locale: { language: "pt-BR" } }), "en");
    assert.equal(t({ locale: { language: "it" } }, "show_many", { count: 4 }), "Mostra le altre 4 destinazioni");
  });

  test("Polish: the language follows Home Assistant, and counts need no declension", () => {
    assert.equal(language({ locale: { language: "pl" } }), "pl");
    assert.equal(language({ locale: { language: "pl-PL" } }), "pl");
    const hass = { locale: { language: "pl" } };
    for (const count of [2, 5, 22]) {
      assert.equal(t(hass, "show_many", { count }), `Pokaż pozostałe cele (${count})`);
      assert.equal(t(hass, "count_many", { count }), `Cele: ${count}`);
    }
    assert.equal(dateRange(hass, new Date(2026, 10, 6), new Date(2026, 10, 8)), "6–8 lis");
  });

  test("text from the sensors is escaped", () => {
    assert.equal(escape(`<b>"Rome" & 'Paris'</b>`), "&lt;b&gt;&quot;Rome&quot; &amp; &#39;Paris&#39;&lt;/b&gt;");
  });

  test("date ranges without padded days", () => {
    const hass = { locale: { language: "it" } };
    assert.equal(dateRange(hass, new Date(2026, 10, 6), new Date(2026, 10, 8)), "6–8 nov");
    // Intl puts thin spaces around the dash between two months.
    assert.equal(dateRange(hass, new Date(2026, 10, 27), new Date(2026, 11, 1)).replace(/\s/g, " "), "27 nov – 1 dic");
  });

  test("weekends: out Thursday to Saturday, back Saturday to Monday", () => {
    assert.equal(isWeekend(new Date(2026, 10, 6), new Date(2026, 10, 8)), true);
    assert.equal(isWeekend(new Date(2026, 10, 9), new Date(2026, 10, 12)), false);
  });
});

describe("the search", () => {
  test("weeks sorted by date and the sources, from the entity registry", () => {
    const hass = makeHass({
      weeks: WEEKS,
      searches: [search("ryanair", "2026-11-05T16:51:51+00:00"), search("google", "unknown", { running: true })],
    });
    const found = readSearch(hass);
    assert.equal(found.device, DEVICE);
    assert.equal(found.name, "Weekend da Milano");
    assert.deepEqual(
      found.weeks.map((w) => w.attributes.outbound_date),
      ["2026-11-06", "2026-11-13"],
    );
    assert.deepEqual(found.searches.map((s) => s.source).sort(), ["google", "ryanair"]);
    assert.equal(readSearch(hass, "another device").weeks.length, 0);
    assert.equal(readSearch({ states: {}, entities: {} }), null);
  });

  test("the editor shows the search the card uses", () => {
    const Editor = defined.get("flight-prices-card-editor");
    const editor = new Editor();
    const forms = [];
    globalThis.document = { createElement: () => { const form = { addEventListener() {} }; forms.push(form); return form; } };
    try {
      editor.hass = makeHass({ weeks: WEEKS });
      editor.setConfig({ type: "custom:flight-prices-card" });
      assert.equal(forms[0].data.device_id, DEVICE);
      assert.deepEqual(forms[0].schema[0].selector.select.options, [{ value: DEVICE, label: "Weekend da Milano" }]);
    } finally {
      delete globalThis.document;
    }
  });

  test("the editor lists the searches", () => {
    assert.deepEqual(searchOptions(makeHass({ weeks: WEEKS })), [{ value: DEVICE, label: "Weekend da Milano" }]);
    assert.deepEqual(FlightPricesCard.getStubConfig(makeHass({ weeks: WEEKS })), { device_id: DEVICE });
  });
});

describe("one destination per page", () => {
  const sorted = [...WEEKS].reverse();

  test("rounds from the cheapest pair", () => {
    const { placed, best, lists } = assign(sorted, "", 3, true);
    // Round 1: LIS 40 to the 13th, TIA 60 to the 6th; round 2: BCN 70 to the 6th, PAR 90 to the 13th.
    assert.deepEqual(Object.fromEntries(placed), {
      LIS: "2026-11-13",
      TIA: "2026-11-06",
      BCN: "2026-11-06",
      PAR: "2026-11-13",
    });
    assert.deepEqual(best.get("LIS"), { date: "2026-11-13", price: 40, trip: sorted[1].attributes.trips[0] });
    // One trip per destination, the cheapest airport first.
    assert.deepEqual(
      lists.get("2026-11-06").map((x) => `${x.destination}/${x.origin}`),
      ["LIS/MXP", "TIA/BGY", "BCN/MXP"],
    );
  });

  test("a week gets at most one destination per round", () => {
    const { placed } = assign(sorted, "", 1, true);
    assert.deepEqual(Object.fromEntries(placed), { LIS: "2026-11-13", TIA: "2026-11-06" });
  });

  test("the airport filter keeps that airport's trips only", () => {
    const { lists, best } = assign(sorted, "BGY", 3, true);
    assert.deepEqual(
      lists.get("2026-11-06").map((x) => `${x.destination}/${x.origin}`),
      ["TIA/BGY", "LIS/BGY"],
    );
    assert.equal(best.has("PAR"), false);
  });

  test("without unique, nothing is assigned", () => {
    assert.equal(assign(sorted, "", 3, false).placed.size, 0);
  });
});

describe("the card", () => {
  test("summary and weeks", () => {
    const hass = makeHass({ weeks: WEEKS, searches: [search("ryanair", new Date().toISOString())] });
    const html = render(hass).shadowRoot.innerHTML;
    assert.match(html, /Weekend da Milano/);
    assert.match(html, /Il più economico: Lisbona · 40\s€/);
    assert.match(html, /Weekend 6–8 nov/);
    assert.match(html, /Weekend 13–15 nov/);
    // Lisbon is cheaper on the 13th: the 6th shows Tirana and Barcelona, and says nothing about Lisbon.
    const first = html.split("Weekend 13–15 nov")[0];
    assert.match(first, /Tirana · 60\s€/);
    assert.doesNotMatch(first.split("Weekend 6–8 nov")[1], /Lisbona/);
    assert.match(first, /Mostra l'altra destinazione|Mostra l&#39;altra destinazione/);
    assert.doesNotMatch(html, /mdi:airplane-alert/);
  });

  test("a tap on the title shows the whole week, with where each one is cheaper", () => {
    const element = render(makeHass({ weeks: WEEKS }));
    click(element, { action: "toggle", week: "2026-11-06" });
    const first = element.shadowRoot.innerHTML.split("Weekend 13–15 nov")[0];
    assert.match(first, /Lisbona · 50\s€/);
    assert.match(first, /meno cara il 13 nov \(40\s€\)/);
    assert.match(first, /3 destinazioni · nascondi/);
    click(element, { action: "toggle", week: "2026-11-06" });
    assert.doesNotMatch(element.shadowRoot.innerHTML.split("Weekend 13–15 nov")[0], /Lisbona · 50/);
  });

  test("the airport filter is remembered on the device", () => {
    const hass = makeHass({ weeks: WEEKS });
    const element = render(hass);
    click(element, { action: "airport", airport: "BGY" });
    assert.equal(storage.get(`flight-prices-card:${DEVICE}:airport`), "BGY");
    assert.doesNotMatch(element.shadowRoot.innerHTML, /Barcellona/);
    assert.match(element.shadowRoot.innerHTML, /Il più economico da BGY/);
    // A new card on the same device starts from it.
    assert.match(render(hass).shadowRoot.innerHTML, /Il più economico da BGY/);
    click(element, { action: "airport", airport: "" });
    assert.equal(storage.has(`flight-prices-card:${DEVICE}:airport`), false);
  });

  test("booking links, two buttons for two tickets", () => {
    const weeks = [
      week(1, "2026-11-06", "2026-11-08", [
        trip("PAR", "MXP", 120, { source: "google", link: "https://out", return_link: "https://back" }),
      ]),
    ];
    const element = render(makeHass({ weeks }));
    const html = element.shadowRoot.innerHTML;
    assert.match(html, /Due biglietti/);
    assert.match(html, /data-url="https:\/\/back"/);
    assert.match(html, /Google Flights/);
    click(element, { action: "link", url: "https://back" });
    assert.deepEqual(opened, ["https://back"]);
  });

  test("a week without flights says which hours were searched", () => {
    const weeks = [...WEEKS, week(3, "2026-11-20", "2026-11-22", [])];
    const html = render(makeHass({ weeks })).shadowRoot.innerHTML;
    assert.match(html, /Nessun volo nelle fasce: andata ven 19–24, ritorno dom 14–24/);
  });

  test("red when a source keeps failing", () => {
    const failing = search("google", "2026-10-01T10:00:00+00:00", { error: "captcha" });
    const html = render(makeHass({ weeks: WEEKS, searches: [failing] })).shadowRoot.innerHTML;
    assert.match(html, /mdi:airplane-alert/);
    assert.match(html, /ultimo tentativo fallito: captcha/);
  });

  test("no search yet", () => {
    const html = render({ states: {}, entities: {}, locale: { language: "en" } }).shadowRoot.innerHTML;
    assert.match(html, /No Flight Prices search found/);
  });

  test("draws again only when a state of the search changes", () => {
    const hass = makeHass({ weeks: WEEKS });
    const element = render(hass);
    element.shadowRoot.innerHTML = "untouched";
    element.hass = { ...hass, states: { ...hass.states, "sensor.unrelated": { state: "2", attributes: {} } } };
    assert.equal(element.shadowRoot.innerHTML, "untouched");
    const changed = { ...WEEKS[0], state: "39" };
    element.hass = { ...hass, states: { ...hass.states, [changed.entity_id]: changed } };
    assert.notEqual(element.shadowRoot.innerHTML, "untouched");
  });
});
