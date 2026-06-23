from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int

