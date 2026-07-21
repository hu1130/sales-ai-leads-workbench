from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenUser(BaseModel):
    id: int
    tenant_id: int
    tenant_name: str | None = None
    name: str
    role: str
    phone: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: TokenUser
