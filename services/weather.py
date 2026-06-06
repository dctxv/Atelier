"""Weather API integration via OpenWeatherMap."""
import httpx
from services import config, http_client

async def get_weather(location: str) -> dict | None:
    api_key = await config.get_secret("weather_api_key")
    if not api_key:
        return None
        
    try:
        # Geocode
        geo_url = "http://api.openweathermap.org/geo/1.0/direct"
        geo_resp = await http_client.client().get(geo_url, params={"q": location, "limit": 1, "appid": api_key}, timeout=5)
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
        if not geo_data:
            return {"error": f"Location '{location}' not found."}
            
        lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
        name = geo_data[0]["name"]
        country = geo_data[0].get("country", "")
        
        # Current weather
        weather_url = "https://api.openweathermap.org/data/2.5/weather"
        w_resp = await http_client.client().get(weather_url, params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}, timeout=5)
        w_resp.raise_for_status()
        w_data = w_resp.json()
        
        desc = w_data["weather"][0]["description"]
        temp = w_data["main"]["temp"]
        feels_like = w_data["main"]["feels_like"]
        humidity = w_data["main"]["humidity"]
        wind_speed = w_data["wind"]["speed"]
        
        return {
            "location": f"{name}, {country}".strip(", "),
            "temperature_celsius": temp,
            "feels_like_celsius": feels_like,
            "condition": desc,
            "humidity_percent": humidity,
            "wind_speed_m_s": wind_speed,
        }
    except Exception as e:
        return {"error": f"Failed to fetch weather: {str(e)}"}
