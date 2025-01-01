from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import os
from datetime import datetime, timedelta

app = FastAPI(title="Crypto Market Data API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER', 'your_user')}:" \
               f"{os.getenv('POSTGRES_PASSWORD', 'your_password')}@" \
               f"{os.getenv('POSTGRES_HOST', 'postgres')}:5432/" \
               f"{os.getenv('POSTGRES_DB', 'crypto_data')}"

engine = create_engine(DATABASE_URL)

# Models
class MarketData(BaseModel):
    symbol: str
    timestamp: datetime
    price: float
    volume: float
    source: str

class CombinedMarketData(BaseModel):
    symbol: str
    binance_price: Optional[float]
    coingecko_price: Optional[float]
    myinvestor_price: Optional[float]
    last_updated: datetime
    binance_volume: Optional[float]
    coingecko_volume: Optional[float]
    myinvestor_volume: Optional[float]

# Dependencies
def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()

# Endpoints
@app.get("/api/v1/market-data/{symbol}", response_model=List[MarketData])
async def get_market_data(symbol: str, source: str = None, db: Session = Depends(get_db)):
    try:
        query = """
            SELECT symbol, timestamp, price, volume, source
            FROM (
                SELECT symbol, timestamp, close as price, volume, 'binance' as source
                FROM binance_data
                WHERE symbol = :symbol
                UNION ALL
                SELECT symbol, timestamp, price_usd as price, volume_24h as volume, 'coingecko' as source
                FROM coingecko_data
                WHERE symbol = :symbol
                UNION ALL
                SELECT symbol, date as timestamp, closing_price as price, volume, 'myinvestor' as source
                FROM myinvestor_data
                WHERE symbol = :symbol
            ) combined
            WHERE (:source IS NULL OR source = :source)
            ORDER BY timestamp DESC
            LIMIT 1000
        """
        result = db.execute(text(query), {"symbol": symbol, "source": source})
        return [dict(row) for row in result]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/combined-data/{symbol}", response_model=CombinedMarketData)
async def get_combined_data(symbol: str, db: Session = Depends(get_db)):
    try:
        query = """
            SELECT *
            FROM crypto_combined_data
            WHERE symbol = :symbol
        """
        result = db.execute(text(query), {"symbol": symbol}).fetchone()
        if result is None:
            raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}")
        return dict(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/latest-prices", response_model=List[CombinedMarketData])
async def get_latest_prices(db: Session = Depends(get_db)):
    try:
        query = """
            SELECT *
            FROM crypto_combined_data
            ORDER BY last_updated DESC
        """
        result = db.execute(text(query))
        return [dict(row) for row in result]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "healthy"}

# Keep your existing chat endpoint
@app.post("/chat/")
async def chat_endpoint(data_input: Dict[str, Any]):
    try:
        df = pd.DataFrame(data_input["data"])
        result = process_data(df, data_input["question"])
        return {"response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def process_data(df: pd.DataFrame, question: str) -> str:
    try:
        num_rows = len(df)
        num_cols = len(df.columns)
        column_names = ", ".join(df.columns)
        
        response = f"""
        Analysis of DataFrame:
        - Rows: {num_rows}
        - Columns: {num_cols}
        - Available columns: {column_names}
        - Question: {question}
        """
        
        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
        if len(numeric_cols) > 0:
            stats = df[numeric_cols].describe()
            response += "\nNumeric columns statistics:\n"
            response += str(stats)
            
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing data: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)