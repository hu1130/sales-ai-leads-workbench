from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.call_provider import AliyunOutboundBotProvider, CallProviderError  # noqa: E402
from app.services.call_provider_settings import EffectiveCallProviderSettings  # noqa: E402


class TestFailure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise TestFailure(message)


def fake_settings(**overrides) -> EffectiveCallProviderSettings:
    values = {
        "provider": "aliyun",
        "base_url": None,
        "app_id": "6485ff54-c3f5-44d4-9fab-ad1803d2aed6",
        "app_key": "fake-access-key-id",
        "app_secret": "fake-access-key-secret",
        "caller": "30360717",
        "script_id": "c6353512-958e-4430-a377-253a095b6624",
        "webhook_secret": None,
        "timeout": 30.0,
        "enabled": True,
        "source": "environment",
        "updated_at": None,
        "updated_by": None,
    }
    values.update(overrides)
    return EffectiveCallProviderSettings(**values)


class FakeRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeClient:
    def __init__(self):
        self.created: list[FakeRequest] = []
        self.assigned: list[FakeRequest] = []
        self.queried: list[FakeRequest] = []
        self.described: list[FakeRequest] = []
        self.downloaded: list[FakeRequest] = []
        self.cancelled: list[FakeRequest] = []

    def create_job_group(self, request):
        self.created.append(request)
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                http_status_code=200,
                request_id="create-request-id",
                job_group=SimpleNamespace(job_group_id="job-group-id-1"),
            )
        )

    def assign_jobs(self, request):
        self.assigned.append(request)
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                http_status_code=200,
                request_id="assign-request-id",
                job_group_id="job-group-id-1",
                jobs_id=["job-id-1"],
            )
        )

    def query_jobs_with_result(self, request):
        self.queried.append(request)
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                http_status_code=200,
                request_id="query-request-id",
                jobs=SimpleNamespace(
                    list=[
                        SimpleNamespace(
                            id="job-id-1",
                            status="Succeeded",
                            status_name="completed",
                            job_failure_reason=None,
                            latest_task=SimpleNamespace(
                                call_duration=10000,
                                status="SucceededInoInterAction",
                                status_name="connected no interaction",
                                task_end_reason="INO_INTERACTION",
                                has_answered=True,
                                contact=SimpleNamespace(reference_id="sales-ai-10-20-30-test"),
                            ),
                        )
                    ]
                ),
            )
        )

    def describe_job(self, request):
        self.described.append(request)
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                http_status_code=200,
                request_id="describe-request-id",
                job=SimpleNamespace(
                    job_id="job-id-1",
                    status="Succeeded",
                    failure_reason=None,
                    tasks=[
                        SimpleNamespace(
                            task_id="task-id-1",
                            status="SucceededInoInterAction",
                            total_duration=19000,
                            conversation=[
                                SimpleNamespace(speaker="Robot", script="hello from sales ai"),
                                SimpleNamespace(speaker="Contact", script="please send details later"),
                            ],
                        )
                    ],
                ),
            )
        )

    def download_recording(self, request):
        self.downloaded.append(request)
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                http_status_code=200,
                request_id="download-request-id",
                download_params=SimpleNamespace(
                    file_name="task-id-1.wav",
                    signature_url="https://recording.example.com/task-id-1.wav",
                ),
            )
        )

    def cancel_jobs(self, request):
        self.cancelled.append(request)
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                http_status_code=200,
                message="OK",
                request_id="cancel-request-id",
            )
        )


class FakeModels:
    CreateJobGroupRequest = FakeRequest
    AssignJobsRequest = FakeRequest
    QueryJobsWithResultRequest = FakeRequest
    DescribeJobRequest = FakeRequest
    DownloadRecordingRequest = FakeRequest
    CancelJobsRequest = FakeRequest


def run() -> None:
    missing = AliyunOutboundBotProvider(fake_settings(script_id=None))
    try:
        missing.start_ai_robot_call(
            customer_phone="19118776762",
            script_text="test",
            campaign_id=1,
            target_id=2,
            customer_id=3,
        )
    except CallProviderError as exc:
        check("CALL_PROVIDER_SCRIPT_ID" in str(exc), f"missing config error should name script id: {exc}")
    else:
        raise TestFailure("missing script id should fail")

    client = FakeClient()
    provider = AliyunOutboundBotProvider(fake_settings())
    provider._build_client = lambda: (client, FakeModels)  # type: ignore[method-assign]
    result = provider.start_ai_robot_call(
        customer_phone="19118776762",
        script_text="test",
        campaign_id=10,
        target_id=20,
        customer_id=30,
    )

    check(result.provider_call_id == "job-id-1", f"provider_call_id mismatch: {result}")
    check(result.initial_status == "initiated", f"initial status mismatch: {result}")
    check(len(client.created) == 1, f"CreateJobGroup should be called once: {client.created}")
    check(len(client.assigned) == 1, f"AssignJobs should be called once: {client.assigned}")

    create_request = client.created[0]
    check(create_request.instance_id == "6485ff54-c3f5-44d4-9fab-ad1803d2aed6", "instance id mismatch")
    check(create_request.script_id == "c6353512-958e-4430-a377-253a095b6624", "script id mismatch")
    check(create_request.calling_number == ["30360717"], f"caller mismatch: {create_request.calling_number}")
    check(create_request.min_concurrency == 1, f"min concurrency mismatch: {create_request.min_concurrency}")
    check(create_request.priority == "Daily", f"priority mismatch: {create_request.priority}")
    check(create_request.ringing_duration == 25, f"ringing mismatch: {create_request.ringing_duration}")

    assign_request = client.assigned[0]
    check(assign_request.instance_id == create_request.instance_id, "assign instance id mismatch")
    check(assign_request.job_group_id == "job-group-id-1", "assign job group id mismatch")
    check(assign_request.calling_number == ["30360717"], "assign caller mismatch")
    check(assign_request.roster_type == "json", "roster type mismatch")

    jobs = json.loads(assign_request.jobs_json[0])
    contact = jobs["contacts"][0]
    check(contact["phoneNumber"] == "19118776762", f"phone mismatch: {contact}")
    check(contact["referenceId"].startswith("sales-ai-10-20-30-"), f"reference id mismatch: {contact}")
    check(result.raw_payload["job_group_id"] == "job-group-id-1", f"raw payload mismatch: {result.raw_payload}")
    check(result.raw_payload["job_ids"] == ["job-id-1"], f"raw payload job ids mismatch: {result.raw_payload}")

    sync_result = provider.sync_ai_robot_call(
        provider_call_id="job-id-1",
        raw_payload={
            "job_group_id": "job-group-id-1",
            "job_ids": ["job-id-1"],
            "reference_id": "sales-ai-10-20-30-test",
        },
    )
    check(len(client.queried) == 1, f"QueryJobsWithResult should be called once: {client.queried}")
    check(len(client.described) == 1, f"DescribeJob should be called once: {client.described}")
    check(len(client.downloaded) == 1, f"DownloadRecording should be called once: {client.downloaded}")
    check(client.queried[0].job_group_id == "job-group-id-1", "query job group id mismatch")
    check(client.described[0].job_id == "job-id-1", "describe job id mismatch")
    check(client.downloaded[0].task_id == "task-id-1", "download task id mismatch")
    check(sync_result.status == "completed", f"sync status mismatch: {sync_result}")
    check(sync_result.duration_seconds == 10, f"sync duration mismatch: {sync_result}")
    check(sync_result.recording_url == "https://recording.example.com/task-id-1.wav", f"sync recording mismatch: {sync_result}")
    check("Robot: hello from sales ai" in (sync_result.transcript or ""), f"sync transcript mismatch: {sync_result}")

    stop_result = provider.stop_ai_robot_call(
        provider_call_id="job-id-1",
        raw_payload={"job_group_id": "job-group-id-1", "job_ids": ["job-id-1"]},
    )
    check(stop_result.accepted, f"stop request should be accepted: {stop_result}")
    check(stop_result.provider_call_id == "job-id-1", f"stopped job id mismatch: {stop_result}")
    check(stop_result.raw_payload["request_id"] == "cancel-request-id", f"cancel request id mismatch: {stop_result}")
    check(len(client.cancelled) == 1, f"CancelJobs should be called once: {client.cancelled}")
    check(client.cancelled[0].all is False, "CancelJobs must not cancel all tenant jobs")
    check(client.cancelled[0].instance_id == "6485ff54-c3f5-44d4-9fab-ad1803d2aed6", "cancel instance id mismatch")
    check(client.cancelled[0].job_group_id == "job-group-id-1", "cancel job group id mismatch")
    check(client.cancelled[0].job_id == ["job-id-1"], f"cancel job id mismatch: {client.cancelled[0].job_id}")

    stop_without_script = AliyunOutboundBotProvider(fake_settings(script_id=None, caller=None))
    stop_without_script._build_client = lambda: (client, FakeModels)  # type: ignore[method-assign]
    stop_without_script.stop_ai_robot_call(provider_call_id="job-id-2")
    check(client.cancelled[1].job_id == ["job-id-2"], "stop must not depend on launch-only caller/script config")

    check(datetime.now().year >= 2026, "sanity")


if __name__ == "__main__":
    run()
    print("PASS: aliyun provider tests completed")
