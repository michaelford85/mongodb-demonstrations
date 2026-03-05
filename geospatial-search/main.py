import argparse
import os
from typing import Any

from dotenv import load_dotenv
from pymongo import MongoClient


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def get_float(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number. Received: {value}") from exc


def parse_args():
    parser = argparse.ArgumentParser(
        description="Geospatial search demo against weather data with geo + wind + temperature filters."
    )
    parser.add_argument("--latitude", type=float, help="Latitude for the search point.")
    parser.add_argument("--longitude", type=float, help="Longitude for the search point.")
    parser.add_argument(
        "--min-wind-speed-rate",
        type=float,
        help="Minimum wind.speed.rate to include in results (wind.speed.rate > value).",
    )
    parser.add_argument(
        "--max-air-temperature-value",
        type=float,
        help="Maximum airTemperature.value to include (airTemperature.value < value).",
    )
    parser.add_argument(
        "--max-distance-meters",
        type=float,
        default=100000,
        help="Maximum distance in meters from the search point (optional).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results to print.",
    )
    parser.add_argument(
        "--geo-field",
        type=str,
        default=None,
        help="Geospatial field used by $geoNear (for example: position).",
    )
    return parser.parse_args()


def build_pipeline(
    latitude: float,
    longitude: float,
    min_wind_speed_rate: float,
    max_air_temperature_value: float,
    max_distance_meters: float,
    geo_field: str,
    limit: int,
):
    return [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [longitude, latitude]},
                "key": geo_field,
                "distanceField": "distanceFromTeam",
                "maxDistance": max_distance_meters,
                "spherical": True,
            }
        },
        {
            "$match": {
                "wind.speed.rate": {"$gt": min_wind_speed_rate},
                "airTemperature.value": {"$lt": max_air_temperature_value},
            }
        },
        {
            "$project": {
                "_id": 0,
                "callLetters": "$callLetters",
                "distanceInKm": {"$round": [{"$divide": ["$distanceFromTeam", 1000]}, 2]},
                "windSpeed": "$wind.speed.rate",
                "temp": "$airTemperature.value",
            }
        },
        {"$sort": {"distanceInKm": 1}},
        {"$limit": limit},
    ]


def build_nearby_preview_pipeline(
    latitude: float,
    longitude: float,
    max_distance_meters: float,
    geo_field: str,
):
    return [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [longitude, latitude]},
                "key": geo_field,
                "distanceField": "distanceFromTeam",
                "maxDistance": max_distance_meters,
                "spherical": True,
            }
        },
        {
            "$project": {
                "_id": 0,
                "callLetters": "$callLetters",
                "distanceInKm": {"$round": [{"$divide": ["$distanceFromTeam", 1000]}, 2]},
                "windSpeed": "$wind.speed.rate",
                "temp": "$airTemperature.value",
            }
        },
        {"$sort": {"distanceInKm": 1}},
        {"$limit": 5},
    ]


def build_nearby_range_pipeline(
    latitude: float,
    longitude: float,
    max_distance_meters: float,
    geo_field: str,
):
    return [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [longitude, latitude]},
                "key": geo_field,
                "distanceField": "distanceFromTeam",
                "maxDistance": max_distance_meters,
                "spherical": True,
            }
        },
        {
            "$group": {
                "_id": None,
                "minWind": {"$min": "$wind.speed.rate"},
                "maxWind": {"$max": "$wind.speed.rate"},
                "minTemp": {"$min": "$airTemperature.value"},
                "maxTemp": {"$max": "$airTemperature.value"},
                "count": {"$sum": 1},
            }
        },
        {"$project": {"_id": 0}},
    ]


def has_geo_index(collection, geo_field: str) -> bool:
    for spec in collection.index_information().values():
        for field, index_type in spec.get("key", []):
            if field == geo_field and index_type in ("2d", "2dsphere"):
                return True
    return False


def main():
    load_dotenv()
    args = parse_args()

    uri = require_env("MONGODB_URI")
    db_name = require_env("DB_NAME")
    collection_name = require_env("COLLECTION_NAME")

    latitude = (
        args.latitude if args.latitude is not None else get_float(os.getenv("LATITUDE"), "LATITUDE")
    )
    longitude = (
        args.longitude
        if args.longitude is not None
        else get_float(os.getenv("LONGITUDE"), "LONGITUDE")
    )
    min_wind_speed_rate = (
        args.min_wind_speed_rate
        if args.min_wind_speed_rate is not None
        else get_float(os.getenv("MIN_WIND_SPEED_RATE"), "MIN_WIND_SPEED_RATE")
    )
    max_air_temperature_value = (
        args.max_air_temperature_value
        if args.max_air_temperature_value is not None
        else get_float(os.getenv("MAX_AIR_TEMPERATURE_VALUE"), "MAX_AIR_TEMPERATURE_VALUE")
    )
    max_distance_meters = (
        args.max_distance_meters
        if args.max_distance_meters is not None
        else get_float(os.getenv("MAX_DISTANCE_METERS"), "MAX_DISTANCE_METERS")
    )
    geo_field = args.geo_field if args.geo_field else os.getenv("GEO_FIELD", "position")

    client = MongoClient(uri)
    try:
        collection = client[db_name][collection_name]
        if not has_geo_index(collection, geo_field):
            raise ValueError(
                f"No 2d/2dsphere index found on '{db_name}.{collection_name}.{geo_field}'. "
                f"Create one with: db.{collection_name}.createIndex({{{geo_field}: '2dsphere'}})"
            )

        pipeline = build_pipeline(
            latitude=latitude,
            longitude=longitude,
            min_wind_speed_rate=min_wind_speed_rate,
            max_air_temperature_value=max_air_temperature_value,
            max_distance_meters=max_distance_meters,
            geo_field=geo_field,
            limit=args.limit,
        )
        results = list(collection.aggregate(pipeline))

        print("=" * 72)
        print(
            f"Geo Search Center: ({latitude}, {longitude}) | Radius: {max_distance_meters} m"
        )
        print(f"Geo Field: {geo_field}")
        print(
            f"Filters: wind.speed.rate > {min_wind_speed_rate} | "
            f"airTemperature.value < {max_air_temperature_value}"
        )
        print("=" * 72)
        if not results:
            print("No matching records found.")
            ranges = list(
                collection.aggregate(
                    build_nearby_range_pipeline(
                        latitude=latitude,
                        longitude=longitude,
                        max_distance_meters=max_distance_meters,
                        geo_field=geo_field,
                    )
                )
            )
            preview = list(
                collection.aggregate(
                    build_nearby_preview_pipeline(
                        latitude=latitude,
                        longitude=longitude,
                        max_distance_meters=max_distance_meters,
                        geo_field=geo_field,
                    )
                )
            )

            if ranges:
                r = ranges[0]
                print(
                    f"Nearby range in radius: wind.speed.rate {r.get('minWind')}..{r.get('maxWind')} | "
                    f"airTemperature.value {r.get('minTemp')}..{r.get('maxTemp')} | docs={r.get('count')}"
                )
            if preview:
                print("Nearest sample rows (without wind/temp filters):")
                print(
                    f"{'#':<4}{'Station':<14}{'Distance (km)':<16}"
                    f"{'Wind Speed':<12}{'Air Temp':<10}"
                )
                print("-" * 72)
                for idx, doc in enumerate(preview, start=1):
                    print(
                        f"{idx:<4}{str(doc.get('stationName', 'N/A')):<14}"
                        f"{str(doc.get('distanceInKm', 'N/A')):<16}"
                        f"{str(doc.get('windSpeed', 'N/A')):<12}"
                        f"{str(doc.get('temp', 'N/A')):<10}"
                    )
                print("-" * 72)
                print(
                    "Try relaxing filters, e.g. --min-wind-speed-rate 1 --max-air-temperature-value 20"
                )
            return

        print(
            f"{'#':<4}{'Station':<14}{'Distance (km)':<16}"
            f"{'Wind Speed':<12}{'Air Temp':<10}"
        )
        print("-" * 72)
        for idx, doc in enumerate(results, start=1):
            station_name = doc.get("stationName", "N/A")
            distance_km = doc.get("distanceInKm", "N/A")
            wind_speed = doc.get("windSpeed", "N/A")
            temp = doc.get("temp", "N/A")
            print(
                f"{idx:<4}{str(station_name):<14}{str(distance_km):<16}"
                f"{str(wind_speed):<12}{str(temp):<10}"
            )
        print("-" * 72)
    finally:
        client.close()


if __name__ == "__main__":
    main()
