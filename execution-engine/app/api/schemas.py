from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID
from datetime import datetime
from decimal import Decimal

#registeration and login request payloads
class UserCreate(BaseModel):
    email: EmailStr
    password: str

#outgoing user data (without password)
class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime

    #this allows pydantic to read data from sqlalchemy orm models 
    model_config = ConfigDict(from_attributes=True)

#outgoing token dataa
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int

# --- Portfolio Schemas ---
class PortfolioResponse(BaseModel):
    asset_symbol: str
    balance: Decimal
    locked_balance: Decimal

    model_config = ConfigDict(from_attributes=True)

# --- Trading Schemas ---
class TradeExecuteRequest(BaseModel):
    type: str # 'BUY' or 'SELL'
    pair: str # e.g., 'BTC-USD'
    amount: Decimal # Amount of the base asset (e.g., 0.5 BTC)
    price: Decimal # Price per unit (e.g., 65000.00)

class TransactionResponse(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    pair: str
    amount: Decimal
    price: Decimal
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)