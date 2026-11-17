# TXST Round Rock weather station archive

Observation archive for the Texas State University Round Rock weather station
(TexMesonet station 142, Synoptic/MesoWest ID TW142), operated by the
Department of Geography and Environmental Studies. It feeds the interactive
meteogram on the department weather page.

## How it works

- `collect.py` asks the public TexMesonet API for the station's last 24 hours
  and merges the records into monthly CSV files. Rows are keyed by observation
  time, so repeat runs only add what is new and a missed run is filled in by
  the next one (up to a day later).
- `.github/workflows/collect.yml` runs the collector every 15 minutes on
  GitHub Actions and commits any new rows.
- `meteogram/meteogram.html` is the chart. It reads `data/index.json` and the
  monthly files straight from this repository.

## Data layout

```
data/index.json            first/last time, row counts, list of monthly files
data/2026/2026-11.csv      one file per UTC month
```

Columns (native TexMesonet units, times in UTC):

| Column | Units |
|---|---|
| `time_utc` | ISO 8601, UTC |
| `air_temp_2m_c`, `air_temp_9m_c` | deg C |
| `rh_pct` | percent |
| `precip_mm` | millimeters in the record interval |
| `wind_speed_10m_ms`, `wind_gust_10m_ms` | meters per second |
| `wind_dir_10m_deg` | degrees |
| `pressure_mb` | millibars |
| `solar_wm2` | watts per square meter |
| `soil_temp_5cm_c` ... `soil_temp_50cm_c` | deg C |
| `soil_vwc_5cm` ... `soil_vwc_50cm` | m3/m3 |

Records are 15-minute values, the finest resolution the TexMesonet API
provides. The station itself logs every 5 minutes.

## Running by hand

```
python collect.py                # last 24 hours
python collect.py --minutes 180  # shorter window
```

No packages beyond the Python standard library are needed.

## Changing the data source

The TexMesonet call is isolated in `fetch_texmesonet()`. To switch to another
feed, add a function that returns the same list of row dictionaries and call
it from `main()`. The CSV layout and the meteogram do not need to change.

## Credit

Station data are collected in partnership with the Texas Water Development
Board's TexMesonet. Contact: Kenny L. Tapp, k.tapp@txst.edu.
