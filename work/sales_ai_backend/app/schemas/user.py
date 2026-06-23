from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    phone: str | None = None
    role: str = "sales"


class UserUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    role: str | None = None
    status: str | None = None
    password: str | None = None


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    phone: str | None
    role: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

