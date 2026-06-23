from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenUser(BaseModel):
    id: int
    name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: TokenUser

