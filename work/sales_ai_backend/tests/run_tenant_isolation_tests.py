from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_TMP = ROOT / ".test_tmp_tenant"
TEST_DB = TEST_TMP / "sales_ai_tenant_test.db"
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
    os.environ["JWT_SECRET_KEY"] = "tenant-isolation-test-secret-key"
    os.environ["DEFAULT_ADMIN_USERNAME"] = "admin"
    os.environ["DEFAULT_ADMIN_PASSWORD"] = "admin123"
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ["DASHSCOPE_API_KEY"] = ""
    os.environ["ASR_PROVIDER"] = ""
    os.environ["PLATFORM_SERVICE_TOKEN"] = "platform-tenant-test-token"
    os.environ["PLATFORM_TENANT_ID"] = "1"


configure_test_environment()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402


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


def login(client: TestClient, username: str, password: str) -> tuple[dict[str, str], dict]:
    payload = expect_status(
        client.post("/api/auth/login", json={"username": username, "password": password}),
        200,
        f"login {username}",
    )
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload["user"]


def seed_second_tenant_admin() -> tuple[str, str, int]:
    db = SessionLocal()
    try:
        tenant = Tenant(name="测试公司B")
        db.add(tenant)
        db.flush()
        username = "tenant_b_admin"
        password = "admin123"
        db.add(
            User(
                tenant_id=tenant.id,
                username=username,
                password_hash=hash_password(password),
                name="B公司管理员",
                role="admin",
                status="active",
            )
        )
        db.commit()
        return username, password, tenant.id
    finally:
        db.close()


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
    payload = {"name": name, "phone": phone, "source": "tenant-isolation-test"}
    if owner_id is not None:
        payload["owner_id"] = owner_id
        payload["lead_status"] = "assigned"
    return expect_status(client.post("/api/customers", headers=headers, json=payload), 200, f"create customer {name}")


def customer_names(payload: dict) -> set[str]:
    return {item["name"] for item in payload["items"]}


def run() -> None:
    with TestClient(app) as client:
        expect_status(client.get("/health"), 200, "health")

        admin_a_headers, admin_a_user = login(client, "admin", "admin123")
        check(admin_a_user["tenant_id"] == 1, f"default admin tenant mismatch: {admin_a_user}")
        check(admin_a_user["tenant_name"], f"default admin should include tenant name: {admin_a_user}")

        admin_b_username, admin_b_password, tenant_b_id = seed_second_tenant_admin()
        admin_b_headers, admin_b_user = login(client, admin_b_username, admin_b_password)
        check(admin_b_user["tenant_id"] == tenant_b_id, f"tenant B admin tenant mismatch: {admin_b_user}")

        sales_a = create_sales_user(client, admin_a_headers, "tenant_a_sales")
        sales_b = create_sales_user(client, admin_b_headers, "tenant_b_sales")
        customer_a = create_customer(client, admin_a_headers, "A公司客户", "13800138001", sales_a["id"])
        customer_b = create_customer(client, admin_b_headers, "B公司客户", "13800138002", sales_b["id"])

        tenant_b_campaign = expect_status(
            client.post(
                "/api/call-campaigns",
                headers=admin_b_headers,
                json={
                    "name": "B tenant platform boundary campaign",
                    "scenario": "ai_robot_lead_filter",
                    "customer_ids": [customer_b["id"]],
                    "assigned_user_id": sales_b["id"],
                },
            ),
            200,
            "create tenant B AI robot campaign",
        )
        expect_status(
            client.post(
                f"/api/call-campaigns/{tenant_b_campaign['id']}/ai-robot/start",
                headers={"Authorization": "Bearer platform-tenant-test-token"},
                json={"provider": "mock", "max_calls": 1},
            ),
            404,
            "platform service token cannot cross tenant boundary",
        )

        customers_a = expect_status(client.get("/api/customers", headers=admin_a_headers), 200, "tenant A customers")
        customers_b = expect_status(client.get("/api/customers", headers=admin_b_headers), 200, "tenant B customers")
        check("A公司客户" in customer_names(customers_a), f"tenant A customer missing: {customers_a}")
        check("B公司客户" not in customer_names(customers_a), f"tenant A leaked tenant B customer: {customers_a}")
        check("B公司客户" in customer_names(customers_b), f"tenant B customer missing: {customers_b}")
        check("A公司客户" not in customer_names(customers_b), f"tenant B leaked tenant A customer: {customers_b}")

        users_a = expect_status(client.get("/api/users", headers=admin_a_headers), 200, "tenant A users")
        users_b = expect_status(client.get("/api/users", headers=admin_b_headers), 200, "tenant B users")
        check({user["username"] for user in users_a} >= {"admin", "tenant_a_sales"}, f"tenant A users missing: {users_a}")
        check("tenant_b_sales" not in {user["username"] for user in users_a}, f"tenant A leaked tenant B user: {users_a}")
        check("tenant_a_sales" not in {user["username"] for user in users_b}, f"tenant B leaked tenant A user: {users_b}")

        expect_status(client.get(f"/api/customers/{customer_a['id']}", headers=admin_b_headers), 404, "tenant B cannot read tenant A customer")
        expect_status(
            client.post(f"/api/customers/{customer_a['id']}/assign", headers=admin_b_headers, json={"owner_id": sales_b["id"]}),
            404,
            "tenant B cannot assign tenant A customer",
        )

        reassigned = expect_status(
            client.post(f"/api/customers/{customer_a['id']}/assign", headers=admin_a_headers, json={"owner_id": sales_a["id"]}),
            200,
            "tenant A assign customer",
        )
        check(reassigned["owner_id"] == sales_a["id"], f"assign should keep tenant A owner: {reassigned}")
        followups = expect_status(
            client.get(f"/api/customers/{customer_a['id']}/followups", headers=admin_a_headers),
            200,
            "tenant A assignment followups",
        )
        check(any(item["source"] == "assignment" for item in followups), f"assignment followup missing: {followups}")

        sales_a_headers, _ = login(client, "tenant_a_sales", "sales123456")
        sales_customers = expect_status(client.get("/api/customers", headers=sales_a_headers), 200, "sales A customers")
        check("A公司客户" in customer_names(sales_customers), f"sales A should see assigned customer: {sales_customers}")
        expect_status(client.get("/api/users", headers=sales_a_headers), 403, "sales cannot list users")
        expect_status(
            client.post(f"/api/customers/{customer_b['id']}/followups", headers=sales_a_headers, json={"content": "cross tenant"}),
            404,
            "sales A cannot write tenant B followup",
        )


if __name__ == "__main__":
    try:
        run()
    except TestFailure as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1) from exc
    print("PASS: tenant isolation tests completed")
