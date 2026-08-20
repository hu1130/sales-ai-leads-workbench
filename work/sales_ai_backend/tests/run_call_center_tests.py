from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_TMP = ROOT / ".test_tmp_call_center"
TEST_DB = TEST_TMP / "sales_ai_call_center_test.db"
TEST_UPLOADS = TEST_TMP / "uploads"


def configure_test_environment() -> None:
    if TEST_TMP.exists():
        resolved = TEST_TMP.resolve()
        if resolved == ROOT.resolve() or ROOT.resolve() not in resolved.parents:
            raise RuntimeError(f"Refusing to remove unexpected path: {resolved}")
        shutil.rmtree(TEST_TMP)
    TEST_UPLOADS.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
    os.environ["UPLOAD_DIR"] = str(TEST_UPLOADS)
    os.environ["JWT_SECRET_KEY"] = "call-center-test-secret-key"
    os.environ["DEFAULT_ADMIN_USERNAME"] = "admin"
    os.environ["DEFAULT_ADMIN_PASSWORD"] = "admin123"
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ["DASHSCOPE_API_KEY"] = ""
    os.environ["ASR_PROVIDER"] = ""
    os.environ["INTEGRATION_API_KEY"] = "integration-test-key"
    os.environ["INTEGRATION_TENANT_ID"] = "1"
    os.environ["PLATFORM_SERVICE_TOKEN"] = "platform-test-service-token"
    os.environ["PLATFORM_TENANT_ID"] = "1"


configure_test_environment()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class TestFailure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise TestFailure(message)


def expect_status(response, status_code: int, label: str) -> dict:
    check(
        response.status_code == status_code,
        f"{label} expected {status_code}, got {response.status_code}: {response.text[:500]}",
    )
    if response.content:
        return response.json()
    return {}


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    payload = expect_status(
        client.post("/api/auth/login", json={"username": username, "password": password}),
        200,
        f"login {username}",
    )
    return {"Authorization": f"Bearer {payload['access_token']}"}


def create_sales_user(client: TestClient, headers: dict[str, str], username: str) -> dict:
    return expect_status(
        client.post(
            "/api/users",
            headers=headers,
            json={
                "username": username,
                "password": "sales123456",
                "name": username,
                "phone": "13900000000",
                "role": "sales",
            },
        ),
        200,
        f"create sales user {username}",
    )


def create_customer(client: TestClient, headers: dict[str, str], name: str, phone: str, owner_id: int | None = None) -> dict:
    payload = {"name": name, "phone": phone, "source": "call-center-test"}
    if owner_id:
        payload["owner_id"] = owner_id
        payload["lead_status"] = "assigned"
    return expect_status(client.post("/api/customers", headers=headers, json=payload), 200, f"create customer {name}")


def run() -> None:
    with TestClient(app) as client:
        expect_status(client.get("/health"), 200, "health")
        expect_status(client.get("/api/call-campaigns"), 401, "unauthenticated campaigns")
        expect_status(client.get("/api/call-reports/overview"), 401, "unauthenticated overview")

        admin_headers = login(client, "admin", "admin123")
        suffix = datetime.now().strftime("%H%M%S%f")
        sales_a = create_sales_user(client, admin_headers, f"call_sales_a_{suffix}")
        sales_b = create_sales_user(client, admin_headers, f"call_sales_b_{suffix}")
        sales_headers = login(client, sales_a["username"], "sales123456")

        provider_status = expect_status(
            client.get("/api/call-provider/status", headers=admin_headers),
            200,
            "call provider status",
        )
        check(provider_status["provider"] == "mock", f"provider should default to mock: {provider_status}")
        check(provider_status["configured"], f"mock provider should be configured: {provider_status}")
        check("ai-robot-calls/webhook/mock" in provider_status["ai_robot_webhook_url"], f"robot webhook url mismatch: {provider_status}")
        check("sales-callbacks/webhook/mock" in provider_status["sales_callback_webhook_url"], f"callback webhook url mismatch: {provider_status}")
        provider_config = expect_status(
            client.get("/api/call-provider/config", headers=admin_headers),
            200,
            "call provider config",
        )
        check(provider_config["source"] == "environment", f"initial provider config should come from env: {provider_config}")
        saved_provider_config = expect_status(
            client.patch(
                "/api/call-provider/config",
                headers=admin_headers,
                json={
                    "provider": "mock",
                    "base_url": "https://mock-call-provider.local",
                    "app_id": "mock-app-id",
                    "app_key": "mock-app-key-secret",
                    "app_secret": "mock-app-secret-value",
                    "caller": "13900000000",
                    "webhook_secret": "mock-webhook-secret",
                    "timeout": 18,
                    "enabled": True,
                },
            ),
            200,
            "save encrypted call provider config",
        )
        check(saved_provider_config["source"] == "database", f"saved config should come from database: {saved_provider_config}")
        check(saved_provider_config["app_key_configured"], f"app key should be configured: {saved_provider_config}")
        check(saved_provider_config["app_key_mask"] != "mock-app-key-secret", f"app key must be masked: {saved_provider_config}")
        check(saved_provider_config["app_secret_configured"], f"app secret should be configured: {saved_provider_config}")
        check(saved_provider_config["webhook_secret_configured"], f"webhook secret should be configured: {saved_provider_config}")
        check(saved_provider_config["caller"] == "13900000000", f"caller mismatch: {saved_provider_config}")
        protected_webhook = client.post(
            "/api/ai-robot-calls/webhook/mock",
            json={"provider_call_id": "missing", "event_type": "completed"},
        )
        check(protected_webhook.status_code == 401, f"webhook should require saved secret: {protected_webhook.text}")
        protected_webhook_with_secret = client.post(
            "/api/ai-robot-calls/webhook/mock",
            headers={"X-Call-Provider-Secret": "mock-webhook-secret"},
            json={"provider_call_id": "missing", "event_type": "completed"},
        )
        check(protected_webhook_with_secret.status_code == 404, f"webhook with secret should pass auth guard: {protected_webhook_with_secret.text}")
        cleared_provider_config = expect_status(
            client.patch(
                "/api/call-provider/config",
                headers=admin_headers,
                json={"clear_webhook_secret": True},
            ),
            200,
            "clear call provider webhook secret",
        )
        check(not cleared_provider_config["webhook_secret_configured"], f"webhook secret should be cleared: {cleared_provider_config}")
        expect_status(
            client.get("/api/call-provider/status", headers=sales_headers),
            403,
            "sales cannot read provider status",
        )
        provider_callback_test = expect_status(
            client.post(
                "/api/call-provider/test-callback",
                headers=admin_headers,
                json={"provider": "mock", "customer_phone": "13800138000"},
            ),
            200,
            "test call provider callback",
        )
        check(provider_callback_test["ok"] and provider_callback_test["provider"] == "mock", f"callback provider test mismatch: {provider_callback_test}")
        provider_robot_test = expect_status(
            client.post(
                "/api/call-provider/test-ai-robot",
                headers=admin_headers,
                json={"provider": "mock", "customer_phone": "13800138000", "script": "connectivity test"},
            ),
            200,
            "test call provider ai robot",
        )
        check(provider_robot_test["ok"] and provider_robot_test["provider"] == "mock", f"robot provider test mismatch: {provider_robot_test}")

        expect_status(
            client.post("/api/customers/assign-random", headers=sales_headers, json={}),
            403,
            "sales cannot random assign customers",
        )
        create_customer(client, admin_headers, f"Random Assign A {suffix}", "13800138101")
        create_customer(client, admin_headers, f"Random Assign B {suffix}", "13800138102")
        random_assign = expect_status(
            client.post(
                "/api/customers/assign-random",
                headers=admin_headers,
                json={"sales_user_ids": [sales_a["id"], sales_b["id"]], "limit": 2},
            ),
            200,
            "random assign unassigned customers",
        )
        check(random_assign["assigned_count"] == 2, f"random assign should assign two customers: {random_assign}")
        random_customers = expect_status(
            client.get("/api/customers", headers=admin_headers, params={"keyword": f"Random Assign {suffix}", "page_size": 10}),
            200,
            "list random assigned customers",
        )
        check(len(random_customers["items"]) == 2, f"random assigned customer list mismatch: {random_customers}")
        check(
            all(
                item["lead_status"] == "assigned" and item["owner_id"] in {sales_a["id"], sales_b["id"]}
                for item in random_customers["items"]
            ),
            f"random assigned customers should be assigned to selected sales users: {random_customers}",
        )

        integration_provider_status = expect_status(
            client.get("/api/integrations/call-provider/status", headers=admin_headers),
            200,
            "integration call provider status",
        )
        check(integration_provider_status["provider"] == "mock", f"integration provider status mismatch: {integration_provider_status}")
        expect_status(
            client.get("/api/integrations/call-provider/status", headers=sales_headers),
            403,
            "sales cannot read integration provider status",
        )

        missing_integration_key = client.post(
            "/api/integrations/website/leads",
            json={"name": "Website Lead Missing Key", "phone": "13800138201"},
        )
        check(missing_integration_key.status_code == 401, f"missing integration key should be rejected: {missing_integration_key.text}")
        integration_headers = {"X-Integration-Key": "integration-test-key"}
        website_lead = expect_status(
            client.post(
                "/api/integrations/website/leads",
                headers=integration_headers,
                json={
                    "external_id": f"web-{suffix}",
                    "name": f"Website Lead {suffix}",
                    "phone": "13800138201",
                    "wechat_id": f"web_wechat_{suffix}",
                    "source": "official_website",
                    "campaign": "landing-page",
                    "page_url": "https://example.com/contact",
                    "message": "interested in sales ai",
                    "utm_source": "baidu",
                },
            ),
            200,
            "create website integration lead",
        )
        check(website_lead["accepted"] and website_lead["created"], f"website lead should be created: {website_lead}")
        duplicate_website_lead = expect_status(
            client.post(
                "/api/integrations/website/leads",
                headers=integration_headers,
                json={
                    "name": f"Website Lead Again {suffix}",
                    "phone": "13800138201",
                    "message": "second website message",
                },
            ),
            200,
            "dedupe website integration lead",
        )
        check(not duplicate_website_lead["created"], f"duplicate website lead should update existing customer: {duplicate_website_lead}")
        check(
            duplicate_website_lead["customer_id"] == website_lead["customer_id"],
            f"duplicate website lead should keep customer id: {duplicate_website_lead}",
        )
        integration_leads = expect_status(
            client.get(
                "/api/integrations/sales-ai/leads",
                headers=integration_headers,
                params={"keyword": f"Website Lead {suffix}", "page_size": 10},
            ),
            200,
            "list integration sales ai leads",
        )
        check(integration_leads["total"] == 1, f"integration leads should include website lead: {integration_leads}")
        integration_customer = integration_leads["items"][0]
        check(integration_customer["id"] == website_lead["customer_id"], f"integration lead customer mismatch: {integration_customer}")
        check(integration_customer["lead_status"] == "unassigned", f"website lead should be unassigned: {integration_customer}")
        check(integration_customer["latest_followup"]["source"] == "website", f"website lead followup missing: {integration_customer}")
        integration_customer_detail = expect_status(
            client.get(f"/api/integrations/sales-ai/customers/{website_lead['customer_id']}", headers=integration_headers),
            200,
            "integration customer detail",
        )
        check(integration_customer_detail["phone"] == "13800138201", f"integration customer phone mismatch: {integration_customer_detail}")
        integration_followups = expect_status(
            client.get(f"/api/integrations/sales-ai/customers/{website_lead['customer_id']}/followups", headers=integration_headers),
            200,
            "integration customer followups",
        )
        check(len(integration_followups) >= 2, f"website duplicate submissions should create followups: {integration_followups}")
        check(all(item["source"] == "website" for item in integration_followups), f"website followups should be sourced: {integration_followups}")

        customer_a = create_customer(client, admin_headers, f"Call Test A {suffix}", "13800138001", sales_a["id"])
        customer_b = create_customer(client, admin_headers, f"Call Test B {suffix}", "13800138002", sales_a["id"])

        expect_status(
            client.post("/api/call-campaigns", headers=admin_headers, json={"name": ""}),
            422,
            "empty campaign name validation",
        )
        expect_status(
            client.post("/api/call-campaigns", headers=sales_headers, json={"name": "Denied campaign"}),
            403,
            "sales cannot create campaign",
        )
        expect_status(
            client.post("/api/call-attempts", headers=admin_headers, json={"call_mode": "manual"}),
            400,
            "attempt requires target/customer/phone",
        )

        campaign = expect_status(
            client.post(
                "/api/call-campaigns",
                headers=admin_headers,
                json={
                    "name": f"Call Center MVP {suffix}",
                    "scenario": "sales_lead_filter",
                    "customer_ids": [customer_a["id"], customer_b["id"]],
                    "assigned_user_id": sales_a["id"],
                },
            ),
            200,
            "create campaign",
        )
        check(campaign["total_count"] == 2, f"campaign should have two targets: {campaign}")

        imported = expect_status(
            client.post(
                f"/api/call-campaigns/{campaign['id']}/targets/import-from-customers",
                headers=admin_headers,
                json={"customer_ids": [customer_a["id"], customer_b["id"]], "assigned_user_id": sales_a["id"]},
            ),
            200,
            "duplicate import",
        )
        check(imported["total"] == 2, f"duplicate import should not create extra targets: {imported}")

        expect_status(client.post(f"/api/call-campaigns/{campaign['id']}/start", headers=admin_headers), 200, "start campaign")
        expect_status(client.post(f"/api/call-campaigns/{campaign['id']}/pause", headers=admin_headers), 200, "pause campaign")
        expect_status(client.post(f"/api/call-campaigns/{campaign['id']}/start", headers=admin_headers), 200, "restart campaign")

        admin_targets = expect_status(
            client.get(f"/api/call-campaigns/{campaign['id']}/targets?page_size=20", headers=admin_headers),
            200,
            "admin list targets",
        )
        target = admin_targets["items"][0]
        check(target["phone"] == customer_a["phone"] or target["phone"] == customer_b["phone"], f"target phone mismatch: {target}")

        sales_campaigns = expect_status(client.get("/api/call-campaigns", headers=sales_headers), 200, "sales list campaigns")
        check(sales_campaigns["total"] == 1, f"sales should see assigned campaign only: {sales_campaigns}")
        sales_targets = expect_status(
            client.get(f"/api/call-campaigns/{campaign['id']}/targets", headers=sales_headers),
            200,
            "sales list targets",
        )
        check(sales_targets["total"] == 2, f"sales should see two assigned targets: {sales_targets}")
        expect_status(
            client.post(f"/api/call-targets/{target['id']}/assign", headers=sales_headers, json={"assigned_user_id": sales_b["id"]}),
            403,
            "sales cannot reassign target",
        )
        expect_status(
            client.patch(f"/api/call-targets/{target['id']}", headers=admin_headers, json={"status": "bad_status"}),
            400,
            "invalid target status",
        )

        attempt = expect_status(
            client.post("/api/call-attempts", headers=sales_headers, json={"target_id": target["id"]}),
            200,
            "create manual attempt",
        )
        check(attempt["call_mode"] == "manual", f"attempt should be manual mode: {attempt}")
        check(attempt["call_status"] == "dialing", f"new attempt should be dialing: {attempt}")
        check(attempt["phone"] == target["phone"], f"attempt phone mismatch: {attempt}")

        expect_status(
            client.post(f"/api/call-attempts/{attempt['id']}/finish", headers=sales_headers, json={"call_status": "invalid"}),
            400,
            "invalid call status",
        )
        finished = expect_status(
            client.post(
                f"/api/call-attempts/{attempt['id']}/finish",
                headers=sales_headers,
                json={"call_status": "connected", "duration_seconds": 86, "remark": "manual callback test"},
            ),
            200,
            "finish manual attempt",
        )
        check(finished["call_status"] == "connected" and finished["duration_seconds"] == 86, f"finish data mismatch: {finished}")

        expect_status(
            client.post(f"/api/call-attempts/{attempt['id']}/submit-transcript", headers=sales_headers, json={"transcript": "x"}),
            422,
            "short transcript validation",
        )
        transcript = (
            "\u5ba2\u6237\u5173\u5fc3\u4ef7\u683c\u548c\u62a5\u4ef7\uff0c"
            "\u8ba4\u53ef\u5408\u540c\u548c\u4ed8\u6b3e\u5b89\u6392\uff0c"
            "\u5e0c\u671b\u4eca\u5929\u6536\u5230\u65b9\u6848\uff0c"
            "\u4e0b\u5468\u90e8\u7f72\u3002"
        )
        analyzed = expect_status(
            client.post(
                f"/api/call-attempts/{attempt['id']}/submit-transcript",
                headers=sales_headers,
                json={"transcript": transcript},
            ),
            200,
            "submit transcript",
        )
        check(analyzed["intent_level"] == "\u9ad8\u610f\u5411", f"expected high intent: {analyzed}")
        check(analyzed["intent_score"] >= 80, f"expected high score: {analyzed}")
        check(analyzed["upload_record_id"], f"transcript should create upload record: {analyzed}")

        callback = expect_status(
            client.post(
                f"/api/customers/{customer_a['id']}/callback",
                headers=sales_headers,
                json={"provider": "mock", "remark": "sales callback test"},
            ),
            200,
            "start sales provider callback",
        )
        check(callback["provider"] == "mock", f"callback provider mismatch: {callback}")
        check(callback["status"] == "initiated", f"callback should be initiated: {callback}")
        check(callback["call_attempt_id"], f"callback should create call attempt: {callback}")

        bridged = expect_status(
            client.post(
                "/api/sales-callbacks/webhook/mock",
                json={"provider_call_id": callback["provider_call_id"], "event_type": "bridged"},
            ),
            200,
            "provider callback bridged webhook",
        )
        check(bridged["status"] == "bridged" and bridged["call_status"] == "connected", f"callback bridged mismatch: {bridged}")

        callback_transcript = (
            "\u9500\u552e\uff1a\u6211\u770b\u5230\u60a8\u521a\u624d\u5173\u6ce8\u62a5\u4ef7\u548c\u5408\u540c\u3002\n"
            "\u5ba2\u6237\uff1a\u5bf9\uff0c\u4eca\u5929\u53ef\u4ee5\u53d1\u6211\u62a5\u4ef7\uff0c"
            "\u4ed8\u6b3e\u6ca1\u95ee\u9898\uff0c\u6211\u4eec\u4e0b\u5468\u5c31\u60f3\u90e8\u7f72\u3002"
        )
        completed_callback = expect_status(
            client.post(
                "/api/sales-callbacks/webhook/mock",
                json={
                    "provider_call_id": callback["provider_call_id"],
                    "event_type": "completed",
                    "duration_seconds": 132,
                    "recording_url": "mock://recordings/sales-callback.wav",
                    "transcript": callback_transcript,
                },
            ),
            200,
            "provider callback completed webhook",
        )
        check(completed_callback["status"] == "completed", f"callback should complete: {completed_callback}")
        check(completed_callback["duration_seconds"] == 132, f"callback duration mismatch: {completed_callback}")

        callback_attempt = expect_status(
            client.get(f"/api/call-attempts/{callback['call_attempt_id']}", headers=sales_headers),
            200,
            "provider callback attempt detail",
        )
        check(callback_attempt["call_mode"] == "provider_callback", f"callback attempt mode mismatch: {callback_attempt}")
        check(callback_attempt["call_status"] == "connected", f"callback attempt should be connected: {callback_attempt}")
        check(callback_attempt["call_recording_id"], f"callback should create recording: {callback_attempt}")

        followups = expect_status(
            client.get(f"/api/customers/{customer_a['id']}/followups", headers=sales_headers),
            200,
            "customer followups after provider callback",
        )
        check(
            any(item["source"] == "sales_callback" for item in followups),
            f"provider callback should create sales followup: {followups}",
        )

        robot_customer = create_customer(client, admin_headers, f"Robot Call Test {suffix}", "13800138999", sales_a["id"])
        robot_campaign = expect_status(
            client.post(
                "/api/call-campaigns",
                headers=admin_headers,
                json={
                    "name": f"AI Robot Campaign {suffix}",
                    "scenario": "ai_robot_lead_filter",
                    "customer_ids": [robot_customer["id"]],
                    "assigned_user_id": sales_a["id"],
                },
            ),
            200,
            "create ai robot campaign",
        )
        expect_status(
            client.post(
                f"/api/call-campaigns/{robot_campaign['id']}/ai-robot/start",
                headers={"Authorization": "Bearer invalid-platform-token"},
                json={"provider": "mock", "max_calls": 1},
            ),
            401,
            "reject invalid platform service token",
        )
        robot_launch = expect_status(
            client.post(
                f"/api/call-campaigns/{robot_campaign['id']}/ai-robot/start",
                headers={"Authorization": "Bearer platform-test-service-token"},
                json={"provider": "mock", "max_calls": 1},
            ),
            200,
            "start ai robot campaign with platform service token",
        )
        check(robot_launch["launched"] == 1, f"robot launch should start one call: {robot_launch}")
        robot_call = robot_launch["items"][0]
        check(robot_call["status"] == "initiated", f"robot call should be initiated: {robot_call}")
        check(robot_call["call_attempt_id"], f"robot call should create attempt: {robot_call}")
        platform_headers = {"Authorization": "Bearer platform-test-service-token"}
        platform_provider_status = expect_status(
            client.get("/api/call-provider/status", headers=platform_headers),
            200,
            "platform service reads provider health/configuration status",
        )
        check(platform_provider_status["provider"] == "mock", f"platform provider status mismatch: {platform_provider_status}")
        platform_calls = expect_status(
            client.get("/api/ai-robot-calls", headers=platform_headers, params={"campaign_id": robot_campaign["id"]}),
            200,
            "platform service lists tenant robot calls",
        )
        check(platform_calls["total"] == 1, f"platform robot call list mismatch: {platform_calls}")
        platform_call = expect_status(
            client.get(f"/api/ai-robot-calls/{robot_call['id']}", headers=platform_headers),
            200,
            "platform service reads robot call detail",
        )
        check(platform_call["provider_call_id"] == robot_call["provider_call_id"], f"platform robot detail mismatch: {platform_call}")

        answered_robot = expect_status(
            client.post(
                "/api/ai-robot-calls/webhook/mock",
                json={"provider_call_id": robot_call["provider_call_id"], "event_type": "answered"},
            ),
            200,
            "ai robot answered webhook",
        )
        check(answered_robot["status"] == "answered" and answered_robot["call_status"] == "connected", f"robot answered mismatch: {answered_robot}")

        robot_transcript = (
            "\u673a\u5668\u4eba\uff1a\u60a8\u597d\uff0c\u60f3\u786e\u8ba4\u4e00\u4e0b\u60a8\u662f\u5426\u5173\u6ce8\u62a5\u4ef7\u548c\u90e8\u7f72\u3002\n"
            "\u5ba2\u6237\uff1a\u5bf9\uff0c\u4eca\u5929\u53ef\u4ee5\u628a\u5408\u540c\u548c\u62a5\u4ef7\u53d1\u6211\uff0c"
            "\u4ed8\u6b3e\u6ca1\u95ee\u9898\uff0c\u4e0b\u5468\u5c31\u60f3\u90e8\u7f72\u3002"
        )
        completed_robot = expect_status(
            client.post(
                "/api/ai-robot-calls/webhook/mock",
                json={
                    "provider_call_id": robot_call["provider_call_id"],
                    "event_type": "completed",
                    "duration_seconds": 98,
                    "recording_url": "mock://recordings/ai-robot.wav",
                    "transcript": robot_transcript,
                },
            ),
            200,
            "ai robot completed webhook",
        )
        check(completed_robot["status"] == "completed", f"robot should complete: {completed_robot}")
        check(completed_robot["high_intent"], f"robot should mark high intent: {completed_robot}")
        check(completed_robot["intent_score"] >= 80, f"robot intent score should be high: {completed_robot}")
        check(completed_robot["target_status"] == "callback", f"high intent robot target should wait callback: {completed_robot}")

        robot_attempt = expect_status(
            client.get(f"/api/call-attempts/{robot_call['call_attempt_id']}", headers=sales_headers),
            200,
            "ai robot attempt detail",
        )
        check(robot_attempt["call_mode"] == "ai_robot", f"robot attempt mode mismatch: {robot_attempt}")
        check(robot_attempt["call_recording_id"], f"robot should create recording: {robot_attempt}")
        check(robot_attempt["ai_analysis_id"], f"robot should create analysis: {robot_attempt}")

        robot_followups = expect_status(
            client.get(f"/api/customers/{robot_customer['id']}/followups", headers=sales_headers),
            200,
            "customer followups after ai robot",
        )
        check(any(item["source"] == "ai_robot" for item in robot_followups), f"ai robot should create followup: {robot_followups}")

        upload_detail = expect_status(
            client.get(f"/api/uploads/{analyzed['upload_record_id']}", headers=admin_headers),
            200,
            "call transcript upload detail",
        )
        check(upload_detail["file_type"] == "document", f"manual transcript should be document: {upload_detail}")
        missing_file = client.get(f"/api/uploads/{analyzed['upload_record_id']}/file", headers=admin_headers)
        check(missing_file.status_code == 404, "manual transcript should not pretend to have an original audio file")

        records = expect_status(client.get("/api/call-attempts", headers=admin_headers), 200, "list call attempts")
        check(any(item["id"] == attempt["id"] for item in records["items"]), f"attempt missing from records: {records}")
        overview = expect_status(client.get("/api/call-reports/overview", headers=admin_headers), 200, "overview")
        check(overview["total_attempts"] >= 1, f"overview total attempts mismatch: {overview}")
        check(overview["high_intent_attempts"] >= 1, f"overview high intent mismatch: {overview}")
        check(overview["connect_rate"] > 0, f"overview connect rate mismatch: {overview}")

        expect_status(
            client.delete(f"/api/call-campaigns/{campaign['id']}", headers=admin_headers),
            409,
            "cannot delete running campaign",
        )
        completed = expect_status(
            client.post(f"/api/call-campaigns/{campaign['id']}/complete", headers=admin_headers),
            200,
            "complete campaign",
        )
        check(completed["status"] == "completed", f"campaign should be completed: {completed}")


if __name__ == "__main__":
    try:
        run()
    except TestFailure as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
    print("PASS: call center MVP tests completed")
