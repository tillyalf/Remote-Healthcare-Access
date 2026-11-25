"""Build ``sa2_master``: one row per 2021 SA2 (GeoParquet, EPSG:7844).

Joins, all on the 9-character string ``sa2_code21``:

* ASGS 2021 SA2 boundaries (base; all 2,473 rows kept, incl. non-spatial codes)
* Census 2021 GCP columns (see :mod:`rha.integrate.census_spec`)
* SEIFA 2021 IRSD (+ excluded-area flag)
* Remoteness Area class (population-majority rule, see :mod:`rha.prep.remoteness`)
* ACCHO counts per SA2 (counts only; no ACCHO detail leaves this module)

Run::

    python -m rha.integrate.build_master
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from rha.config import SETTINGS_PATH, data_path, load_settings
from rha.ingest import abs_files
from rha.ingest.accho import load_accho_points
from rha.integrate.census_spec import CENSUS_COLUMNS, census_spec
from rha.prep.remoteness import assign_sa1_ra, sa2_remoteness

log = logging.getLogger("rha.integrate.build_master")

# Columns that must never appear in sa2_master (ACCHO detail / PII guard).
FORBIDDEN_COLUMN_FRAGMENTS = ("address", "phone", "latitude", "longitude", "suburb", "postcode")

BASE_COLUMN_DOCS: dict[str, tuple[str, str]] = {
    "sa2_code21": ("identifier", "SA2 2021 code (9-char string)"),
    "sa2_name21": ("identifier", "SA2 2021 name"),
    "state": ("identifier", "State/territory abbreviation"),
    "state_code": ("identifier", "ASGS state code"),
    "sa3_code21": ("identifier", "Parent SA3 code"),
    "sa3_name21": ("identifier", "Parent SA3 name"),
    "sa4_code21": ("identifier", "Parent SA4 code"),
    "gccsa_code21": ("identifier", "Parent GCCSA code"),
    "area_albers_sqkm": ("count", "SA2 area, km² (ABS, Albers)"),
    "ra_code": ("stratifier", "Remoteness class 0-4 (pop-majority; stratifier, not feature)"),
    "ra_name": ("stratifier", "Remoteness class name"),
    "ra_method": ("qa", "'population' or 'area' (area fallback where SA2 pop is 0/missing)"),
    "ra_pop_share": ("qa", "Share of SA2 MB-count population in assigned RA class"),
    "ra_area_share": ("qa", "Share of SA2 area in assigned RA class"),
    "ra_n_classes": ("qa", "Number of RA classes the SA2's SA1s fall in"),
    "ra_split": ("flag", "Assigned-class share < integrate.ra_split_threshold"),
    "seifa_irsd_score": ("socioeconomic", "SEIFA 2021 IRSD score (low = disadvantaged)"),
    "seifa_irsd_decile": ("socioeconomic", "IRSD national decile (1 = most disadvantaged)"),
    "seifa_irsd_pctl": ("socioeconomic", "IRSD national percentile"),
    "seifa_irsd_decile_state": ("socioeconomic", "IRSD within-state decile"),
    "seifa_excluded": ("flag", "SA2 excluded from SEIFA IRSD by ABS"),
    "accho_count": ("accho", "ACCHO sites within the SA2 (sensitive aggregate; own module)"),
    "accho_count_manual_geocode": ("qa", "Of accho_count, sites geocoded manually"),
    "is_nonspatial": ("flag", "No geometry (migratory/offshore, no usual address, outside AU)"),
    "is_zero_pop": ("flag", "Census pop_total is 0 or missing"),
    "in_analysis": ("flag", "Spatial and pop_total > 0"),
    "geometry": ("geometry", "SA2 polygon, EPSG:7844"),
}


# ---------------------------------------------------------------------------
# Steps (pure where possible)
# ---------------------------------------------------------------------------
def make_base(sa2: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Rename/select SA2 boundary columns and add ``is_nonspatial``."""
    base = gpd.GeoDataFrame(
        {
            "sa2_code21": sa2["SA2_CODE_2021"].astype(str),
            "sa2_name21": sa2["SA2_NAME_2021"],
            "state": sa2["STATE_CODE_2021"].astype(str).map(abs_files.STATE_ABBR),
            "state_code": sa2["STATE_CODE_2021"].astype(str),
            "sa3_code21": sa2["SA3_CODE_2021"],
            "sa3_name21": sa2["SA3_NAME_2021"],
            "sa4_code21": sa2["SA4_CODE_2021"],
            "gccsa_code21": sa2["GCCSA_CODE_2021"],
            "area_albers_sqkm": sa2["AREA_ALBERS_SQKM"],
        },
        geometry=sa2.geometry.values,
        crs=sa2.crs,
    )
    base["is_nonspatial"] = base.geometry.isna() | base.geometry.is_empty
    return base


def sa1_population(mb_counts: pd.DataFrame, mb_to_sa1: pd.DataFrame) -> pd.DataFrame:
    """Sum Mesh Block Count persons to SA1. Returns ``SA1_CODE_2021, pop``."""
    m = mb_to_sa1.merge(mb_counts[["MB_CODE_2021", "Person"]], on="MB_CODE_2021", how="left",
                        validate="1:1")
    n_missing = int(m["Person"].isna().sum())
    if n_missing:
        log.warning("%d mesh blocks in ASGS have no MB count", n_missing)
    return (
        m.groupby("SA1_CODE_2021")["Person"]
        .sum(min_count=1)
        .rename("pop")
        .reset_index()
    )


def build_remoteness(
    sa1: gpd.GeoDataFrame,
    ra: gpd.GeoDataFrame,
    sa1_pop: pd.DataFrame,
    split_threshold: float,
    metric_crs: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """SA1 -> RA by point-in-polygon, then SA2 class by population majority."""
    sa1_ra = assign_sa1_ra(sa1, ra, metric_crs=metric_crs)
    df = (
        sa1_ra.merge(sa1[["SA1_CODE_2021", "SA2_CODE_2021", "AREA_ALBERS_SQKM"]],
                     on="SA1_CODE_2021", how="left", validate="1:1")
        .merge(sa1_pop, on="SA1_CODE_2021", how="left", validate="1:1")
        .rename(columns={"AREA_ALBERS_SQKM": "area"})
    )
    out = sa2_remoteness(df, split_threshold=split_threshold)
    qa = {
        "sa1_assigned_within": int((sa1_ra["ra_assign"] == "within").sum()),
        "sa1_assigned_nearest": int((sa1_ra["ra_assign"] == "nearest").sum()),
        "sa2_ra_method_population": int((out["ra_method"] == "population").sum()),
        "sa2_ra_method_area": int((out["ra_method"] == "area").sum()),
        "sa2_ra_split": int(out["ra_split"].sum()),
        "sa2_ra_multi_class": int((out["ra_n_classes"] > 1).sum()),
        "ra_split_threshold": split_threshold,
    }
    return out, qa


def count_points_per_sa2(
    points: gpd.GeoDataFrame,
    sa2: gpd.GeoDataFrame,
    max_nearest_m: float,
    metric_crs: str,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Assign points to SA2 polygons (within; nearest fallback <= ``max_nearest_m``).

    Returns per-SA2 ``n`` and ``n_manual`` (points with geocode_method == 'manual')
    for SA2s with at least one point, and aggregate QA counts. No point-level data is
    returned.
    """
    polys = sa2.loc[~(sa2.geometry.isna() | sa2.geometry.is_empty), ["sa2_code21", "geometry"]]
    pts = points.to_crs(polys.crs)
    j = gpd.sjoin(pts, polys, how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    code = j["sa2_code21"].copy()
    n_within = int(code.notna().sum())

    miss = code.isna()
    n_nearest = 0
    if miss.any():
        near = gpd.sjoin_nearest(
            pts.loc[miss].to_crs(metric_crs),
            polys.to_crs(metric_crs),
            how="left",
            max_distance=max_nearest_m,
        )
        near = near[~near.index.duplicated(keep="first")]
        code.loc[miss] = near["sa2_code21"].values
        n_nearest = int(code.loc[miss].notna().sum())

    assigned = pd.DataFrame(
        {"sa2_code21": code, "manual": pts["geocode_method"].eq("manual").values}
    ).dropna(subset=["sa2_code21"])
    counts = (
        assigned.groupby("sa2_code21")
        .agg(n=("manual", "size"), n_manual=("manual", "sum"))
        .reset_index()
    )
    qa = {
        "points": len(pts),
        "assigned_within": n_within,
        "assigned_nearest": n_nearest,
        "unassigned": int(code.isna().sum()),
        "sa2_with_points": len(counts),
    }
    return counts, qa


def add_flags(master: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add ``is_zero_pop`` and ``in_analysis``; flags only, nothing is dropped."""
    master["is_zero_pop"] = master["pop_total"].fillna(0).eq(0)
    master["in_analysis"] = ~master["is_nonspatial"] & ~master["is_zero_pop"]
    return master


def validate_master(
    master: pd.DataFrame,
    *,
    boundary_codes: set[str],
    census_codes: set[str],
    seifa_codes: set[str],
    accho_assigned: int | None = None,
) -> None:
    """Raise ``ValueError`` listing every failed integrity check."""
    errs: list[str] = []
    codes = master["sa2_code21"]
    if not pd.api.types.is_string_dtype(codes):
        errs.append(f"sa2_code21 dtype is {codes.dtype}, expected string")
    if not codes.is_unique:
        errs.append(f"{int(codes.duplicated().sum())} duplicate sa2_code21")
    if set(codes) != boundary_codes:
        errs.append("sa2_code21 set differs from SA2 boundary layer")
    if not codes.str.len().eq(9).all():
        errs.append("sa2_code21 values not all 9 characters")
    if missing := census_codes - set(codes):
        errs.append(f"{len(missing)} Census SA2 codes missing from master")
    if missing := seifa_codes - set(codes):
        errs.append(f"{len(missing)} SEIFA SA2 codes missing from master")
    if master.loc[codes.isin(census_codes), "pop_total"].isna().any():
        errs.append("Census join left pop_total null for some Census codes")
    spatial = ~master["is_nonspatial"]
    if master.loc[spatial, "ra_code"].isna().any():
        errs.append(f"{int(master.loc[spatial, 'ra_code'].isna().sum())} spatial SA2s lack ra_code")
    seifa_ok = master["seifa_irsd_score"].notna() ^ master["seifa_excluded"]
    if not seifa_ok[codes.isin(seifa_codes)].all():
        errs.append("SEIFA: rows neither scored nor excluded (or both)")
    if accho_assigned is not None and int(master["accho_count"].sum()) != accho_assigned:
        errs.append("accho_count total != number of assigned ACCHO points")
    bad = [c for c in master.columns if any(f in c.lower() for f in FORBIDDEN_COLUMN_FRAGMENTS)]
    if bad:
        errs.append(f"forbidden columns present: {bad}")
    if errs:
        raise ValueError("sa2_master validation failed:\n  - " + "\n  - ".join(errs))


def column_dictionary(master: pd.DataFrame) -> pd.DataFrame:
    """Name, dtype, source, role and description for every master column."""
    census = {c.name: (f"Census 2021 GCP {c.table}:{c.source}", c.role, c.description)
              for c in CENSUS_COLUMNS}
    rows = []
    for col in master.columns:
        if col in census:
            src, role, desc = census[col]
        else:
            role, desc = BASE_COLUMN_DOCS.get(col, ("", ""))
            src = "derived"
        rows.append({"column": col, "dtype": str(master[col].dtype), "source": src,
                     "role": role, "description": desc})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def build_master(settings: dict[str, Any]) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Run every join and integrity check; return (master, qa)."""
    crs_metric = settings["crs"]["metric"]
    cfg = settings["integrate"]
    qa: dict[str, Any] = {}

    sa2 = abs_files.load_sa2(data_path("asgs_main", settings))
    base = make_base(sa2)
    boundary_codes = set(base["sa2_code21"])
    qa["sa2_rows"] = len(base)
    qa["sa2_nonspatial"] = int(base["is_nonspatial"].sum())

    # Census
    census = abs_files.load_census_columns(data_path("census_dir", settings), census_spec())
    g07_check = abs_files.load_census_columns(
        data_path("census_dir", settings), {"G07": {"Tot_Indigenous_P": "_g07_indig"}}
    ).merge(census[["sa2_code21", "pop_indigenous"]], on="sa2_code21")
    if not g07_check["_g07_indig"].equals(g07_check["pop_indigenous"]):
        raise ValueError("G01 and G07 Indigenous totals disagree")
    census_codes = set(census["sa2_code21"])
    qa["census_rows"] = len(census)
    qa["census_codes_not_in_boundaries"] = len(census_codes - boundary_codes)

    # SEIFA
    seifa = abs_files.load_seifa_irsd(data_path("seifa", settings))
    seifa_codes = set(seifa["sa2_code21"])
    qa["seifa_scored"] = int(seifa["seifa_irsd_score"].notna().sum())
    qa["seifa_excluded"] = int(seifa["seifa_excluded"].sum())

    # Remoteness
    gpkg = data_path("asgs_main", settings)
    sa1 = abs_files.load_sa1(gpkg)
    sa1_pop = sa1_population(
        abs_files.load_mb_counts(data_path("mb_counts", settings)),
        abs_files.load_mb_to_sa1(gpkg),
    )
    remote, qa["remoteness"] = build_remoteness(
        sa1, abs_files.load_ra(data_path("asgs_ra", settings)), sa1_pop,
        split_threshold=cfg["ra_split_threshold"], metric_crs=crs_metric,
    )

    # ACCHO (sensitive: only aggregate counts leave this block)
    points = load_accho_points(data_path("accho", settings))
    counts, acc_qa = count_points_per_sa2(
        points, base, max_nearest_m=cfg["accho_nearest_max_m"], metric_crs=crs_metric
    )
    qa["accho"] = {**points.attrs.get("qa", {}), **acc_qa}
    del points

    master = (
        base.merge(census, on="sa2_code21", how="left", validate="1:1")
        .merge(seifa, on="sa2_code21", how="left", validate="1:1")
        .merge(remote, on="sa2_code21", how="left", validate="1:1")
        .merge(
            counts.rename(columns={"n": "accho_count", "n_manual": "accho_count_manual_geocode"}),
            on="sa2_code21", how="left", validate="1:1",
        )
    )
    master["seifa_excluded"] = master["seifa_excluded"].fillna(False).astype(bool)
    master["ra_split"] = master["ra_split"].astype("boolean")
    for c in ("accho_count", "accho_count_manual_geocode"):
        master[c] = master[c].fillna(0).astype("Int64")
        master.loc[master["is_nonspatial"], c] = pd.NA
    master = add_flags(master)

    validate_master(
        master,
        boundary_codes=boundary_codes,
        census_codes=census_codes,
        seifa_codes=seifa_codes,
        accho_assigned=acc_qa["assigned_within"] + acc_qa["assigned_nearest"],
    )
    qa["in_analysis"] = int(master["in_analysis"].sum())
    qa["zero_pop"] = int(master["is_zero_pop"].sum())
    return master, qa


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--settings", type=Path, default=SETTINGS_PATH)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    settings = load_settings(args.settings)
    master, qa = build_master(settings)

    out = data_path("sa2_master", settings)
    out.parent.mkdir(parents=True, exist_ok=True)
    master.to_parquet(out, index=False)
    column_dictionary(master).to_csv(data_path("sa2_master_columns", settings), index=False)
    with open(data_path("sa2_master_qa", settings), "w", encoding="utf-8") as f:
        json.dump(qa, f, indent=2)
    log.info("Wrote %s (%d rows, %d columns)", out, len(master), master.shape[1])
    log.info("QA: %s", json.dumps(qa))


if __name__ == "__main__":
    main()
