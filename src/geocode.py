'''
GEOCODING THE RECORDED NACCHO LOCATIONS
---------------------------------------

Author: Tilly
Date: October 2026
'''

import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# file paths
input_file = "data/raw/NACCHO_locations.xlsx"
output_file = "data/processed/NACCHO_locations_geocoded.xlsx"

# load data, postcode is string as NT starts in 0.
df = pd.read_excel(
    input_file,
    dtype={"postcode": str}
)

# checking 4 digits in case of above mistype.
df["postcode"] = df["postcode"].str.zfill(4)

# testing
# df = df.head(10)

# Nomainatim geocoder converts the addresses to coordinates, adding timeout due to timeout issue.
geolocator = Nominatim(
    user_agent="remote_healthcare_access_project",
    timeout=10
)

# This is to limit the number of requests to the geocoder to avoid sending too many requests together, also retries.
geocode = RateLimiter(
    geolocator.geocode,
    min_delay_seconds=2,
    max_retries=3,
    error_wait_seconds=5,
    swallow_exceptions=True # prevents failed request from stopping the program.
)

# takes one row and connects all fields.
def geocode_address(row):
    address = (
        f"{row['address']}, "
        f"{row['suburb_town']}, "
        f"{row['state']}, "
        f"{row['postcode']}, "
        f"Australia"
    )

    try:
        location = geocode(address,country_codes="au") # sends address, restricting search to aus.

        # extracts coordinates if found.
        if location:
            print(f"Found: {address}")
            return pd.Series({"latitude": location.latitude,"longitude": location.longitude})
        print(f"Not found: {address}") # no matching address

    except Exception as e:
        print(f"Error with {address}: {e}") # error

    # for if it could not be geocoded.
    return pd.Series({
        "latitude": None,
        "longitude": None
    })

# create empty list to store coordinates
coordinates = []

# iterates through each row in the dataframe.
for _, row in df.iterrows():
    result = geocode_address(row)
    coordinates.append(result)

# convert list of results to a dataframe
coordinates = pd.DataFrame(coordinates)

# add the coordinates to the original dataframe
df["latitude"] = coordinates["latitude"]
df["longitude"] = coordinates["longitude"]


# save results to a new file, not added an unneccessary index column.
df.to_excel(output_file, index=False)
