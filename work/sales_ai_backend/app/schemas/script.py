from pydantic import BaseModel, Field


class ScriptCreate(BaseModel):
    title: str = Field(..., min_length=1, description="话术标题")
    category: str = Field(default="general", description="分类")
    content: str = Field(..., min_length=1, description="话术内容")
