"""Census 2021 GCP (SA2) columns pulled into ``sa2_master``.

Table numbers and short column names were verified against
``Metadata_2021_GCP_DataPack_R1_R2.xlsx`` (2026-11-25). Values are raw published counts;
they are randomly perturbed by the ABS, so components may not sum to totals.
Compute ratios in modules from these counts and their denominators.

``role`` tags (also written to ``sa2_master_columns.csv``):

* ``count`` / ``denominator``: ordinary inputs.
* ``overlaps_irsd``: a SEIFA IRSD input; do not use in the same model as IRSD.
* ``need_context_only``: aggregate long-term health condition counts. Descriptive need
  context ONLY. **Never a target, label, or outcome**, and not to be used to validate
  access scores.
"""

from __future__ import annotations

from typing import NamedTuple


class CensusCol(NamedTuple):
    table: str        # DataPack file id
    source: str       # short column name in the CSV
    name: str         # output column in sa2_master
    role: str
    description: str


_AGE_BANDS = [
    ("Age_0_4_yr_P", "age_0_4"), ("Age_5_14_yr_P", "age_5_14"),
    ("Age_15_19_yr_P", "age_15_19"), ("Age_20_24_yr_P", "age_20_24"),
    ("Age_25_34_yr_P", "age_25_34"), ("Age_35_44_yr_P", "age_35_44"),
    ("Age_45_54_yr_P", "age_45_54"), ("Age_55_64_yr_P", "age_55_64"),
    ("Age_65_74_yr_P", "age_65_74"), ("Age_75_84_yr_P", "age_75_84"),
    ("Age_85ov_P", "age_85_over"),
]

CENSUS_COLUMNS: list[CensusCol] = [
    # G01 Selected Person Characteristics by Sex
    CensusCol("G01", "Tot_P_P", "pop_total", "denominator", "Total persons (usual residence)"),
    CensusCol("G01", "Indigenous_P_Tot_P", "pop_indigenous", "count",
              "Aboriginal and/or Torres Strait Islander persons"),
    *[CensusCol("G01", s, n, "count", f"Persons aged {n[4:].replace('_', '-')}")
      for s, n in _AGE_BANDS],
    CensusCol("G01", "Count_psns_occ_priv_dwgs_P", "pop_occ_priv_dwellings", "denominator",
              "Persons in occupied private dwellings"),
    # G07 Indigenous Status by Age by Sex
    CensusCol("G07", "Tot_Non_Indigenous_P", "pop_non_indigenous", "count",
              "Non-Indigenous persons"),
    CensusCol("G07", "Tot_Indig_status_ns_P", "pop_indig_status_ns", "count",
              "Persons with Indigenous status not stated"),
    # G02 Selected Medians and Averages
    CensusCol("G02", "Median_age_persons", "median_age", "count", "Median age of persons"),
    CensusCol("G02", "Median_tot_hhd_inc_weekly", "median_hhd_income_weekly", "overlaps_irsd",
              "Median total household income ($/week). IRSD input: not alongside IRSD"),
    # G13 Language Used at Home by Proficiency in Spoken English (totals in G13E)
    CensusCol("G13E", "P_Tot_SEO", "lang_english_only", "count", "Speaks English only at home"),
    CensusCol("G13E", "P_Tot_UOLSE_VWorW", "lang_other_eng_well", "count",
              "Uses other language at home; speaks English very well or well"),
    CensusCol("G13E", "P_Tot_UOLSE_NWorNAA", "lang_other_eng_not_well", "overlaps_irsd",
              "Uses other language; speaks English not well or not at all. IRSD input"),
    CensusCol("G13E", "P_Tot_UOLSE_Tot", "lang_other_total", "count",
              "Uses other language at home (all English proficiency levels incl. not stated)"),
    CensusCol("G13E", "P_Tot_NS", "lang_not_stated", "count", "Language/proficiency not stated"),
    CensusCol("G13E", "P_Tot_Tot", "lang_total", "denominator", "Total persons (G13)"),
    # G18 Core Activity Need for Assistance by Age by Sex
    CensusCol("G18", "P_Tot_Need_for_assistance", "assist_need", "overlaps_irsd",
              "Persons with core activity need for assistance. IRSD input"),
    CensusCol("G18", "P_Tot_No_need_for_assistance", "assist_no_need", "count",
              "Persons without need for assistance"),
    CensusCol("G18", "P_Tot_Need_for_assistance_ns", "assist_not_stated", "count",
              "Need for assistance not stated"),
    CensusCol("G18", "P_Tot_Tot", "assist_total", "denominator", "Total persons (G18)"),
    # G20 Count of Selected Long-Term Health Conditions: NEED CONTEXT ONLY, NEVER A TARGET
    CensusCol("G20A", "P_0_cond_Tot", "needctx_lthc_0", "need_context_only",
              "Persons with none of the selected long-term health conditions"),
    CensusCol("G20A", "P_1_cond_Tot", "needctx_lthc_1", "need_context_only",
              "Persons with one selected long-term health condition"),
    CensusCol("G20A", "P_2_cond_Tot", "needctx_lthc_2", "need_context_only",
              "Persons with two selected long-term health conditions"),
    CensusCol("G20A", "P_3_or_mo_cond_Tot", "needctx_lthc_3plus", "need_context_only",
              "Persons with three or more selected long-term health conditions"),
    CensusCol("G20A", "P_1m_cond_Tot_Tot", "needctx_lthc_1plus", "need_context_only",
              "Persons with one or more selected long-term health conditions"),
    CensusCol("G20A", "P_cond_NS_Tot", "needctx_lthc_not_stated", "need_context_only",
              "Long-term health condition count not stated"),
    CensusCol("G20B", "P_Tot_Tot", "needctx_lthc_total", "denominator", "Total persons (G20)"),
    # G34 Number of Motor Vehicles by Dwellings (occupied private dwellings)
    CensusCol("G34", "Num_MVs_per_dweling_0_MVs", "dwell_no_vehicle", "overlaps_irsd",
              "Occupied private dwellings with no motor vehicle. IRSD input"),
    CensusCol("G34", "Num_MVs_per_dweling_Tot", "dwell_vehicles_stated", "denominator",
              "Occupied private dwellings with number of vehicles stated"),
    CensusCol("G34", "Num_MVs_NS", "dwell_vehicles_not_stated", "count",
              "Occupied private dwellings, number of vehicles not stated"),
    CensusCol("G34", "Total_dwelings", "dwell_occ_private", "denominator",
              "Total occupied private dwellings"),
]


def census_spec() -> dict[str, dict[str, str]]:
    """``{table: {source: name}}`` for :func:`rha.ingest.abs_files.load_census_columns`."""
    spec: dict[str, dict[str, str]] = {}
    for c in CENSUS_COLUMNS:
        spec.setdefault(c.table, {})[c.source] = c.name
    return spec
