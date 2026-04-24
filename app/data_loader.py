import logging
import os

import numpy as np
import pandas as pd
from scipy.spatial import KDTree

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUEL_PRICE_FILE_PATH = os.path.join(BASE_DIR, "data_files", "final_fuel_price_data.csv")
CITY_COORDINATES_FILE_PATH = os.path.join(BASE_DIR, "data_files", "state_city_coordinates.csv")

# Singletons — built once at startup
_fuel_data: list[dict] | None = None
_kdtree: KDTree | None = None
_city_coord_data: pd.DataFrame | None = None


def get_fuel_data() -> tuple[list[dict], KDTree]:
    """Load fuel station data and build a KD-Tree for spatial lookups."""
    global _fuel_data, _kdtree

    if _fuel_data is not None:
        return _fuel_data, _kdtree

    df = pd.read_csv(FUEL_PRICE_FILE_PATH)
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["retail_price", "lat", "lng"])

    df["retail_price"] = pd.to_numeric(
        df["retail_price"].astype(str).str.replace(r"[$,]", "", regex=True),
        errors="coerce",
    )
    df = df.dropna(subset=["retail_price"])

    _fuel_data = (
        df[["opis_truckstop_id", "truckstop_name", "address", "city", "state", "retail_price", "lat", "lng"]]
        .rename(columns={
            "opis_truckstop_id": "id",
            "truckstop_name": "name",
            "retail_price": "price",
            "lng": "lon",
        })
        .to_dict(orient="records")
    )

    coords_rad = np.radians([[s["lat"], s["lon"]] for s in _fuel_data])
    _kdtree = KDTree(coords_rad)

    logger.info("Loaded %d fuel stations.", len(_fuel_data))
    return _fuel_data, _kdtree


def geocode_from_csv(place: str) -> list[float] | None:
    """Convert 'City, ST' to [lon, lat] using a local coordinates CSV."""
    global _city_coord_data

    if _city_coord_data is None:
        _city_coord_data = pd.read_csv(CITY_COORDINATES_FILE_PATH)

    parts = [p.strip() for p in place.split(",")]
    if len(parts) < 2:
        return None

    city, state = parts[0], parts[1]
    match = _city_coord_data[
        (_city_coord_data["city"].str.lower() == city.lower())
        & (_city_coord_data["state"].str.upper() == state.upper())
    ]

    if match.empty:
        return None

    row = match.iloc[0]
    return [float(row["lng"]), float(row["lat"])]