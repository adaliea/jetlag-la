# Jet Lag: Hide + Seek Los Angeles

An LA-specific small game for the official Jet Lag: The Game Hide + Seek
home game.

## Start here

1. Read [RULES_LA.md](RULES_LA.md).
2. Open [map/index.html](map/index.html) in a browser.
3. At Union Station, randomly choose the first hiding pair and begin a 40-minute
   hiding period.

The standard game uses Metro Rail stations inside the map as eligible hiding
zone centers. The interactive map shows the agreed game border, current rail
lines, neighborhood divisions, and a 400 m hiding-zone preview for every
eligible station. It also includes opt-in device location, an official-rules
link, an in-map LA special-rules panel, and a rendered full-rules page with
the safety exclusion list.

For an offline lookup table, use
[map/station-reference.csv](map/station-reference.csv).

## Why this differs from the older LA map

The useful core of
[kavigupta/jet-lag-small-game-la](https://github.com/kavigupta/jet-lag-small-game-la)
is retained: a central-LA border, neighborhood/CDP divisions, and a
transit-centered game.

The older map used July 2023 rail data and included 530 multi-line bus stops,
for 581 total hiding centers. This edition uses current Metro Rail data and
keeps the standard game within the official small-game recommendation of
30-100 stations. In particular, it includes the three D Line Extension
Section 1 stations now present in Metro's current feed.

## Rebuild the map

The checked-in map is ready to play. To refresh it after a Metro service
change:

```powershell
Invoke-WebRequest -Uri 'https://gitlab.com/LACMTA/gtfs_rail/-/raw/master/gtfs_rail.zip' -OutFile 'gtfs_rail.zip'
Expand-Archive -Path gtfs_rail.zip -DestinationPath current-gtfs-rail -Force
python scripts/build_map.py
```

The builder intentionally uses the older project's hand-drawn central-LA
border and neighborhood divisions as its geographic base.

## Deploy to Cloudflare Workers

The `map/` directory is configured as a static Workers asset bundle in
`wrangler.toml`.

```powershell
npm install
npm run dev
npm run deploy
```

`npm run deploy` rebuilds the map before publishing it. Wrangler will prompt
for Cloudflare authentication if needed. To change the Workers project name,
edit `name` in `wrangler.toml`.

## Sources

- [Official home-game rules](https://jetlag.denull.ru/en/rules/)
- [LA Metro current rail GTFS](https://gitlab.com/LACMTA/gtfs_rail)
- [Older LA map and source data](https://github.com/kavigupta/jet-lag-small-game-la)
