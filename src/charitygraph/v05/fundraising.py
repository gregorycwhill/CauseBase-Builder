"""Bounded fundraising-expenditure arithmetic; never an efficiency or ROI model."""
from decimal import Decimal
from pydantic import BaseModel, field_validator, model_validator
from .models import Amount

class AttributionComponent(BaseModel):
    observation_id: str
    amount: Amount
    treatment: str
    additivity_basis: str
    governed_fraction: str | None = None
    @field_validator("treatment")
    @classmethod
    def valid_treatment(cls, value):
        if value not in {"definite","possible","excluded"}: raise ValueError("invalid attribution treatment")
        return value
class FundraisingBounds(BaseModel):
    lower_bound: Amount
    upper_bound: Amount
    point_estimate: Amount | None = None
    @model_validator(mode="after")
    def ordered(self):
        if Decimal(self.upper_bound.amount) < Decimal(self.lower_bound.amount): raise ValueError("upper bound below lower bound")
        return self
def calculate_bounds(components: list[AttributionComponent]) -> FundraisingBounds:
    bases={x.additivity_basis for x in components}
    if len(bases) != len(components): raise ValueError("components lack non-overlapping additivity basis")
    currencies={x.amount.currency for x in components}
    if len(currencies)!=1: raise ValueError("mixed currencies")
    lower=sum((Decimal(x.amount.amount) for x in components if x.treatment=="definite"),Decimal())
    upper=sum((Decimal(x.amount.amount) for x in components if x.treatment in {"definite","possible"}),Decimal())
    currency=currencies.pop(); return FundraisingBounds(lower_bound=Amount(amount=str(lower),currency=currency),upper_bound=Amount(amount=str(upper),currency=currency))
