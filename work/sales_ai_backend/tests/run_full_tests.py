from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_TMP = ROOT / ".test_tmp"
TEST_DB = TEST_TMP / "sales_ai_test.db"
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
    os.environ["JWT_SECRET_KEY"] = "test-secret-key"
    os.environ["DEFAULT_ADMIN_USERNAME"] = "admin"
    os.environ["DEFAULT_ADMIN_PASSWORD"] = "admin123"
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ["DASHSCOPE_API_KEY"] = ""
    os.environ["ASR_PROVIDER"] = ""


configure_test_environment()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models.analysis import AIAnalysisResult  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.services.customer_service import update_customer_from_analysis  # noqa: E402


CASES = [
    (
        "test_high.txt",
        """
        客户姓名：赵总
        电话：13566668888
        公司有18个销售，需要购买AI销售线索分析系统。
        他说预算12万以内可以接受，今天要正式报价和合同模板，明天上午确认付款和上线时间。
        """,
        "高意向",
    ),
    (
        "test_mid.txt",
        """
        客户姓名：刘经理
        电话：13755556666
        想了解销售资料上传、客户跟进记录、老板查看销售线索。
        目前还在对比两家供应商，希望先安排演示，价格合适再考虑。
        """,
        "中意向",
    ),
    (
        "test_low.txt",
        """
        客户姓名：周先生
        电话：13922223333
        只是先看看产品资料，暂时没有预算，也没有明确上线时间。
        后面有需要再联系。
        """,
        "低意向",
    ),
    (
        "test_none.txt",
        """
        客户姓名：孙女士
        电话：13611112222
        今年不考虑购买，已经明确说暂时不需要，明年再说。
        """,
        "暂无意向",
    ),
]


class TestFailure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise TestFailure(message)


def login(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    check(response.status_code == 200, f"admin login failed: {response.status_code} {response.text}")
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload_text(client: TestClient, headers: dict[str, str], filename: str, text: str) -> dict:
    files = {"file": (filename, text.encode("utf-8"), "text/plain")}
    response = client.post("/api/uploads", headers=headers, files=files)
    check(response.status_code == 200, f"upload failed for {filename}: {response.status_code} {response.text}")
    upload_id = response.json()["id"]
    detail = client.get(f"/api/uploads/{upload_id}", headers=headers)
    check(detail.status_code == 200, f"upload detail failed for {filename}: {detail.status_code} {detail.text}")
    payload = detail.json()
    check(payload["status"] == "completed", f"{filename} was not completed: {payload}")
    check(payload["analysis"] is not None, f"{filename} has no analysis")
    return payload


def run() -> None:
    corrupt_customer = Customer(name="????", phone="13800000000")
    recognized_analysis = AIAnalysisResult(
        customer_name="张先生",
        intent_level="高意向",
        intent_score=85,
        summary="客户计划本周签合同。",
    )
    update_customer_from_analysis(corrupt_customer, recognized_analysis)
    check(corrupt_customer.name == "张先生", "recognized name should replace a corrupt placeholder")

    with TestClient(app) as client:
        health = client.get("/health")
        check(health.status_code == 200 and health.json()["status"] == "ok", "health check failed")

        bad_login = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        check(bad_login.status_code == 401, "bad password should be rejected")

        headers = login(client)

        user_payload = {
            "username": "sales01",
            "password": "sales123456",
            "name": "测试销售",
            "phone": "13811112222",
            "role": "sales",
        }
        user_response = client.post("/api/users", headers=headers, json=user_payload)
        check(user_response.status_code == 200, f"create user failed: {user_response.status_code} {user_response.text}")
        users_response = client.get("/api/users", headers=headers)
        check(users_response.status_code == 200 and users_response.json(), "list users failed")
        sales_login = client.post("/api/auth/login", json={"username": "sales01", "password": "sales123456"})
        check(sales_login.status_code == 200, f"sales login failed: {sales_login.text}")
        sales_headers = {"Authorization": f"Bearer {sales_login.json()['access_token']}"}
        sales_dashboard = client.get("/api/dashboard/stats", headers=sales_headers)
        check(sales_dashboard.status_code == 200, f"sales dashboard failed: {sales_dashboard.text}")

        recognition = client.get("/api/ai/recognition/status", headers=headers)
        check(recognition.status_code == 200, f"recognition status failed: {recognition.text}")
        recognition_payload = recognition.json()
        check("ocr" in recognition_payload and "asr" in recognition_payload, "recognition status shape failed")

        uploaded = []
        for filename, text, expected_level in CASES:
            detail = upload_text(client, headers, filename, text)
            analysis = detail["analysis"]
            actual_level = analysis["intent_level"]
            check(
                actual_level == expected_level,
                f"{filename} expected {expected_level}, got {actual_level}: {analysis}",
            )
            uploaded.append(detail)

        unknown_files = {"file": ("empty_photo.png", b"not a real image but enough for fallback", "image/png")}
        unknown_response = client.post("/api/uploads", headers=headers, files=unknown_files)
        check(unknown_response.status_code == 200, f"unknown upload failed: {unknown_response.text}")
        unknown_id = unknown_response.json()["id"]
        unknown_detail = client.get(f"/api/uploads/{unknown_id}", headers=headers).json()
        check(unknown_detail["analysis"]["intent_level"] == "无法判断", "image fallback should be unable to judge")
        check("未能读取图片内容" in unknown_detail["analysis"]["raw_text"], "image fallback should explain missing OCR text")
        check(len(unknown_detail["file_sha256"]) == 64, "uploaded file should have sha256")
        duplicate_unknown = client.post("/api/uploads", headers=headers, files=unknown_files)
        check(duplicate_unknown.status_code == 200, f"duplicate upload failed: {duplicate_unknown.text}")
        duplicate_payload = duplicate_unknown.json()
        check(duplicate_payload["duplicate"] is True, "duplicate upload should be flagged")
        check(duplicate_payload["id"] == unknown_id, "duplicate upload should return existing upload id")
        original_file = client.get(f"/api/uploads/{unknown_id}/file", headers=headers)
        check(original_file.status_code == 200, f"original image failed: {original_file.status_code}")
        check(original_file.content == unknown_files["file"][1], "original image bytes changed")
        check(original_file.headers["content-type"].startswith("image/png"), "original image content type failed")

        for level in ["高意向", "中意向", "低意向", "暂无意向", "无法判断"]:
            response = client.get("/api/leads", headers=headers, params={"intent_level": level, "page_size": 50})
            check(response.status_code == 200, f"leads failed for {level}: {response.status_code} {response.text}")
            check(response.json()["total"] >= 1, f"leads should include at least one {level}")

        customers = client.get("/api/customers", headers=headers, params={"page_size": 50})
        check(customers.status_code == 200, f"customers list failed: {customers.text}")
        customer_items = customers.json()["items"]
        check(len(customer_items) >= 5, "customers were not created from uploads")

        duplicate_a = client.post(
            "/api/customers",
            headers=headers,
            json={"name": "重复客户A", "phone": "13999990000", "demand_summary": "第一次登记"},
        )
        duplicate_b = client.post(
            "/api/customers",
            headers=headers,
            json={"name": "重复客户B", "phone": "13999990000", "demand_summary": "第二次登记", "intent_level": "高意向"},
        )
        check(duplicate_a.status_code == 200 and duplicate_b.status_code == 200, "manual duplicate customers should be created")
        duplicate_groups = client.get("/api/customers/duplicates", headers=headers)
        check(duplicate_groups.status_code == 200, f"duplicate customers failed: {duplicate_groups.text}")
        check(
            any(group["match_value"] == "13999990000" for group in duplicate_groups.json()["items"]),
            "duplicate phone group should be listed",
        )
        merge_response = client.post(
            f"/api/customers/{duplicate_a.json()['id']}/merge",
            headers=headers,
            json={"source_customer_id": duplicate_b.json()["id"]},
        )
        check(merge_response.status_code == 200, f"customer merge failed: {merge_response.status_code} {merge_response.text}")
        source_after_merge = client.get(f"/api/customers/{duplicate_b.json()['id']}", headers=headers)
        check(source_after_merge.status_code == 404, "merged source customer should be removed")

        high_customer = next(item for item in customer_items if item["intent_level"] == "高意向")
        customer_id = high_customer["id"]

        files_before_forbidden_upload = {path.name for path in TEST_UPLOADS.iterdir() if path.is_file()}
        forbidden_upload = client.post(
            "/api/uploads",
            headers=sales_headers,
            files={"file": ("forbidden.txt", b"must not be persisted", "text/plain")},
            data={"customer_id": str(customer_id)},
        )
        check(forbidden_upload.status_code == 403, "sales user should not upload to another owner's customer")
        files_after_forbidden_upload = {path.name for path in TEST_UPLOADS.iterdir() if path.is_file()}
        check(
            files_after_forbidden_upload == files_before_forbidden_upload,
            "forbidden upload should not leave an orphaned file",
        )

        records = client.get(f"/api/customers/{customer_id}/records", headers=headers)
        check(records.status_code == 200 and records.json(), "customer records failed")

        followup_payload = {"content": "测试补充备注", "next_followup_at": None}
        followup = client.post(f"/api/customers/{customer_id}/followups", headers=headers, json=followup_payload)
        check(followup.status_code == 200, f"manual followup failed: {followup.status_code} {followup.text}")
        followups = client.get(f"/api/customers/{customer_id}/followups", headers=headers)
        check(followups.status_code == 200 and followups.json()[0]["source"] == "manual_note", "manual followup source failed")

        call_files = {"file": ("call.mp3", b"fake call audio bytes", "audio/mpeg")}
        call_data = {"callee_phone": "13833334444", "sales_username": "sales01"}
        call = client.post("/api/call-recordings", headers=headers, files=call_files, data=call_data)
        check(call.status_code == 200, f"call recording upload failed: {call.status_code} {call.text}")
        call_payload = call.json()
        duplicate_call = client.post("/api/call-recordings", headers=headers, files=call_files, data=call_data)
        check(duplicate_call.status_code == 200, f"duplicate call upload failed: {duplicate_call.text}")
        check(duplicate_call.json()["duplicate"] is True, "duplicate call recording should be flagged")
        check(
            duplicate_call.json()["upload_record_id"] == call_payload["upload_record_id"],
            "duplicate call recording should reuse existing upload",
        )
        transcript = client.post(
            f"/api/call-recordings/{call_payload['recording_id']}/transcript",
            headers=headers,
            json={
                "transcript": (
                    "客户姓名：赵总。客户明确询问正式报价、合同、付款方式和下周上线时间，"
                    "希望今天发送合同，明天电话确认。"
                )
            },
        )
        check(transcript.status_code == 200, f"transcript callback failed: {transcript.status_code} {transcript.text}")
        call_upload = client.get(f"/api/uploads/{call_payload['upload_record_id']}", headers=headers)
        check(call_upload.status_code == 200, "call upload detail failed after transcript")
        check(call_upload.json()["analysis"]["intent_level"] == "高意向", "call transcript was not analyzed")
        call_customer_id = client.get(f"/api/uploads/{call_payload['upload_record_id']}", headers=headers).json()["customer_id"]
        call_followups = client.get(f"/api/customers/{call_customer_id}/followups", headers=headers).json()
        check(any(item["source"] == "call_auto" for item in call_followups), "call_auto followup was not created")

        dashboard = client.get("/api/dashboard/stats", headers=headers)
        check(dashboard.status_code == 200, f"dashboard failed: {dashboard.status_code} {dashboard.text}")
        stats = dashboard.json()
        check(stats["total_customers"] >= 5 and stats["total_uploads"] >= 6, f"dashboard stats look wrong: {stats}")

        reanalyze_id = uploaded[0]["id"]
        reanalyze = client.post(f"/api/uploads/{reanalyze_id}/reanalyze", headers=headers)
        check(reanalyze.status_code == 200, f"reanalyze failed: {reanalyze.status_code} {reanalyze.text}")


if __name__ == "__main__":
    try:
        run()
    except TestFailure as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
    print("PASS: backend full flow tests completed")
