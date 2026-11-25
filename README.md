# Remote Healthcare Access !!IN PROGRESS!!

This project investigates how machine learning and geospatial analysis can be utilised to identify communities that face greater barriers in accessing healthcare. 

This investigation will be executed at a community level, with a clear focus on not predicting or seeking out health outcomes or PII. Rather using this project to expose current inequalities present in geographic areas. 

Healthcare access, particularly in Aboriginal communities, is significantly more complex then physical distance alone. This project therefore places a core focus on identifying patterns, gaps, and contributing factors, instead of mathematically determining healthcare access. This is especially important in the consideration of National Aboriginal Community Controlled Health Organisation (NACCHO). NACCHO represents 148 Aboriginal Community Control Health Organisaitons (ACCHOs) which provide culturally informed, community-led healthcare. Considering this, these organisations will be highlighted as an entirely separate factor instead of being generalised with Geographic accessibility measurements.

### Two Main Sections to This Project:
- Part A: Descriptive and Geospatial: This will utilise mapping and data analysis to investigate healthcare accessibility across communities based on key contributing factors such as geographical distance, socioeconomic disadvantage, and the presence of ACCHOs.
- Part B: Machine Learning and Research: This will develop a machine learning model to classify community-level accessibility, and then discover which factors are more strongly associated with communities experiencing greater barriers with healthcare access.

## Getting started

Requires Python 3.11+. Raw data is not included (see [data/README.md](data/README.md)); paths are set in [config/settings.yaml](config/settings.yaml).

```bash
python -m venv venv
venv/Scripts/activate          # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"

python -m rha.integrate.build_master   # builds data/processed/sa2_master.parquet
pytest                                 # synthetic tests + local completeness checks
```

## Pipeline status

| Stage | Status |
|---|---|
| **Milestone 1: ingest + integrate** | Done: `sa2_master` (one row per 2021 SA2) joins SA2 boundaries, Census 2021, SEIFA IRSD, Remoteness and ACCHO counts per SA2 |
| Milestone 2: first module + clickable map | Next |

`sa2_master` notes:
- **Remoteness** is assigned to each SA2 as the class covering most of its population (from SA1s weighted by Mesh Block counts), with an area fallback for zero-population SA2s. `ra_pop_share` and an `ra_split` flag (< 90%) are kept. Remoteness is used to group and compare areas, not as a model feature.
- **Census** values are raw published counts. ABS adds small random adjustments, so totals are used as published. A column dictionary with each column's role is written to `data/processed/sa2_master_columns.csv`.
- **Long-term health conditions** are included only as aggregate *need context*. They are never a target or outcome.
- **SEIFA IRSD** inputs (e.g. income, no vehicle) are tagged `overlaps_irsd` so they are not modelled alongside IRSD.
- Non-spatial and zero-population SA2s are kept and flagged (`is_nonspatial`, `is_zero_pop`, `in_analysis`), never silently dropped.

