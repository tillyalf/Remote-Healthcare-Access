"""Loaders for local ABS files (ASGS boundaries, Remoteness, SEIFA, Census GCP, Mesh Block counts).

All loaders return SA2/SA1/MB codes as strings and do no joining; joins live in
:mod:`rha.integrate.build_master`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

import geopandas as gpd
import pandas as pd

log = logging.getLogger(__name__)

SA2_LAYER = "SA2_2021_AUST_GDA2020"
SA1_LAYER = "SA1_2021_AUST_GDA2020"
MB_LAYER = "MB_2021_AUST_GDA2020"
RA_LAYER = "RA_2021_AUST_GDA2020"

STATE_ABBR = {
    "1": "NSW", "2": "VIC", "3": "QLD", "4": "SA", "5": "WA",
    "6": "TAS", "7": "NT", "8": "ACT", "9": "OT", "Z": "OUT",
}


def load_sa2(gpkg: Path) -> gpd.GeoDataFrame:
    """SA2 2021 polygons (EPSG:7844), including the 19 non-spatial rows (null geometry)."""
    gdf = gpd.read_file(gpkg, layer=SA2_LAYER)
    log.info("SA2 layer: %d rows", len(gdf))
    return gdf


def load_sa1(gpkg: Path) -> gpd.GeoDataFrame:
    """SA1 2021 polygons with parent SA2 code and Albers area."""
    return gpd.read_file(
        gpkg, layer=SA1_LAYER, columns=["SA1_CODE_2021", "SA2_CODE_2021", "AREA_ALBERS_SQKM"]
    )


def load_mb_to_sa1(gpkg: Path) -> pd.DataFrame:
    """Mesh Block -> SA1 lookup (attributes only, no geometry)."""
    return gpd.read_file(
        gpkg, layer=MB_LAYER, columns=["MB_CODE_2021", "SA1_CODE_2021"], ignore_geometry=True
    )


def load_ra(gpkg: Path) -> gpd.GeoDataFrame:
    """Remoteness Area polygons (state x class) with an integer ``ra_class`` 0-4.

    Placeholder rows (migratory / no usual address / outside Australia) have no
    geometry and are dropped.
    """
    ra = gpd.read_file(gpkg, layer=RA_LAYER)
    ra = ra[ra.geometry.notna() & ~ra.geometry.is_empty].copy()
    ra["ra_class"] = ra["RA_CODE_2021"].str[-1].astype(int)
    if not ra["ra_class"].between(0, 4).all():
        raise ValueError("Unexpected RA class codes in RA layer")
    return ra[["RA_CODE_2021", "RA_NAME_2021", "ra_class", "geometry"]]


def load_mb_counts(xlsx: Path) -> pd.DataFrame:
    """ABS 'Mesh Block Counts, 2021': one row per MB with ``Person`` and ``Dwelling``.

    The workbook has one sheet per state/part (``Table N``), header on row 7.
    """
    sheets = pd.read_excel(xlsx, sheet_name=None, header=6, dtype={"MB_CODE_2021": str})
    frames = [
        df[["MB_CODE_2021", "MB_CATEGORY_NAME_2021", "Dwelling", "Person"]]
        for name, df in sheets.items()
        if name.startswith("Table")
    ]
    mb = pd.concat(frames, ignore_index=True)
    mb = mb[mb["MB_CODE_2021"].str.fullmatch(r"\d{11}", na=False)].copy()
    mb["Person"] = pd.to_numeric(mb["Person"]).astype("int64")
    # Dwelling is blank for the 9 non-spatial 'NOUSUALRESIDENCE' mesh blocks.
    mb["Dwelling"] = pd.to_numeric(mb["Dwelling"]).astype("Int64")
    if not mb["MB_CODE_2021"].is_unique:
        raise ValueError("Duplicate mesh block codes in MB counts")
    log.info("MB counts: %d mesh blocks, %d persons", len(mb), mb["Person"].sum())
    return mb


# ---------------------------------------------------------------------------
# SEIFA
# ---------------------------------------------------------------------------
_SEIFA_CODE_COL = "2021 Statistical Area Level 2  (SA2) 9-Digit Code"


def _seifa_table(xlsx: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx, sheet_name=sheet, header=5, dtype={_SEIFA_CODE_COL: str})
    if _SEIFA_CODE_COL not in df.columns:
        raise ValueError(f"SEIFA {sheet}: code column not found; layout changed?")
    df = df.rename(columns={_SEIFA_CODE_COL: "sa2_code21"})
    return df[df["sa2_code21"].str.fullmatch(r"\d{9}", na=False)].copy()


def load_seifa_irsd(xlsx: Path) -> pd.DataFrame:
    """IRSD (SEIFA Table 2) plus the excluded-areas flag (Table 6), one row per SA2 code.

    Columns: sa2_code21, seifa_irsd_score, seifa_irsd_decile (national),
    seifa_irsd_pctl (national), seifa_irsd_decile_state, seifa_excluded.
    """
    t2 = _seifa_table(xlsx, "Table 2")
    # Table 2 has duplicate headings: national ranks first, then state ("Decile.1").
    expected = {"Score", "Decile", "Percentile", "Decile.1"}
    if not expected <= set(t2.columns):
        raise ValueError(f"SEIFA Table 2 missing columns {expected - set(t2.columns)}")
    irsd = pd.DataFrame(
        {
            "sa2_code21": t2["sa2_code21"],
            "seifa_irsd_score": pd.to_numeric(t2["Score"]),
            "seifa_irsd_decile": pd.to_numeric(t2["Decile"]).astype("Int64"),
            "seifa_irsd_pctl": pd.to_numeric(t2["Percentile"]).astype("Int64"),
            "seifa_irsd_decile_state": pd.to_numeric(t2["Decile.1"]).astype("Int64"),
        }
    )
    t6 = _seifa_table(xlsx, "Table 6")
    excluded = t6.loc[t6["IRSD"].astype(str).str.strip() == "Y", "sa2_code21"]
    out = irsd.merge(
        pd.DataFrame({"sa2_code21": excluded, "seifa_excluded": True}), on="sa2_code21", how="outer"
    )
    out["seifa_excluded"] = out["seifa_excluded"].fillna(False).astype(bool)
    if not out["sa2_code21"].is_unique:
        raise ValueError("SEIFA: duplicate SA2 codes")
    if (out["seifa_excluded"] & out["seifa_irsd_score"].notna()).any():
        raise ValueError("SEIFA: SA2 both scored and excluded")
    log.info("SEIFA IRSD: %d scored, %d excluded", irsd.shape[0], int(out.seifa_excluded.sum()))
    return out


# ---------------------------------------------------------------------------
# Census GCP DataPack
# ---------------------------------------------------------------------------
def census_file(census_dir: Path, table: str) -> Path:
    """Path of ``2021Census_{table}_AUST_SA2.csv``; raises if not exactly one match."""
    matches = sorted(Path(census_dir).glob(f"2021Census_{table}_AUST_SA2*.csv"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected 1 Census file for {table} in {census_dir}, got {matches}"
        )
    return matches[0]


def load_census_columns(
    census_dir: Path, spec: Mapping[str, Mapping[str, str]]
) -> pd.DataFrame:
    """Read selected Census GCP columns and rename them.

    ``spec`` maps DataPack file id (e.g. ``"G13E"``) -> {source column: output column}.
    Returns one row per SA2 code with column ``sa2_code21``; raw (perturbed) counts are
    kept as published. Never sum perturbed components to rebuild a total.
    """
    out: pd.DataFrame | None = None
    for table, cols in spec.items():
        df = pd.read_csv(
            census_file(census_dir, table),
            usecols=["SA2_CODE_2021", *cols],
            dtype={"SA2_CODE_2021": str},
        ).rename(columns={"SA2_CODE_2021": "sa2_code21", **cols})
        if not df["sa2_code21"].is_unique:
            raise ValueError(f"Census {table}: duplicate SA2 codes")
        out = df if out is None else out.merge(df, on="sa2_code21", how="outer", validate="1:1")
    assert out is not None
    return out
