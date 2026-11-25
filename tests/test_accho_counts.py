"""ACCHO loading and per-SA2 counting, on SYNTHETIC data only (never real ACCHO rows)."""

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from rha.ingest.accho import load_accho_points
from rha.integrate.build_master import count_points_per_sa2

CRS = "EPSG:7844"


def _write_fake_accho(tmp_path):
    df = pd.DataFrame(
        {
            "name": ["Fake Service A", "Fake Service B", "Fake Service C", "Fake D", "Fake E"],
            "state": ["NSW", "NSW", "NSW", "NSW", "NSW"],
            "address": ["1 Test St"] * 5,
            "phone": ["0000"] * 5,
            "latitude": [-29.5, -29.5, -29.4, 10.0, -29.6],    # B duplicates A; D outside AU
            "longitude": [140.5, 140.5, 141.5, 140.0, 140.6],
            "geocode_method": ["nominatim", "nominatim", "Manual ", "manual", "manual"],
        }
    )
    p = tmp_path / "synthetic_points.xlsx"
    df.to_excel(p, index=False)
    return p


def test_loader_drops_sensitive_columns_duplicates_and_out_of_bbox(tmp_path):
    pts = load_accho_points(_write_fake_accho(tmp_path))
    assert list(pts.columns) == ["state", "geocode_method", "geometry"]
    assert len(pts) == 3
    assert pts.attrs["qa"]["dropped_duplicate_coords"] == 1
    assert pts.attrs["qa"]["dropped_outside_bbox"] == 1
    assert set(pts["geocode_method"]) == {"nominatim", "manual"}


def _sa2():
    return gpd.GeoDataFrame(
        {"sa2_code21": ["100000001", "100000002", "199999499"]},
        geometry=[box(140, -30, 141, -29), box(141, -30, 142, -29), None],
        crs=CRS,
    )


def test_counts_within_and_manual(tmp_path):
    pts = load_accho_points(_write_fake_accho(tmp_path))
    counts, qa = count_points_per_sa2(pts, _sa2(), max_nearest_m=1000, metric_crs="EPSG:3577")
    c = counts.set_index("sa2_code21")
    assert c.loc["100000001", "n"] == 2 and c.loc["100000001", "n_manual"] == 1
    assert c.loc["100000002", "n"] == 1 and c.loc["100000002", "n_manual"] == 1
    assert qa == {"points": 3, "assigned_within": 3, "assigned_nearest": 0,
                  "unassigned": 0, "sa2_with_points": 2}
    assert set(counts.columns) == {"sa2_code21", "n", "n_manual"}


def test_nearest_fallback_respects_max_distance():
    pts = gpd.GeoDataFrame(
        {"state": ["NSW", "NSW"], "geocode_method": ["manual", "manual"]},
        # ~500 m and ~50 km south of the SA2 boxes' southern edge (lat -30)
        geometry=gpd.points_from_xy([140.5, 140.5], [-30.0045, -30.45]),
        crs=CRS,
    )
    counts, qa = count_points_per_sa2(pts, _sa2(), max_nearest_m=1000, metric_crs="EPSG:3577")
    assert qa["assigned_nearest"] == 1 and qa["unassigned"] == 1
    assert counts.set_index("sa2_code21").loc["100000001", "n"] == 1
