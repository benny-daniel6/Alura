"""
Weather service for Alura AI Stylist.

Uses Open-Meteo (free, no API key) to fetch current weather conditions.
Provides structured weather context for LLM outfit generation prompts.
"""

import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# WMO Weather interpretation codes mapped to human-readable descriptions
WMO_CODE_DESCRIPTIONS: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

# Open-Meteo API base URL
OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"


class WeatherService:
    """Fetches current weather conditions using the Open-Meteo free API."""

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self._geocode_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    async def get_current_weather(
        self, latitude: float, longitude: float
    ) -> Dict[str, Any]:
        """
        Fetch current weather for a given lat/lon.

        Returns:
            {
                "temperature_c": 22.5,
                "apparent_temperature_c": 24.1,
                "humidity_pct": 55,
                "wind_speed_kmh": 12.3,
                "weather_code": 2,
                "condition": "Partly cloudy",
                "is_rainy": False,
                "is_cold": False,
                "is_hot": False,
            }
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "timezone": "auto",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(OPEN_METEO_BASE, params=params)
                response.raise_for_status()
                data = response.json()

            current = data.get("current", {})
            temp_c = current.get("temperature_2m", 20.0)
            apparent_c = current.get("apparent_temperature", temp_c)
            humidity = current.get("relative_humidity_2m", 50)
            wind_kmh = current.get("wind_speed_10m", 0.0)
            weather_code = current.get("weather_code", 0)

            condition = WMO_CODE_DESCRIPTIONS.get(weather_code, "Unknown")

            # Classify for styling context
            is_rainy = weather_code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
            is_cold = temp_c < 12.0
            is_hot = temp_c > 30.0

            return {
                "temperature_c": temp_c,
                "apparent_temperature_c": apparent_c,
                "humidity_pct": humidity,
                "wind_speed_kmh": wind_kmh,
                "weather_code": weather_code,
                "condition": condition,
                "is_rainy": is_rainy,
                "is_cold": is_cold,
                "is_hot": is_hot,
            }

        except Exception as e:
            logger.warning(f"Weather API fetch failed: {e}. Using fallback defaults.")
            return self._fallback_weather()

    async def geocode(self, city: str) -> Optional[Dict[str, Any]]:
        """
        Resolves a city name to {"latitude", "longitude", "name"} with Open-Meteo geocoding (no key).
        Results are cached for the process lifetime; returns None when the city is unknown or the call fails.
        """
        key = city.strip().lower()
        if not key:
            return None
        if key in self._geocode_cache:
            return self._geocode_cache[key]
        # "Mumbai, India" -> search "Mumbai"; the API matches on the place name only
        name = city.split(",")[0].strip()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    OPEN_METEO_GEOCODING, params={"name": name, "count": 1, "language": "en", "format": "json"}
                )
                response.raise_for_status()
                results = response.json().get("results") or []
        except Exception as e:
            logger.warning(f"Geocoding '{city}' failed: {e}")
            return None
        if not results:
            self._geocode_cache[key] = None
            return None
        top = results[0]
        label = ", ".join(p for p in (top.get("name"), top.get("country")) if p)
        place = {"latitude": top["latitude"], "longitude": top["longitude"], "name": label}
        self._geocode_cache[key] = place
        return place

    @staticmethod
    def _fallback_weather() -> Dict[str, Any]:
        """Graceful fallback when weather API is unreachable."""
        return {
            "temperature_c": 20.0,
            "apparent_temperature_c": 20.0,
            "humidity_pct": 50,
            "wind_speed_kmh": 8.0,
            "weather_code": 1,
            "condition": "Mainly clear (fallback)",
            "is_rainy": False,
            "is_cold": False,
            "is_hot": False,
        }

    @staticmethod
    def weather_to_prompt_snippet(weather: Dict[str, Any]) -> str:
        """Format weather data as a concise prompt snippet for the LLM."""
        return (
            f"Current weather: {weather['condition']}, "
            f"{weather['temperature_c']}°C (feels like {weather['apparent_temperature_c']}°C), "
            f"humidity {weather['humidity_pct']}%, "
            f"wind {weather['wind_speed_kmh']} km/h. "
            f"{'It is raining — suggest waterproof outerwear or an umbrella.' if weather['is_rainy'] else ''}"
            f"{'It is cold — prioritize layering and warm fabrics.' if weather['is_cold'] else ''}"
            f"{'It is hot — suggest breathable, lightweight fabrics.' if weather['is_hot'] else ''}"
        )


weather_service = WeatherService()
