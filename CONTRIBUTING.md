# Contributing

Thanks for helping. Bug reports, fixes, new options and new sources are all welcome. For anything bigger than a small fix, open an issue first, so we can agree on the approach before you write the code. Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## Be gentle with the sources

Neither Ryanair nor Google Flights offers this as an API, and both can block clients that ask too much. Keep it that way:

- Do not lower `RYANAIR_DELAY` or `GOOGLE_DELAY` in `const.py`, or add requests to a round, without discussing it in an issue first.
- The Google Flights round stops at the first sign of a block (consent page, captcha, HTTP 429) or after 5 errors in a row (`GOOGLE_MAX_ERRORS`). A new source has to stop the same way.
- Results are saved, so a restart or a change of options must not search again unless what a source searches has changed.
- A new source needs to work without an account or an API key, and to say in the README what it reads and how often.

## Reporting a security problem

Do not open a public issue: see [SECURITY.md](SECURITY.md).

## Development

You need Python 3.14, the version the tests run on, and Node.js 24 for the card's tests.

The repository has two parts. `app/` is the app: `flight_prices_engine`, the search engine, with its sources, its HTTP API and its Docker image; it needs no Home Assistant. `custom_components/flight_prices` is the integration: forms, sensors and card, talking to the app. Each has its own environment:

```
python -m venv .venv                                # the integration
.venv/bin/pip install -r requirements_test.txt      # .venv\Scripts\pip on Windows
pytest
ruff check . && ruff format --check .
node --test "tests/card/*.test.mjs"

python -m venv app/.venv                            # the app
app/.venv/bin/pip install -r app/requirements_test.txt
cd app && .venv/bin/pytest
```

The integration's tests fake the app, counting the requests with the engine's own code. To try both together, start the engine with `python -m flight_prices_engine --data ./data` and add the integration with the address `http://localhost:8765`.

The dashboard card is one JavaScript file with no dependencies and no build step (`custom_components/flight_prices/frontend/flight-prices-card.js`); keep it that way, so what Home Assistant loads is what is in the repository. Its tests replace the browser with the few globals the card uses and read what it renders.

The tests never reach Ryanair or Google: they read saved answers from `app/tests/fixtures`, served by a local fake of Ryanair, and Google is replaced in the tests. When you save a new answer, keep only what the test needs and remove cookies or anything else tied to your browser. The same commands run on every push and pull request.

## What a pull request needs

- One change per pull request, with tests for the behaviour it adds or fixes.
- Texts shown in Home Assistant live in `strings.json` and `translations/en.json` (identical), with one more file per language in `translations/`; the card keeps its own texts in `STRINGS`, at the top of `flight-prices-card.js`, and so does the app's page (`app/flight_prices_engine/web/index.html`); the app's options are in `app/translations/`. Add every new key to every language in every place; if you cannot translate it, leave the English text and say so in the pull request. A new language needs both too: a file in `translations/` and a block in `STRINGS`.
- Update `README.md` when sensors, attributes, options or the number of requests change.
- AI coding tools are fine, as they were for this project: read and test what you submit as if you had written it, and say in the pull request that you used one.
- Commit messages say what changes for the person using the integration, for example *Leave out countries, keep one trip per destination and airport*.

## Dependencies

The integration installs nothing in Home Assistant. The app's requirements are pinned to exact versions in `app/requirements.txt`, which both the image and the engine's tests install.

[Renovate](https://docs.renovatebot.com) opens the updates on Monday mornings, once a release is at least 7 days old (`renovate.json`). Updates of the test tools and of the GitHub Actions merge themselves when the tests pass. Updates of `app/requirements.txt` and of the image in `app/Dockerfile` are merged by hand after reading the changelog, because they change the code that searches, and they reach users only with a release. `fast-flights` builds the Google Flights search, so check a real search after updating it.

## Releases

The app and the integration are released together, with the same version.

1. Bump `version` in `custom_components/flight_prices/manifest.json`, in `app/config.yaml` and in `app/flight_prices_engine/__init__.py`.
2. Push a tag `v` plus that version, for example `v1.0.0`.
3. The **Release** workflow checks that the tag matches both versions. It pushes the app's image for amd64 and aarch64 to `ghcr.io`, and creates a draft release with `flight_prices.zip`, which is what the Marketplace (HACS before Home Assistant 2026.11) installs. Write the notes and publish the draft by hand: releases are immutable once published.
