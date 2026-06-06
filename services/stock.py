"""Stock API integration via Finnhub."""
from services import config, http_client

async def get_stock(ticker: str) -> dict | None:
    api_key = await config.get_secret("stock_api_key")
    if not api_key:
        return None
        
    try:
        url = "https://finnhub.io/api/v1/quote"
        resp = await http_client.client().get(url, params={"symbol": ticker.upper(), "token": api_key}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("d") is None and data.get("c") == 0:
            return {"error": f"Ticker '{ticker}' not found or invalid."}
            
        return {
            "symbol": ticker.upper(),
            "current_price": data.get("c"),
            "change": data.get("d"),
            "percent_change": data.get("dp"),
            "high_day": data.get("h"),
            "low_day": data.get("l"),
            "open_day": data.get("o"),
            "previous_close": data.get("pc")
        }
    except Exception as e:
        return {"error": f"Failed to fetch stock data: {str(e)}"}
