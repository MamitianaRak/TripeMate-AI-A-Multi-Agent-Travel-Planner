"""Custom MCP server exposing OpenWeather current conditions and forecast.

Runs as a standalone stdio process launched by the MCP client:
    python app/mcp_servers/weather_server.py
"""

import os
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://api.openweathermap.org/data/2.5"
TIMEOUT_SECONDS = 15
FORECAST_ENTRIES = 5

mcp = FastMCP("Weather MCP Server")


def _get(endpoint: str, city: str) -> dict[str, Any]:
    # The MCP client passes the key through the subprocess environment.
    api_key = os.getenv("OPENWEATHER_API_KEY", "")

    if not api_key:
        return {"error": "OPENWEATHER_API_KEY is not configured."}

    try:
        response = requests.get(
            f"{BASE_URL}/{endpoint}",
            params={"q": city, "appid": api_key, "units": "metric"},
            timeout=TIMEOUT_SECONDS,
        )
        data = response.json()
    except requests.RequestException as exc:
        return {"error": f"Weather service request failed: {exc}"}
    except ValueError:
        return {"error": "Weather service returned invalid JSON."}

    if response.status_code != 200:
        return {"error": data.get("message", "Unknown weather service error."), "city": city}

    return data


@mcp.tool()
def get_current_weather(city: str) -> dict[str, Any]:
    """Current temperature, humidity, wind and conditions for a city."""
    data = _get("weather", city)

    if "error" in data:
        return data

    return {
        "city": data["name"],
        "temperature_c": data["main"]["temp"],
        "feels_like_c": data["main"]["feels_like"],
        "humidity": data["main"]["humidity"],
        "condition": data["weather"][0]["description"],
        "wind_speed": data["wind"]["speed"],
    }


@mcp.tool()
def get_forecast(city: str) -> dict[str, Any]:
    """Next forecast entries (3-hour steps) for a city."""
    data = _get("forecast", city)

    if "error" in data:
        return data

    forecast = [
        {
            "datetime": item["dt_txt"],
            "temperature": item["main"]["temp"],
            "weather": item["weather"][0]["description"],
        }
        for item in data.get("list", [])[:FORECAST_ENTRIES]
    ]

    return {"city": city, "forecast": forecast}


if __name__ == "__main__":
    from dotenv import load_dotenv

    # Allows running the server by hand with keys from `.env`.
    load_dotenv()
    mcp.run()
