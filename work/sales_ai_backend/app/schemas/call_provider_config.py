from pydantic import BaseModel, Field


class CallProviderConfigOut(BaseModel):
    provider: str
    base_url: str | None
    app_id: str | None
    app_key_configured: bool
    app_key_mask: str | None
    app_secret_configured: bool
    app_secret_mask: str | None
    caller: str | None
    script_id: str | None
    webhook_secret_configured: bool
    webhook_secret_mask: str | None
    timeout: float
    enabled: bool
    source: str
    updated_at: str | None = None
    updated_by: int | None = None


class CallProviderConfigUpdate(BaseModel):
    provider: str | None = Field(default=None, max_length=40)
    base_url: str | None = Field(default=None, max_length=500)
    app_id: str | None = Field(default=None, max_length=160)
    app_key: str | None = Field(default=None, max_length=1000)
    app_secret: str | None = Field(default=None, max_length=2000)
    caller: str | None = Field(default=None, max_length=32)
    webhook_secret: str | None = Field(default=None, max_length=2000)
    timeout: float | None = Field(default=None, ge=1, le=300)
    enabled: bool | None = None
    clear_app_key: bool = False
    clear_app_secret: bool = False
    clear_webhook_secret: bool = False


class CallProviderStatusOut(BaseModel):
    provider: str
    configured: bool
    mode: str
    base_url_configured: bool
    app_id_configured: bool
    app_key_configured: bool
    app_secret_configured: bool
    caller_configured: bool
    script_id_configured: bool
    webhook_secret_configured: bool
    timeout: float
    ai_robot_webhook_url: str
    sales_callback_webhook_url: str
    notes: list[str]


class CallProviderTestRequest(BaseModel):
    provider: str | None = Field(default=None, max_length=40)
    sales_phone: str | None = Field(default=None, max_length=32)
    customer_phone: str = Field(min_length=3, max_length=32)
    script: str | None = Field(default=None, max_length=1000)


class CallProviderTestOut(BaseModel):
    ok: bool
    provider: str
    test_type: str
    provider_call_id: str | None = None
    initial_status: str | None = None
    message: str
    raw_payload: dict | None = None
