# Live faction card

`render.py` pulls faction data from the Torn API and draws `public/card.png`.
A GitHub Actions workflow (`.github/workflows/update-card.yml`) reruns it every
10 minutes and publishes the image with GitHub Pages.

- Edit the words, tiles, requirements and upgrade maximums in `config.json`.
- The API key is read from the `TORN_API_KEY` repository secret. Never put it in a file.
- `python render.py --demo` draws the card with sample numbers.
- `python render.py --dump` prints the raw API data (useful for checking upgrade names).

Fonts: Bebas Neue and Barlow Condensed, SIL Open Font License 1.1.
