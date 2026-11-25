# Remote Healthcare Access — Project Brief for Claude Code

## What this project is
A geospatial + machine learning investigation into **which Australian communities face greater barriers to accessing healthcare**, analysed at the **SA2 (Statistical Area Level 2, ASGS 2021)** level.

The end product is an **interactive map**: a user clicks a location → the app identifies the SA2 → returns a profile showing scores per access factor ("module"), how the area compares to similar areas, and the main contributing factors.

### Framing (important — read before writing any analysis code)
- The project **exposes patterns, gaps and contributing factors**. It does **not** compute a single "true" access score and does **not** predict health outcomes.
- **No health outcome data** (hospitalisations, mortality, disease prevalence) is used as a target or feature.
- **No PII.** Community-level aggregates only.
- **ACCHOs (Aboriginal Community Controlled Health Organisations)** are treated as their **own factor/module**, never merged into generic "health facility" counts. Proximity to an ACCHO is not equated with adequate access.
- Follow Indigenous Data Sovereignty principles (CARE, Maiam nayri Wingara). **Never publish, export, commit, or print the raw ACCHO location list** (see Data handling).

---

## Data sources

| Dataset | Source | Vintage | Status | Notes |
|---|---|---|---|---|
| NACCHO / ACCHO locations | Manually compiled from naccho.org.au/locations (18.08.26) and HealthInfoNet map (19.08.26) | 2026 | Have, geocoded (some manual) | Geocoded file (`data/processed/NACCHO_locations_geocoded.xlsx`) columns: name, state, address, suburb_town, postcode, phone, source, type, notes, `latitude`, `longitude`, geocode_method. Pipeline reads only state/latitude/longitude/geocode_method and drops rows with duplicate coordinates. **Sensitive — never commit.** |
| SA2 boundaries | ABS ASGS Ed. 3 Main Structure GeoPackage (`ASGS_2021_Main_Structure_GDA2020.gpkg`, layer `SA2_2021_AUST_GDA2020`; also SA1/MB layers) | 2021 | Have | Source key: `SA2_CODE_2021` (9-char string) → `sa2_code21` in sa2_master. 2,473 rows incl. 19 non-spatial |
| Remoteness Areas | ABS ASGS Ed. 3 (`ASGS_Ed3_2021_RA_GDA2020.gpkg`, state × class polygons, no SA2 key) | 2021 | Have | Use as **stratifier**, not a model feature. SA2 class = majority-**population** class of its SA1s (MB counts); area-majority fallback where pop is 0. `ra_pop_share`/`ra_split` stored |
| Mesh Block Counts | ABS Census 2021 Mesh Block Counts (persons, dwellings) | 2021 | Have | SA1 population weights (RA assignment, later pop-weighted centroids) |
| SEIFA | ABS SEIFA 2021 | 2021 | Have | Use IRSD. Do not combine with its raw Census components in the same model (double-counting) |
| Census DataPacks | ABS 2021 Census GCP, SA2 level (`data/raw/census_gcp_2021_sa2/`, extracted from the official zip with Metadata) | 2021 | Have | Perturbed counts: use published totals, never sum components. Verify table numbers against `Metadata_2021_GCP_DataPack_R1_R2.xlsx` (the old `data/raw/census_data/` copy is mislabelled by one table). No internet question in 2021. Long-term health condition counts (G20) are **need context only, never a target** |
| Health facilities (GP, hospital, pharmacy) | Geoscience Australia `National_HealthDirect_Health_Facilities` ArcGIS REST service; NHSD via AURIN (academic licence) as fallback | latest | To add | Also cross-check ACCHO list against NHSD |
| Road network | OpenStreetMap (Geofabrik Australia extract) | latest | To add | For travel-time routing via local OSRM/Valhalla |
| Public transport | State GTFS feeds | latest | Later | Mainly relevant outside remote areas |
| ABS Indigenous Structure (ILOC/IARE/IREG) | ABS ASGS Ed. 3 | 2021 | Optional | Secondary geography for ACCHO module |
| Modified Monash Model | Dept of Health | 2019/latest | Optional | Health-specific remoteness, alongside ABS RA |

**Vintage rule:** everything joins on **2021 SA2s**. Do not mix boundary editions. 2026 Census/ASGS = a future separate version.

---

## Suggested architecture

### Pipeline
```
ingest → prep → integrate → features (modules) → analysis → ml → validate → outputs (app)
```

### Repository layout
```
remote-healthcare-access/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .gitignore                 # must ignore data/ and any *naccho* / *accho* files
├── config/
│   ├── sources.yaml           # every source: URL, access method, licence, retrieved date
│   └── settings.yaml          # CRS, paths, routing endpoint, thresholds
├── data/                      # NEVER committed
│   ├── raw/                   # untouched downloads + API snapshots (dated folders)
│   ├── interim/               # cleaned, standardised
│   └── processed/             # sa2_master.parquet, module outputs
├── src/rha/
│   ├── ingest/
│   │   ├── base.py            # Source interface: fetch() -> raw path, logs date + hash
│   │   ├── abs_files.py       # local ABS zips/shapefiles
│   │   ├── arcgis.py          # generic ArcGIS REST FeatureServer client (paging, caching)
│   │   ├── abs_data_api.py    # ABS SDMX Data API (beta) client
│   │   └── accho.py           # loads private ACCHO file from local path only
│   ├── prep/                  # cleaning, CRS standardisation, code normalisation
│   ├── integrate/
│   │   └── build_master.py    # one row per SA2 → sa2_master (GeoParquet)
│   ├── modules/               # one file per access factor (see interface below)
│   │   ├── base.py
│   │   ├── geographic.py
│   │   ├── supply.py
│   │   ├── accho.py
│   │   ├── socioeconomic.py
│   │   ├── need.py
│   │   ├── mobility.py
│   │   └── digital.py
│   ├── routing/
│   │   └── travel_time.py     # OSRM/Valhalla table queries, cached
│   ├── analysis/
│   │   ├── spatial_stats.py   # Moran's I, LISA hotspots (PySAL)
│   │   └── descriptive.py
│   ├── ml/
│   │   ├── typology.py        # clustering of SA2s into access typologies
│   │   ├── gap_model.py       # expected-vs-actual supply residuals
│   │   └── impute.py          # spatial imputation with uncertainty
│   ├── validate/              # sensitivity analysis, spatial CV, sanity checks
│   └── app/
│       ├── api.py             # FastAPI: GET /sa2?lat=&lon=  → profile JSON
│       └── profile.py         # assembles module outputs into a profile
├── frontend/                  # map UI (MapLibre/Leaflet or Streamlit+Folium for v1)
├── notebooks/                 # exploration only; logic lives in src/
└── tests/
```

### Core data contract: `sa2_master`
GeoParquet, EPSG:7844 (GDA2020) for storage; project to EPSG:3577 (Australian Albers) for any distance/area calculation. One row per SA2. Key columns:
`sa2_code21` (str, 9 chars), `sa2_name21`, `state`, `ra_code`, `ra_name`, `pop_total`, `pop_indigenous`, `seifa_irsd_score`, `seifa_irsd_decile`, `geometry`, plus Census-derived columns. Exclude non-spatial/migratory/zero-population SA2s from analysis, but keep a flag column rather than silently dropping. Non-spatial codes are `x97979799` (Migratory – Offshore – Shipping), `x99999499` (No usual address) per state, and `ZZZZZZZZZ` (Outside Australia); flags: `is_nonspatial`, `is_zero_pop`, `in_analysis`. Column roles (incl. `overlaps_irsd`, `need_context_only`) are listed in `data/processed/sa2_master_columns.csv`.

### Module interface
Every module is independent and returns the same shape, so new modules plug in without touching the rest:

```python
class AccessModule(ABC):
    name: str
    inputs: list[str]                  # required sa2_master columns / external layers

    @abstractmethod
    def compute(self, master: gpd.GeoDataFrame) -> pd.DataFrame:
        """Return one row per sa2_code21 with:
           {name}_score       float, oriented so higher = greater barrier
           {name}_pctl_ra     percentile within same Remoteness Area
           {name}_evidence    dict of the raw values behind the score
           {name}_quality     'ok' | 'imputed' | 'low_confidence'
        """
```

| Module | Measures | Method |
|---|---|---|
| geographic | Travel time to nearest GP / hospital / ED | Road-network routing from population-weighted SA2 centroid (use SA1/mesh block pop weights) |
| supply | Services per capita within reach | Enhanced two-step floating catchment area (E2SFCA) |
| accho | Travel time to nearest ACCHO, count in reach, Indigenous pop share | Routing + counts; reported separately, never merged into supply |
| socioeconomic | Disadvantage | SEIFA IRSD |
| need | Age structure, long-term conditions (aggregate Census) | Standardised indicators |
| mobility | No-vehicle households, PT availability | Census + GTFS |
| digital | Telehealth viability | Best-available proxies; flag as low confidence |

### ML layer — what it is (and isn't) for
There is **no ground-truth "access" label**. Do not build a supervised model that predicts an access score or a health outcome.
- **Typologies:** cluster SA2s on module scores (scale → optional PCA/UMAP → k-means/GMM/HDBSCAN). Name clusters by their profile.
- **Gap detection:** model expected service supply from population/need; large negative residuals = potential gaps.
- **Spatial patterns:** LISA hotspots on module scores.
- **Imputation:** fill missing/suppressed values with spatially-aware models; always output uncertainty and set `_quality = 'imputed'`.
- **Validation:** spatial (blocked) cross-validation, never random splits; sensitivity of results to weights, catchment thresholds, and cluster count.

### Map profile (app output)
`GET /sa2?lat=&lon=` → point-in-polygon → JSON:
```json
{
  "sa2_code21": "...", "sa2_name21": "...", "remoteness": "...",
  "typology": {"cluster": 3, "label": "..."},
  "modules": {"geographic": {"score":..., "pctl_ra":..., "evidence": {...}, "quality": "ok"}, "...": {}},
  "top_factors": ["...", "..."],
  "caveats": ["..."]
}
```
Any future LLM-generated narrative must only paraphrase this JSON — no invented facts.

The public-facing map shows ACCHO **availability metrics at SA2 level** (e.g. travel time band, count in reach), **not** ACCHO point locations.

---

## Data handling rules
- `data/` is git-ignored. ACCHO file is read from a local path set in `settings.yaml`; never copied into the repo, notebooks outputs, logs, tests, or the frontend bundle.
- Tests use **synthetic** fixtures, never real ACCHO rows.
- Every API pull is snapshotted to `data/raw/<source>/<YYYY-MM-DD>/` with request params and a hash; analysis runs from snapshots, not live calls.
- Record URL, licence, and retrieval date for each source in `config/sources.yaml` (mirror the README's raw-data log).
- Rate-limit and cache all external calls. Self-host routing (OSRM/Valhalla in Docker) rather than hammering free hosted APIs.

## Conventions
- Python 3.11+, `geopandas`, `pandas`, `shapely`, `pyproj`, `pysal`/`esda`, `scikit-learn`, `requests`/`httpx`, `fastapi`, `pytest`.
- SA2 codes are always **strings** (preserve leading digits).
- Functions are pure where possible; notebooks import from `src/rha`.
- Every pipeline stage is runnable via CLI (e.g. `python -m rha.integrate.build_master`) and is idempotent.
- Type hints + docstrings; `ruff` for lint/format.

## Milestones
1. **Ingest + integrate:** build `sa2_master` from SA2 boundaries, Census, SEIFA, Remoteness, ACCHO counts. Tests for join completeness (every SA2 present, no duplicate codes).
2. **First module end-to-end:** `accho` or `geographic` (straight-line distance first, then swap in routing) → simple clickable map (Streamlit + Folium is fine for v1).
3. Add facilities layer (GA HealthDirect REST service) → `supply` module (E2SFCA).
4. Routing service → real travel times for `geographic` and `accho`.
5. Remaining modules → typology clustering, gap model, LISA.
6. Validation + sensitivity analysis → FastAPI + proper frontend.

## Current status
Milestone 1 (ingest + integrate) implemented: `python -m rha.integrate.build_master` builds `data/processed/sa2_master.parquet` (+ QA json, column dictionary); tests in `tests/`. Hospitals/GPs/transport not yet added.
