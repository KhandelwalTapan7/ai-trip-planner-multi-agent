import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def geocode(place):
    r = requests.get(GEOCODE_URL, params={"name": place, "count": 1}, timeout=15)
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        return None
    top = results[0]
    return top["latitude"], top["longitude"]


def get_weather(coords, start_date, end_date):
    lat, lon = coords
    r = requests.get(
        WEATHER_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "start_date": start_date,
            "end_date": end_date,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("daily", {})
