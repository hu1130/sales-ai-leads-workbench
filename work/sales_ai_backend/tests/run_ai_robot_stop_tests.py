from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_TMP = ROOT / ".test_tmp_ai_robot_stop"
TEST_DB = TEST_TMP / "sales_ai_robot_stop_test.db"


def configure_test_environment() -> None:
    if TEST_TMP.exists():
        resolved = TEST_TMP.resolve()
        if resolved == ROOT.resolve() or ROOT.resolve() not in resolved.parents:
            raise RuntimeError(f"Refusing to remove unexpected path: {resolved}")
        shutil.rmtree(TEST_TMP)
    TEST_TMP.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
    os.environ["UPLOAD_DIR"] = str(TEST_TMP / "uploads")
    os.environ["JWT_SECRET_KEY"] = "ai-robot-stop-test-secret"
    os.environ["DEFAULT_ADMIN_USERNAME"] = "admin"
    os.environ["DEFAULT_ADMIN_PASSWORD"] = "admin123"
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ["DASHSCOPE_API_KEY"] = ""
    os.environ["ASR_PROVIDER"] = ""
    os.environ["CALL_PROVIDER"] = "mock"
    os.environ["PLATFORM_SERVICE_TOKEN"] = "platform-stop-test-token"
    os.environ["PLATFORM_TENANT_ID"] = "1"


configure_test_environment()
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.ai_robot_call import AiRobotCallEvent, AiRobotCallStopRequest  # noqa: E402


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
    return response.json() if response.content else {}


def run() -> None:
    with TestClient(app) as client:
        openapi = expect_status(client.get("/openapi.json"), 200, "read Provider OpenAPI")
        check(
            "/api/ai-robot-calls/{robot_call_id}/stop" in openapi["paths"],
            "Provider OpenAPI must publish the stop route",
        )
        login = expect_status(
            client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}),
            200,
            "admin login",
        )
        admin_headers = {"Authorization": f"Bearer {login['access_token']}"}
        platform_headers = {"Authorization": "Bearer platform-stop-test-token"}

        customer = expect_status(
            client.post(
                "/api/customers",
                headers=admin_headers,
                json={"name": "Stop Test Customer", "phone": "13800138000", "source": "stop-test"},
            ),
            200,
            "create stop-test customer",
        )
        campaign = expect_status(
            client.post(
                "/api/call-campaigns",
                headers=admin_headers,
                json={
                    "name": "Stop Test Campaign",
                    "scenario": "ai_robot_lead_filter",
                    "customer_ids": [customer["id"]],
                },
            ),
            200,
            "create stop-test campaign",
        )
        launch = expect_status(
            client.post(
                f"/api/call-campaigns/{campaign['id']}/ai-robot/start",
                headers=platform_headers,
                json={"provider": "mock", "max_calls": 1},
            ),
            200,
            "launch stop-test robot call",
        )
        robot_call = launch["items"][0]
        requested_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        payload = {
            "call_task_id": "clt_stop_test_001",
            "provider_task_ref": "ptk_stop_test_001",
            "provider_call_id": robot_call["provider_call_id"],
            "reason_code": "TEST_TEARDOWN",
            "requested_at": requested_at,
            "trace_id": "tr_stop_test_001",
        }
        stop_url = f"/api/ai-robot-calls/{robot_call['id']}/stop"
        stop_headers = {
            **platform_headers,
            "Idempotency-Key": "AI_CALL_STOP:clt_stop_test_001",
        }

        expect_status(
            client.post(stop_url, headers={**admin_headers, "Idempotency-Key": stop_headers["Idempotency-Key"]}, json=payload),
            401,
            "employee admin JWT cannot invoke platform stop",
        )
        expect_status(
            client.post(stop_url, headers={**platform_headers, "Idempotency-Key": "AI_CALL_STOP:clt_wrong"}, json=payload),
            400,
            "reject mismatched idempotency key",
        )
        wrong_mapping = {
            **payload,
            "call_task_id": "clt_wrong_mapping_001",
            "provider_task_ref": "ptk_wrong_mapping_001",
            "provider_call_id": "another-provider-call",
        }
        expect_status(
            client.post(
                stop_url,
                headers={**platform_headers, "Idempotency-Key": "AI_CALL_STOP:clt_wrong_mapping_001"},
                json=wrong_mapping,
            ),
            409,
            "reject unpersisted provider mapping",
        )

        first = expect_status(client.post(stop_url, headers=stop_headers, json=payload), 202, "accept stop request")
        check(first["accepted"] is True, f"stop request should be accepted: {first}")
        check(first["status"] == "CANCEL_REQUESTED", f"stop status mismatch: {first}")
        check(first["robot_call_id"] == robot_call["id"], f"robot call id mismatch: {first}")
        check(first["provider_call_id"] == robot_call["provider_call_id"], f"provider call id mismatch: {first}")
        check(first["receipt_id"].startswith("stp_"), f"receipt id mismatch: {first}")
        check(first["replayed"] is False, f"first stop request must not be marked replayed: {first}")

        unchanged = expect_status(client.get(f"/api/ai-robot-calls/{robot_call['id']}", headers=platform_headers), 200, "read call after stop")
        check(unchanged["status"] == "initiated", f"accepted stop must not pretend final cancellation: {unchanged}")

        replay = expect_status(client.post(stop_url, headers=stop_headers, json=payload), 200, "replay stop request")
        check(replay["replayed"] is True, f"stop replay flag mismatch: {replay}")
        check(replay["receipt_id"] == first["receipt_id"], f"stop replay must return original receipt: {replay}")

        conflict = expect_status(
            client.post(stop_url, headers=stop_headers, json={**payload, "reason_code": "USER_REQUESTED"}),
            409,
            "reject conflicting stop replay",
        )
        check(conflict["detail"] == "IDEMPOTENCY_CONFLICT", f"conflict code mismatch: {conflict}")

        expect_status(
            client.post(
                "/api/ai-robot-calls/webhook/mock",
                json={"provider_call_id": robot_call["provider_call_id"], "event_type": "completed"},
            ),
            200,
            "complete robot call",
        )
        terminal_payload = {
            **payload,
            "call_task_id": "clt_stop_terminal_001",
            "provider_task_ref": "ptk_stop_terminal_001",
            "reason_code": "USER_REQUESTED",
            "trace_id": "tr_stop_terminal_001",
        }
        terminal = expect_status(
            client.post(
                stop_url,
                headers={**platform_headers, "Idempotency-Key": "AI_CALL_STOP:clt_stop_terminal_001"},
                json=terminal_payload,
            ),
            200,
            "return already-terminal stop fact",
        )
        check(terminal["accepted"] is False, f"terminal call must not send another provider stop: {terminal}")
        check(terminal["status"] == "ALREADY_TERMINAL", f"terminal stop status mismatch: {terminal}")

        invalid_utc = {
            **payload,
            "call_task_id": "clt_stop_naive_time_001",
            "provider_task_ref": "ptk_stop_naive_time_001",
            "requested_at": "2026-08-20T00:00:00",
        }
        expect_status(
            client.post(
                stop_url,
                headers={**platform_headers, "Idempotency-Key": "AI_CALL_STOP:clt_stop_naive_time_001"},
                json=invalid_utc,
            ),
            422,
            "reject non-UTC requested_at",
        )

        db = SessionLocal()
        try:
            stops = db.query(AiRobotCallStopRequest).all()
            events = db.query(AiRobotCallEvent).filter(AiRobotCallEvent.event_type == "robot_call_stop_requested").all()
            check(len(stops) == 2, f"expected two persisted stop facts, got {len(stops)}")
            check(len(events) == 2, f"expected two stop audit events, got {len(events)}")
        finally:
            db.close()


if __name__ == "__main__":
    try:
        run()
    except TestFailure as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
    print("PASS: AI robot stop tests completed")
