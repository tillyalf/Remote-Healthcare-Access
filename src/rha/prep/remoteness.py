"""Assign each SA2 one ABS Remoteness Area (RA) class.

RA 2021 is built from SA1s, so an SA2 can straddle classes. Rule (approved 2026-11-25):

1. Each SA1 gets the RA class whose polygon contains its representative point
   (SA1s nest within RA polygons; nearest polygon is a fallback for slivers).
2. SA1 population = sum of 2021 Mesh Block Count persons.
3. Each SA2 is assigned the class holding the largest share of its population
   (``ra_method = 'population'``). Where SA2 population is zero or missing, the
   class with the largest share of its area is used (``ra_method = 'area'``).
4. ``ra_pop_share`` / ``ra_area_share`` are the shares of the assigned class, stored so
   the split threshold can be changed without re-running joins. ``ra_split`` flags
   SA2s whose assigned-class share (by the method used) is below the threshold.

RA is a stratifier, not a model feature.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

RA_NAMES = {
    0: "Major Cities of Australia",
    1: "Inner Regional Australia",
    2: "Outer Regional Australia",
    3: "Remote Australia",
    4: "Very Remote Australia",
}


def assign_sa1_ra(
    sa1: gpd.GeoDataFrame, ra: gpd.GeoDataFrame, metric_crs: str = "EPSG:3577"
) -> pd.DataFrame:
    """Return ``SA1_CODE_2021, ra_class, ra_assign`` ('within' | 'nearest') for spatial SA1s."""
    sa1 = sa1[sa1.geometry.notna() & ~sa1.geometry.is_empty]
    pts = gpd.GeoDataFrame(
        {"SA1_CODE_2021": sa1["SA1_CODE_2021"].values},
        geometry=sa1.geometry.representative_point().values,
        crs=sa1.crs,
    )
    ra = ra.to_crs(pts.crs)[["ra_class", "geometry"]]
    hit = gpd.sjoin(pts, ra, how="left", predicate="within")
    hit = hit[~hit.index.duplicated(keep="first")]
    out = hit[["SA1_CODE_2021", "ra_class"]].copy()
    out["ra_assign"] = "within"

    miss = out["ra_class"].isna()
    if miss.any():
        near = gpd.sjoin_nearest(
            pts.loc[miss].to_crs(metric_crs), ra.to_crs(metric_crs), how="left"
        )
        near = near[~near.index.duplicated(keep="first")]
        out.loc[miss, "ra_class"] = near["ra_class"].values
        out.loc[miss, "ra_assign"] = "nearest"
    out["ra_class"] = out["ra_class"].astype(int)
    return out.reset_index(drop=True)


def sa2_remoteness(sa1_ra: pd.DataFrame, split_threshold: float = 0.90) -> pd.DataFrame:
    """Collapse SA1-level RA classes to one class per SA2.

    Parameters
    ----------
    sa1_ra
        One row per SA1 with ``SA2_CODE_2021``, ``ra_class`` (0-4), ``pop`` (may be NaN)
        and ``area`` (km²).
    split_threshold
        ``ra_split`` is True when the assigned class's share is below this.

    Returns
    -------
    DataFrame indexed by nothing, with columns sa2_code21, ra_code, ra_name, ra_method,
    ra_pop_share, ra_area_share, ra_n_classes, ra_split.
    """
    g = (
        sa1_ra.groupby(["SA2_CODE_2021", "ra_class"])
        .agg(pop=("pop", lambda s: s.sum(min_count=1)), area=("area", "sum"))
        .reset_index()
    )
    tot = g.groupby("SA2_CODE_2021").agg(
        pop_tot=("pop", lambda s: s.sum(min_count=1)), area_tot=("area", "sum")
    )
    g = g.join(tot, on="SA2_CODE_2021")
    g["pop_share"] = np.where(g["pop_tot"] > 0, g["pop"].fillna(0) / g["pop_tot"], np.nan)
    g["area_share"] = np.where(g["area_tot"] > 0, g["area"] / g["area_tot"], np.nan)
    g["use_pop"] = g["pop_tot"].fillna(0) > 0

    # Rank: primary share by the method in use, tie-break by area share, then the more
    # remote class (conservative for an access study).
    g["primary"] = np.where(g["use_pop"], g["pop_share"], g["area_share"])
    g = g.sort_values(
        ["SA2_CODE_2021", "primary", "area_share", "ra_class"],
        ascending=[True, False, False, False],
    )
    top = g.groupby("SA2_CODE_2021", sort=False).head(1)
    n_classes = g.groupby("SA2_CODE_2021")["ra_class"].nunique()

    out = pd.DataFrame(
        {
            "sa2_code21": top["SA2_CODE_2021"].values,
            "ra_code": top["ra_class"].astype("Int64").values,
            "ra_method": np.where(top["use_pop"], "population", "area"),
            "ra_pop_share": top["pop_share"].values,
            "ra_area_share": top["area_share"].values,
        }
    )
    out["ra_name"] = out["ra_code"].map(RA_NAMES)
    out["ra_n_classes"] = out["sa2_code21"].map(n_classes).astype("Int64")
    share = np.where(out["ra_method"] == "population", out["ra_pop_share"], out["ra_area_share"])
    out["ra_split"] = share < split_threshold
    return out[
        ["sa2_code21", "ra_code", "ra_name", "ra_method", "ra_pop_share", "ra_area_share",
         "ra_n_classes", "ra_split"]
    ]
