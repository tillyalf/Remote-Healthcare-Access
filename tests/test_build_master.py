"""Join-completeness and integrity checks for sa2_master.

Synthetic tests always run. ``test_real_master_*`` run only when the locally built
``data/processed/sa2_master.parquet`` exists (it is never committed).
"""

import geopandas as gpd
import pandas as pd
import pytest

from rha.config import data_path
from rha.ingest.abs_files import load_census_columns
from rha.integrate.build_master import validate_master
from rha.integrate.census_spec import CENSUS_COLUMNS, census_spec

CODES = {"101021007", "101021008", "199999499"}


def _good_master():
    return pd.DataFrame(
        {
            "sa2_code21": pd.Series(["101021007", "101021008", "199999499"], dtype="str"),
            "pop_total": [100, 0, 50],
            "is_nonspatial": [False, False, True],
            "ra_code": pd.array([0, 1, pd.NA], dtype="Int64"),
            "seifa_irsd_score": [1000.0, None, None],
            "seifa_excluded": [False, True, True],
            "accho_count": pd.array([1, 0, pd.NA], dtype="Int64"),
        }
    )


def _validate(m, **kw):
    args = dict(boundary_codes=CODES, census_codes=CODES, seifa_codes=CODES, accho_assigned=1)
    validate_master(m, **{**args, **kw})


def test_validate_passes_on_good_master():
    _validate(_good_master())


@pytest.mark.parametrize(
    "mutate, msg",
    [
        (lambda m: pd.concat([m, m.iloc[[0]]], ignore_index=True), "duplicate"),
        (lambda m: m.iloc[:2], "differs from SA2 boundary"),
        (lambda m: m.assign(ra_code=pd.array([pd.NA, 1, pd.NA], dtype="Int64")), "lack ra_code"),
        (lambda m: m.assign(accho_count=pd.array([5, 0, pd.NA], dtype="Int64")), "accho_count"),
        (lambda m: m.assign(latitude=0.0), "forbidden"),
        (lambda m: m.assign(seifa_excluded=[True, True, True]), "SEIFA"),
    ],
)
def test_validate_catches_problems(mutate, msg):
    with pytest.raises(ValueError, match=msg):
        _validate(mutate(_good_master()))


def test_census_loader_keeps_codes_as_strings(tmp_path):
    pd.DataFrame({"SA2_CODE_2021": ["101021007", "801011001"], "Tot_P_P": [5, 6],
                  "Other": [1, 2]}).to_csv(tmp_path / "2021Census_G01_AUST_SA2.csv", index=False)
    pd.DataFrame({"SA2_CODE_2021": ["801011001", "101021007"], "P_Tot_Tot": [7, 8]}).to_csv(
        tmp_path / "2021Census_G18_AUST_SA2.csv", index=False)
    out = load_census_columns(
        tmp_path, {"G01": {"Tot_P_P": "pop_total"}, "G18": {"P_Tot_Tot": "assist_total"}}
    ).set_index("sa2_code21")
    assert pd.api.types.is_string_dtype(out.index)
    assert list(out.columns) == ["pop_total", "assist_total"]
    assert out.loc["101021007"].tolist() == [5, 8]


def test_census_spec_is_consistent():
    names = [c.name for c in CENSUS_COLUMNS]
    assert len(names) == len(set(names))
    assert sum(len(v) for v in census_spec().values()) == len(CENSUS_COLUMNS)
    # Long-term health conditions are need context only, never a target.
    lthc = [c for c in CENSUS_COLUMNS if c.table.startswith("G20") and c.role != "denominator"]
    assert lthc and all(c.role == "need_context_only" for c in lthc)
    assert all(c.name.startswith("needctx_") for c in lthc)


# ---------------------------------------------------------------------------
# Real-data completeness (local only)
# ---------------------------------------------------------------------------
MASTER = data_path("sa2_master")
needs_master = pytest.mark.skipif(not MASTER.exists(), reason="sa2_master not built locally")


@needs_master
def test_real_master_every_sa2_present_once():
    m = gpd.read_parquet(MASTER)
    sa2 = gpd.read_file(data_path("asgs_main"), layer="SA2_2021_AUST_GDA2020",
                        columns=["SA2_CODE_2021"], ignore_geometry=True)
    assert m["sa2_code21"].is_unique
    assert set(m["sa2_code21"]) == set(sa2["SA2_CODE_2021"])
    assert m["sa2_code21"].str.len().eq(9).all()
    assert m.crs.to_epsg() == 7844


@needs_master
def test_real_master_flags_and_coverage():
    m = gpd.read_parquet(MASTER)
    a = m[m["in_analysis"]]
    assert a["pop_total"].gt(0).all()
    assert a["ra_code"].notna().all()
    pop_rule = a["ra_method"] == "population"
    assert a.loc[pop_rule, "ra_pop_share"].between(0, 1).all()
    # Area fallback only where MB-count pop is 0: a handful of tiny SA2s whose
    # (independently perturbed) Census pop_total is > 0.
    assert a.loc[~pop_rule, "ra_pop_share"].isna().all()
    assert a.loc[~pop_rule, "pop_total"].lt(20).all()
    assert (a["seifa_irsd_score"].notna() | a["seifa_excluded"]).all()
    assert m.loc[m["is_nonspatial"], "accho_count"].isna().all()
