# Geospatial Weather Search Demo (Python)

This demonstration runs a MongoDB geospatial aggregation using:
- `latitude`
- `longitude`
- `wind.speed.rate`
- `airTemperature.value`

The script is designed to mirror this style of query:
- Start with `$geoNear`
- Filter by wind and air temperature
- Project a clean result shape

## Dataset

Default `.env.example` values use:
- `DB_NAME=sample_weatherdata`
- `COLLECTION_NAME=data`

In plain language, `sample_weatherdata.data` is a collection of weather station observations.
Each document can include:
- Where the station is (`position` with longitude/latitude)
- Wind information (`wind.speed.rate`)
- Air temperature (`airTemperature.value`)
- Station identifier (`stn`)

## What This Script Does (Plain English)

1. Starts from a map point you provide (latitude/longitude).
2. Looks for nearby weather records within your radius.
3. Keeps only rows where:
- wind speed is above your minimum
- air temperature is below your maximum
4. Prints a simple table with station, distance, wind speed, and temperature.

If nothing matches, it also shows nearby data ranges so you can pick better filter values.

## Prerequisites

- Python 3.10+
- MongoDB Atlas cluster with access to `sample_weatherdata`
- A `2dsphere` index on the location field used by `$geoNear`

For `sample_weatherdata.data`, create index if needed:

```javascript
db.data.createIndex({ position: "2dsphere" })
```

## Setup

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Create your `.env` file:

```bash
cp .env.example .env
```

3. Edit `.env` values:

```env
DB_NAME=sample_weatherdata
COLLECTION_NAME=data

# Your Atlas connection string (must have access to sample_weatherdata)
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-host>/?retryWrites=true&w=majority

LATITUDE=40.730610
LONGITUDE=-73.935242
MIN_WIND_SPEED_RATE=5
MAX_AIR_TEMPERATURE_VALUE=0
MAX_DISTANCE_METERS=100000
GEO_FIELD=position
```

## Run

Use values from `.env`:

```bash
python3 main.py
```

If no rows match, the script now prints:
- wind/temp value ranges found within the radius
- a preview of the 5 nearest rows without wind/temp filtering

This makes it easier to choose threshold values that return interesting results.

Override from CLI:

```bash
python3 main.py \
  --latitude 40.730610 \
  --longitude -73.935242 \
  --min-wind-speed-rate 5 \
  --max-air-temperature-value 0 \
  --max-distance-meters 100000 \
  --geo-field position \
  --limit 10
```

## Sample Inputs That Usually Return Interesting Results

1. NYC area, broad filters (good first run):

```bash
python3 main.py --latitude 40.730610 --longitude -73.935242 --min-wind-speed-rate 1 --max-air-temperature-value 20 --max-distance-meters 300000 --limit 10
```

2. Great Lakes area, colder and windier:

```bash
python3 main.py --latitude 41.8781 --longitude -87.6298 --min-wind-speed-rate 6 --max-air-temperature-value 0 --max-distance-meters 600000 --limit 10
```

3. Alaska area, very cold focus:

```bash
python3 main.py --latitude 61.2181 --longitude -149.9003 --min-wind-speed-rate 4 --max-air-temperature-value -10 --max-distance-meters 800000 --limit 10
```

## Aggregation Pipeline Steps

The script builds this pipeline:

1. `$geoNear`
- `near` is the user-provided point `[longitude, latitude]`.
- `key` is `GEO_FIELD` (default `position`).
- `distanceField` is `distanceFromTeam`.
- `maxDistance` comes from user input.
- `spherical` is `true`.

2. `$match`
- `wind.speed.rate > MIN_WIND_SPEED_RATE`
- `airTemperature.value < MAX_AIR_TEMPERATURE_VALUE`

3. `$project`
- `stationName: "$stn"`
- `distanceInKm: distanceFromTeam / 1000`
- `windSpeed: "$wind.speed.rate"`
- `temp: "$airTemperature.value"`

4. `$sort`
- By `distanceInKm` ascending.

5. `$limit`
- Controlled by `--limit` (default: `10`).

## Pipeline Definition (Mongo Shell Style)

```javascript
db.data.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [ -73.935242, 40.730610 ] },
      key: "position",
      distanceField: "distanceFromTeam",
      maxDistance: 100000,
      spherical: true
    }
  },
  {
    $match: {
      "wind.speed.rate": { $gt: 5 },
      "airTemperature.value": { $lt: 0 }
    }
  },
  {
    $project: {
      _id: 0,
      stationName: "$stn",
      distanceInKm: { $divide: ["$distanceFromTeam", 1000] },
      windSpeed: "$wind.speed.rate",
      temp: "$airTemperature.value"
    }
  }
])
```

## Atlas GUI Walkthrough

1. Open Atlas and go to your cluster.
2. Click `Browse Collections`.
3. Open database `sample_weatherdata`, collection `data`.
4. Open the `Aggregation` tab.
5. Add stage 1: `$geoNear`

```json
{
  "near": { "type": "Point", "coordinates": [ -73.935242, 40.730610 ] },
  "key": "position",
  "distanceField": "distanceFromTeam",
  "maxDistance": 100000,
  "spherical": true
}
```

6. Add stage 2: `$match`

```json
{
  "wind.speed.rate": { "$gt": 5 },
  "airTemperature.value": { "$lt": 0 }
}
```

7. Add stage 3: `$project`

```json
{
  "_id": 0,
  "stationName": "$stn",
  "distanceInKm": { "$divide": [ "$distanceFromTeam", 1000 ] },
  "windSpeed": "$wind.speed.rate",
  "temp": "$airTemperature.value"
}
```

8. Optional: add stage 4 as `$sort`:

```json
{
  "distanceInKm": 1
}
```

9. Optional: add stage 5 as `$limit`:

```json
10
```

10. Click `Run`.
11. Adjust coordinates and threshold values to explore nearby extreme-weather stations.

## Troubleshooting

If you get this error:

`$geoNear requires a 2d or 2dsphere index, but none were found`

check all three are aligned:

1. `.env` database and collection (`DB_NAME`, `COLLECTION_NAME`)
2. The geospatial field used by the query (`GEO_FIELD`)
3. The index created in that same database/collection/field

Example for this demo:

```javascript
use sample_weatherdata
db.data.createIndex({ position: "2dsphere" })
```
