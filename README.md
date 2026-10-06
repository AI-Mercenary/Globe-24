# Globe-24

A real-time 3D globe built with three.js. All data is live and from public sources; nothing is simulated.

**Live:** https://ai-mercenary.github.io/Globe-24/

## Features

- **Realistic Earth**: NASA Blue Marble by day, Black Marble city lights by night, lit by the sun's actual current position
- **Satellite imagery anywhere**: click the globe to open imagery
  - High-res mosaic (Esri World Imagery), down to street level
  - Dated 30 m passes from Sentinel-2 / Landsat (NASA HLS); finds the latest pass automatically
  - Daily global imagery (NASA VIIRS)
  - 10-minute geostationary frames (GOES-East/West, Himawari), with a calendar and time-lapse
  - 3D terrain and buildings (MapLibre + AWS terrain + OpenStreetMap)
  - Current weather at that spot (Open-Meteo)
- **Live layers**: earthquakes (USGS, last 24 h), natural events (NASA EONET), satellites and the ISS with its orbit (CelesTrak + SGP4)
- **World clocks**: 90 cities grouped by continent
- **Country locator**: 242 countries with flags, capital, population, currency, languages and local time
- **Around the world**: rotating real imagery of random places
- **Tools**: great-circle measurement, MGRS coordinates, coordinate/place search, cinematic camera flights
- Works on desktop and mobile; adapts render resolution to keep the frame rate up

## Run locally

It's a single static page. Any static server works:

```bash
python -m http.server 8000
```

Or use the bundled server, which adds a satellite-data cache and the World Bank population lookup:

```bash
python serve.py        # http://localhost:5173
```

No API keys are needed.

## Data sources

Esri World Imagery · NASA GIBS (VIIRS, HLS, GOES, Himawari) · USGS Earthquake Hazards · NASA EONET · CelesTrak · Natural Earth · Open-Meteo · OpenStreetMap Nominatim · mledoze/countries · World Bank · flagcdn
