from pydantic import BaseModel, Field


class QuotationItem(BaseModel):
    name: str = Field(..., min_length=1)
    qty: int = Field(default=1, gt=0)
    unit_price: float = Field(default=0, ge=0)


class QuotationCreate(BaseModel):
    title: str = ""
    items: list[QuotationItem] = Field(default_factory=list)
    notes: str | None = None


class QuotationStatusUpdate(BaseModel):
    status: str  # draft / sent / accepted / rejected
