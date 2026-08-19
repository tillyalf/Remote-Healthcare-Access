import pandas as pd
from geopy.geocoders import Nominatim
from time import sleep


# loads file
input_file = "data/raw/NACCHO_locations.xlsx"
output_file = "data/processed/NACCHO_locations_geocoded.xlsx"

df = pd.read_excel(input_file)

geolocator = Nominatim(
    user_agent="remote_healthcare_access_project"
)


# function which geocodes full address 
def geocode_address(row):
    address = (
        f"{row['address']}, "
        f"{row['suburb_town']}, "
        f"{row['state']}, "
        f"{row['postcode']}, "
        f"Australia"
    )

    try:
        location = geolocator.geocode(address)

        if location:
            print(f"Found: {address}")
            return pd.Series({"latitude": location.latitude,"longitude": location.longitude})
        print(f"Not found: {address}")

    except Exception as e:
        print(f"Error with {address}: {e}")

    return pd.Series({
        "latitude": None,
        "longitude": None
    })


# using an array to make it pause to not hit usage restrictions
coordinates = []
for _, row in df.iterrows():
    result = geocode_address(row)
    coordinates.append(result)
    sleep(2)

# apply function to each row
coordinates = pd.DataFrame(coordinates)
df["latitude"] = coordinates["latitude"]
df["longitude"] = coordinates["longitude"]


# save results 
df.to_excel(output_file, index=False)
