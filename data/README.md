# Raw Data Information

I will not be posting the specific datasets used for various reasons, however, here I will document the URLs and the download dates for reference. The main reason for this falls with the publication of ACCHO locations. These are shared only in map form, this seems intentional and I do not want to lead to any misuse of these valuable sources. 

### NACCHO_locations
This dataset I have built details the locations of ACCHO services across Australia. This information was manually recorded from:
- https://www.naccho.org.au/locations/ 18.08.26
- https://healthinfonet.ecu.edu.au/key-resources/health-professionals/health-workers/map-of-aboriginal-and-islander-healthmedical-services/ 19.08.26

I recorded this through Excel recording seperate columns for name, state, address, suburb_town, postcode, phone, and notes. This notes section was mainly used for the more remote areas, in which the address is via another town, or for any small address mistakes I noticed during my process.


The geocoded version (`data/processed/NACCHO_locations_geocoded.xlsx`) adds `latitude`, `longitude` and `geocode_method` (nominatim or manual). The pipeline reads only the coordinates, state and geocode method, drops rows with duplicate coordinates, and outputs **counts per SA2 only**: never point locations.

### ABS datasets (2021, CC BY 4.0)
Full URLs, retrieval dates and hashes are kept in `config/sources.yaml`.

| File / folder | Contents |
|---|---|
| `ASGS_2021_Main_Structure_GDA2020.gpkg` | ASGS Ed. 3 boundaries: SA2 (used as the base), SA1 and Mesh Block layers |
| `ASGS_Ed3_2021_RA_GDA2020.gpkg` | Remoteness Area polygons (state × class) |
| `SEIFA.xlsx` | SEIFA 2021 SA2 tables (Table 2 = IRSD, Table 6 = excluded areas) |
| `census_gcp_2021_sa2/` | 2021 Census GCP DataPack, SA2, extracted from `2021_GCP_SA2_for_AUS_short-header.zip` incl. `Metadata/` |
| `mesh_block_counts_2021/2026-11-25/` | Census 2021 Mesh Block Counts (persons per mesh block), used to weight remoteness by population |

Note: an earlier copy in `census_data/` has every file labelled one table number too high (e.g. its "G02" is really G01) and is missing G62. Don't use it.
