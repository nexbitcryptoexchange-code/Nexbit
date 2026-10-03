"""Pydantic request/response models."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal
from datetime import datetime


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=6)


class VerifyEmailIn(BaseModel):
    code: str


class TwoFAIn(BaseModel):
    enabled: bool
    code: Optional[str] = None


class ProfileUpdateIn(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    anti_phishing_code: Optional[str] = None


class KycSubmitIn(BaseModel):
    full_name: str
    document_type: Literal["passport", "id_card", "driver_license"]
    document_number: str
    country: str
    dob: str


class KycDecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: Optional[str] = None


class OrderIn(BaseModel):
    pair: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit", "stop"]
    quantity: float = Field(gt=0)
    price: Optional[float] = None
    stop_price: Optional[float] = None


class FuturesOrderIn(BaseModel):
    pair: str
    side: Literal["long", "short"]
    leverage: int = Field(ge=1, le=125)
    quantity: float = Field(gt=0)
    entry_price: Optional[float] = None
    tp: Optional[float] = None
    sl: Optional[float] = None


class ClosePositionIn(BaseModel):
    position_id: str


class DepositIn(BaseModel):
    asset: str
    amount: float = Field(gt=0)


class WithdrawIn(BaseModel):
    asset: str
    amount: float = Field(gt=0)
    address: str
    network: Optional[str] = None


class TransferIn(BaseModel):
    asset: str
    amount: float = Field(gt=0)
    from_wallet: Literal["spot", "futures", "earn"]
    to_wallet: Literal["spot", "futures", "earn"]


class EarnSubscribeIn(BaseModel):
    product_id: str
    amount: float = Field(gt=0)


class ApiKeyIn(BaseModel):
    label: str
    permissions: List[Literal["read", "trade", "withdraw"]]


class AdminUserUpdateIn(BaseModel):
    status: Optional[Literal["active", "suspended", "banned"]] = None
    role: Optional[Literal["user", "admin", "support"]] = None
    kyc_status: Optional[Literal["unverified", "pending", "approved", "rejected"]] = None


class AdminTxDecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Optional[str] = None


class MarketPairIn(BaseModel):
    symbol: str
    base: str
    quote: str
    min_qty: float = 0.0001
    tick: float = 0.01
    maker_fee: float = 0.001
    taker_fee: float = 0.001
    enabled: bool = True


class FeeConfigIn(BaseModel):
    spot_maker: float
    spot_taker: float
    futures_maker: float
    futures_taker: float
    withdraw_fee_pct: float


class SupportTicketIn(BaseModel):
    subject: str
    message: str
    category: Optional[str] = "general"


class SupportReplyIn(BaseModel):
    ticket_id: str
    message: str

