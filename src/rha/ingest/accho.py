"""Load the private ACCHO location file from a local path.

SENSITIVE (Indigenous Data Sovereignty; see CLAUDE.md). Rules enforced here:

* Only the columns needed for spatial counting are read (coordinates, state,
  geocode method). Names, addresses and phone numbers are never loaded.
* Nothing row-level is logged or printed: only aggregate counts.
* The returned frame is for in-memory use only; callers must not write it out.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

log = logging.getLogger(__name__)

ACCHO_COLUMNS = ["state", "latitude", "longitude", "geocode_method"]

# Generous bounding box for Australia incl. Torres Strait / Tasmania (GDA2020 lon/lat).
_AU_BBOX = {"lat": (-44.5, -9.0), "lon": (112.0, 154.5)}


def load_accho_points(path: Path, crs: str = "EPSG:7844") -> gpd.GeoDataFrame:
    """Return ACCHO points as a GeoDataFrame with columns state, geocode_method, geometry.

    Rows with identical coordinates are treated as duplicates and only the first is
    kept (decision 2026-11-25: go off the coordinates).
    """
    df = pd.read_excel(path, usecols=ACCHO_COLUMNS)
    n_in = len(df)
    df = df.dropna(subset=["latitude", "longitude"])
    n_nocoord = n_in - len(df)

    in_box = df["latitude"].between(*_AU_BBOX["lat"]) & df["longitude"].between(*_AU_BBOX["lon"])
    n_outside = int((~in_box).sum())
    df = df[in_box]

    dup = df.duplicated(subset=["latitude", "longitude"], keep="first")
    n_dup = int(dup.sum())
    df = df[~dup]

    df["geocode_method"] = df["geocode_method"].astype(str).str.strip().str.lower()
    gdf = gpd.GeoDataFrame(
        df[["state", "geocode_method"]].reset_index(drop=True),
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs=crs,
    )
    log.info(
        "ACCHO: %d rows read, %d without coords, %d outside AU bbox, %d duplicate coords "
        "dropped, %d points kept",
        n_in, n_nocoord, n_outside, n_dup, len(gdf),
    )
    gdf.attrs["qa"] = {
        "rows_read": n_in,
        "dropped_no_coords": n_nocoord,
        "dropped_outside_bbox": n_outside,
        "dropped_duplicate_coords": n_dup,
        "points_kept": len(gdf),
    }
    return gdf
