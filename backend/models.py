"""Pydantic request/response models."""
from pydantic import BaseModel, EmailStr, Field, model_validator, ConfigDict
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
    model_config = ConfigDict(allow_inf_nan=False)
    pair: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit", "stop"]
    quantity: float = Field(gt=0)
    price: Optional[float] = None
    stop_price: Optional[float] = None


class FuturesOrderIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
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
    model_config = ConfigDict(allow_inf_nan=False)
    asset: str
    amount: float = Field(gt=0)


class WithdrawIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    asset: str
    amount: float = Field(gt=0)
    address: str
    network: Optional[str] = None


class TransferIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    asset: str
    amount: float = Field(gt=0)
    from_wallet: Literal["spot", "futures", "earn"]
    to_wallet: Literal["spot", "futures", "earn"]


class EarnSubscribeIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
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


class AdminBalanceAdjustmentIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    user_id: str
    asset: str
    amount: float = Field(gt=0)
    action: Literal["credit", "debit"]
    note: Optional[str] = None
    reference_id: Optional[str] = Field(default=None, min_length=8, max_length=100)


class MarketPairIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    symbol: str = Field(min_length=5, max_length=30)
    base: str = Field(min_length=2, max_length=15)
    quote: str = Field(min_length=2, max_length=15)
    min_qty: float = Field(default=0.0001, gt=0)
    tick: float = Field(default=0.01, gt=0)
    maker_fee: float = Field(default=0.001, ge=0)
    taker_fee: float = Field(default=0.001, ge=0)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_pair(self):
        self.symbol = self.symbol.strip().upper()
        self.base = self.base.strip().upper()
        self.quote = self.quote.strip().upper()
        if self.symbol != f"{self.base}/{self.quote}":
            raise ValueError("symbol must match base/quote")
        if self.base == self.quote:
            raise ValueError("base and quote assets must differ")
        return self


class FeeConfigIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    spot_maker: float = Field(ge=0)
    spot_taker: float = Field(ge=0)
    futures_maker: float = Field(ge=0)
    futures_taker: float = Field(ge=0)
    withdraw_fee_pct: float = Field(ge=0)


class FeeTreasuryIn(BaseModel):
    user_id: str = Field(min_length=1)


class SupportTicketIn(BaseModel):
    subject: str
    message: str
    category: Optional[str] = "general"


class SupportReplyIn(BaseModel):
    ticket_id: str
    message: str
