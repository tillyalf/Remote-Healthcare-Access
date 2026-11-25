"""Remoteness assignment rule, on synthetic SA1s/RA polygons."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from rha.prep.remoteness import assign_sa1_ra, sa2_remoteness


def _sa1(rows):
    return pd.DataFrame(rows, columns=["SA2_CODE_2021", "ra_class", "pop", "area"])


def test_population_majority_beats_area_majority():
    # Town SA1 (major city, small area, most people) + big sparse SA1 (outer regional).
    df = _sa1([("100000001", 0, 900, 5.0), ("100000001", 2, 100, 95.0)])
    out = sa2_remoteness(df, split_threshold=0.9).iloc[0]
    assert out.ra_code == 0
    assert out.ra_method == "population"
    assert out.ra_pop_share == pytest.approx(0.9)
    assert out.ra_area_share == pytest.approx(0.05)
    assert not out.ra_split  # 0.9 is not < 0.9
    assert out.ra_n_classes == 2


def test_split_flag_below_threshold():
    df = _sa1([("100000002", 1, 600, 50.0), ("100000002", 2, 400, 50.0)])
    out = sa2_remoteness(df, split_threshold=0.9).iloc[0]
    assert out.ra_code == 1
    assert out.ra_split


@pytest.mark.parametrize("pops", [(0, 0), (None, None)])
def test_area_fallback_when_population_zero_or_missing(pops):
    df = _sa1([("100000003", 3, pops[0], 30.0), ("100000003", 4, pops[1], 70.0)])
    out = sa2_remoteness(df, split_threshold=0.9).iloc[0]
    assert out.ra_method == "area"
    assert out.ra_code == 4
    assert pd.isna(out.ra_pop_share)
    assert out.ra_area_share == pytest.approx(0.7)
    assert out.ra_split


def test_tie_breaks_to_larger_area_then_more_remote():
    df = _sa1([("100000004", 1, 50, 10.0), ("100000004", 2, 50, 10.0)])
    assert sa2_remoteness(df).iloc[0].ra_code == 2


def test_single_class_sa2():
    df = _sa1([("100000005", 0, 10, 1.0), ("100000005", 0, 20, 1.0)])
    out = sa2_remoteness(df).iloc[0]
    assert out.ra_pop_share == 1.0 and not out.ra_split and out.ra_n_classes == 1


def test_assign_sa1_ra_point_in_polygon():
    crs = "EPSG:7844"
    ra = gpd.GeoDataFrame({"ra_class": [0, 3]}, geometry=[box(140, -30, 141, -29),
                                                          box(141, -30, 142, -29)], crs=crs)
    sa1 = gpd.GeoDataFrame(
        {"SA1_CODE_2021": ["10000000001", "10000000002"]},
        geometry=[box(140.1, -29.9, 140.2, -29.8), box(141.5, -29.9, 141.6, -29.8)],
        crs=crs,
    )
    out = assign_sa1_ra(sa1, ra).set_index("SA1_CODE_2021")
    assert out.loc["10000000001", "ra_class"] == 0
    assert out.loc["10000000002", "ra_class"] == 3
    assert (out["ra_assign"] == "within").all()
