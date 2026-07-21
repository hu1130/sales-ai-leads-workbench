from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import re

from app.core.config import get_settings
from app.services.call_provider_settings import EffectiveCallProviderSettings, get_effective_call_provider_settings


@dataclass
class CallbackLaunchResult:
    provider_call_id: str
    initial_status: str = "initiated"
    raw_payload: dict = field(default_factory=dict)


@dataclass
class AiRobotLaunchResult:
    provider_call_id: str
    initial_status: str = "initiated"
    raw_payload: dict = field(default_factory=dict)


@dataclass
class AiRobotSyncResult:
    provider_call_id: str
    status: str
    duration_seconds: int | None = None
    recording_url: str | None = None
    transcript: str | None = None
    failure_reason: str | None = None
    raw_payload: dict = field(default_factory=dict)


class CallProviderError(RuntimeError):
    pass


class BaseCallProvider:
    name = "base"

    def start_callback(
        self,
        *,
        sales_phone: str,
        customer_phone: str,
        sales_id: int,
        customer_id: int,
    ) -> CallbackLaunchResult:
        raise NotImplementedError

    def start_ai_robot_call(
        self,
        *,
        customer_phone: str,
        script_text: str,
        campaign_id: int,
        target_id: int,
        customer_id: int,
    ) -> AiRobotLaunchResult:
        raise NotImplementedError

    def sync_ai_robot_call(
        self,
        *,
        provider_call_id: str,
        raw_payload: dict | None = None,
    ) -> AiRobotSyncResult:
        raise NotImplementedError


class MockCallProvider(BaseCallProvider):
    name = "mock"

    def start_callback(
        self,
        *,
        sales_phone: str,
        customer_phone: str,
        sales_id: int,
        customer_id: int,
    ) -> CallbackLaunchResult:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        provider_call_id = f"mock-callback-{customer_id}-{sales_id}-{stamp}"
        return CallbackLaunchResult(
            provider_call_id=provider_call_id,
            initial_status="initiated",
            raw_payload={
                "provider": self.name,
                "sales_phone": _mask_phone(sales_phone),
                "customer_phone": _mask_phone(customer_phone),
            },
        )

    def start_ai_robot_call(
        self,
        *,
        customer_phone: str,
        script_text: str,
        campaign_id: int,
        target_id: int,
        customer_id: int,
    ) -> AiRobotLaunchResult:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        provider_call_id = f"mock-robot-{campaign_id}-{target_id}-{customer_id}-{stamp}"
        return AiRobotLaunchResult(
            provider_call_id=provider_call_id,
            initial_status="initiated",
            raw_payload={
                "provider": self.name,
                "customer_phone": _mask_phone(customer_phone),
                "campaign_id": campaign_id,
                "target_id": target_id,
                "script_preview": (script_text or "")[:120],
            },
        )

    def sync_ai_robot_call(
        self,
        *,
        provider_call_id: str,
        raw_payload: dict | None = None,
    ) -> AiRobotSyncResult:
        return AiRobotSyncResult(
            provider_call_id=provider_call_id,
            status="completed",
            duration_seconds=30,
            recording_url=f"mock://recordings/{provider_call_id}.wav",
            transcript="Robot: mock ai robot call completed.\nContact: interested in a follow-up.",
            raw_payload={"provider": self.name, "source": "mock_sync", "launch_raw_payload": raw_payload or {}},
        )


class AliyunOutboundBotProvider(BaseCallProvider):
    name = "aliyun"

    def __init__(self, settings: EffectiveCallProviderSettings | None = None):
        self.settings = settings or get_effective_call_provider_settings()

    def start_callback(
        self,
        *,
        sales_phone: str,
        customer_phone: str,
        sales_id: int,
        customer_id: int,
    ) -> CallbackLaunchResult:
        raise CallProviderError("aliyun outboundbot only supports AI robot outbound calls in this integration.")

    def start_ai_robot_call(
        self,
        *,
        customer_phone: str,
        script_text: str,
        campaign_id: int,
        target_id: int,
        customer_id: int,
    ) -> AiRobotLaunchResult:
        self._ensure_configured()
        client, models = self._build_client()

        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        reference_id = f"sales-ai-{campaign_id}-{target_id}-{customer_id}-{stamp}"
        group_name = f"sales-ai-{campaign_id}-{target_id}-{stamp}"
        strategy_json = _json_dumps(
            {
                "repeatBy": "Once",
                "maxAttemptsPerDay": "1",
                "minAttemptInterval": "10",
                "routingStrategy": "LocalProvinceFirst",
                "workingTime": [{"beginTime": "09:00:00", "endTime": "20:00:00"}],
                "repeatable": False,
            }
        )
        recall_strategy_json = _json_dumps(
            {
                "emptyNumberIgnore": True,
                "inArrearsIgnore": True,
                "outOfServiceIgnore": True,
            }
        )

        try:
            create_response = client.create_job_group(
                models.CreateJobGroupRequest(
                    instance_id=self.settings.app_id,
                    script_id=self.settings.script_id,
                    job_group_name=group_name,
                    job_group_description=f"Sales AI robot call for customer {customer_id}",
                    calling_number=[self.settings.caller],
                    recall_calling_number=[self.settings.caller],
                    min_concurrency=1,
                    priority="Daily",
                    ringing_duration=25,
                    strategy_json=strategy_json,
                    recall_strategy_json=recall_strategy_json,
                )
            )
        except Exception as exc:  # SDK exceptions vary by transport layer.
            raise CallProviderError(f"aliyun CreateJobGroup failed: {_sdk_error_message(exc)}") from exc

        create_body = getattr(create_response, "body", None)
        if not _response_ok(create_body):
            raise CallProviderError(f"aliyun CreateJobGroup failed: {_response_message(create_body)}")
        job_group = getattr(create_body, "job_group", None)
        job_group_id = getattr(job_group, "job_group_id", None)
        if not job_group_id:
            raise CallProviderError("aliyun CreateJobGroup did not return JobGroupId")

        jobs_json = [
            _json_dumps(
                {
                    "extras": [
                        {"key": "CampaignId", "value": str(campaign_id)},
                        {"key": "TargetId", "value": str(target_id)},
                        {"key": "CustomerId", "value": str(customer_id)},
                    ],
                    "contacts": [
                        {
                            "phoneNumber": customer_phone,
                            "name": f"客户{customer_id}",
                            "referenceId": reference_id,
                            "role": "客户",
                        }
                    ],
                }
            )
        ]
        try:
            assign_response = client.assign_jobs(
                models.AssignJobsRequest(
                    instance_id=self.settings.app_id,
                    job_group_id=job_group_id,
                    calling_number=[self.settings.caller],
                    jobs_json=jobs_json,
                    roster_type="json",
                    is_asynchrony=False,
                    strategy_json=strategy_json,
                )
            )
        except Exception as exc:
            raise CallProviderError(f"aliyun AssignJobs failed: {_sdk_error_message(exc)}") from exc

        assign_body = getattr(assign_response, "body", None)
        if not _response_ok(assign_body):
            raise CallProviderError(f"aliyun AssignJobs failed: {_response_message(assign_body)}")
        job_ids = getattr(assign_body, "jobs_id", None) or []
        provider_call_id = job_ids[0] if job_ids else job_group_id
        return AiRobotLaunchResult(
            provider_call_id=provider_call_id,
            initial_status="initiated",
            raw_payload={
                "provider": self.name,
                "instance_id": self.settings.app_id,
                "script_id": self.settings.script_id,
                "caller": self.settings.caller,
                "customer_phone": _mask_phone(customer_phone),
                "campaign_id": campaign_id,
                "target_id": target_id,
                "customer_id": customer_id,
                "job_group_id": job_group_id,
                "job_ids": job_ids,
                "reference_id": reference_id,
                "create_request_id": getattr(create_body, "request_id", None),
                "assign_request_id": getattr(assign_body, "request_id", None),
            },
        )

    def sync_ai_robot_call(
        self,
        *,
        provider_call_id: str,
        raw_payload: dict | None = None,
    ) -> AiRobotSyncResult:
        self._ensure_configured()
        client, models = self._build_client()
        launch_payload = raw_payload or {}
        job_group_id = _clean_text(launch_payload.get("job_group_id"))
        job_id = _clean_text(provider_call_id) or _first_clean_text(launch_payload.get("job_ids"))
        reference_id = _clean_text(launch_payload.get("reference_id"))

        query_body = None
        query_job = None
        query_task = None
        if job_group_id:
            try:
                query_response = client.query_jobs_with_result(
                    models.QueryJobsWithResultRequest(
                        instance_id=self.settings.app_id,
                        job_group_id=job_group_id,
                        page_number=1,
                        page_size=50,
                    )
                )
            except Exception as exc:
                raise CallProviderError(f"aliyun QueryJobsWithResult failed: {_sdk_error_message(exc)}") from exc

            query_body = getattr(query_response, "body", None)
            if not _response_ok(query_body):
                raise CallProviderError(f"aliyun QueryJobsWithResult failed: {_response_message(query_body)}")
            query_job = _pick_aliyun_query_job(_aliyun_query_jobs(query_body), job_id, reference_id)
            if query_job is not None:
                job_id = _clean_text(getattr(query_job, "id", None)) or job_id
                query_task = getattr(query_job, "latest_task", None)

        describe_body = None
        described_job = None
        if job_id:
            try:
                describe_response = client.describe_job(
                    models.DescribeJobRequest(
                        instance_id=self.settings.app_id,
                        job_id=job_id,
                        with_script=False,
                    )
                )
            except Exception as exc:
                raise CallProviderError(f"aliyun DescribeJob failed: {_sdk_error_message(exc)}") from exc

            describe_body = getattr(describe_response, "body", None)
            if not _response_ok(describe_body):
                raise CallProviderError(f"aliyun DescribeJob failed: {_response_message(describe_body)}")
            described_job = getattr(describe_body, "job", None)

        task = _pick_aliyun_task(getattr(described_job, "tasks", None), query_task)
        aliyun_status = (
            _clean_text(getattr(task, "status", None))
            or _clean_text(getattr(query_task, "status", None))
            or _clean_text(getattr(query_job, "status", None))
            or _clean_text(getattr(described_job, "status", None))
            or "Executing"
        )
        task_id = _clean_text(getattr(task, "task_id", None))
        duration_seconds = _aliyun_duration_seconds(query_task, task)
        transcript = _aliyun_transcript(task)
        failure_reason = _aliyun_failure_reason(query_job, query_task, described_job, task)
        recording_url = None
        download_body = None
        download_error = None

        if task_id and _aliyun_status_terminal(aliyun_status):
            try:
                download_response = client.download_recording(
                    models.DownloadRecordingRequest(
                        instance_id=self.settings.app_id,
                        task_id=task_id,
                        need_voice_slice_recording=False,
                    )
                )
                download_body = getattr(download_response, "body", None)
                if _response_ok(download_body):
                    download_params = getattr(download_body, "download_params", None)
                    recording_url = _clean_text(getattr(download_params, "signature_url", None))
                else:
                    download_error = _response_message(download_body)
            except Exception as exc:
                download_error = _sdk_error_message(exc)

        sync_payload = {
            "provider": self.name,
            "job_group_id": job_group_id,
            "job_id": job_id,
            "task_id": task_id,
            "reference_id": reference_id,
            "aliyun_status": aliyun_status,
            "query_result": _model_to_map(query_body),
            "describe_result": _model_to_map(describe_body),
            "download_result": _model_to_map(download_body),
            "download_error": download_error,
        }
        return AiRobotSyncResult(
            provider_call_id=job_id or provider_call_id,
            status=_aliyun_status_to_robot_status(aliyun_status, query_task, described_job),
            duration_seconds=duration_seconds,
            recording_url=recording_url,
            transcript=transcript,
            failure_reason=failure_reason,
            raw_payload=sync_payload,
        )

    def _ensure_configured(self) -> None:
        missing = []
        if not self.settings.app_id:
            missing.append("CALL_PROVIDER_APP_ID/InstanceId")
        if not self.settings.app_key:
            missing.append("CALL_PROVIDER_APP_KEY/AccessKeyId")
        if not self.settings.app_secret:
            missing.append("CALL_PROVIDER_APP_SECRET/AccessKeySecret")
        if not self.settings.caller:
            missing.append("CALL_PROVIDER_CALLER")
        if not self.settings.script_id:
            missing.append("CALL_PROVIDER_SCRIPT_ID/SceneId")
        if not self.settings.enabled:
            missing.append("enabled")
        if missing:
            raise CallProviderError("aliyun outboundbot configuration is incomplete: " + ", ".join(missing))

    def _build_client(self):
        try:
            from alibabacloud_outboundbot20191226.client import Client as OutboundBotClient
            from alibabacloud_outboundbot20191226 import models
            from alibabacloud_tea_openapi import utils_models as open_api_models
        except ImportError as exc:
            raise CallProviderError("aliyun outboundbot SDK is not installed; run pip install -r requirements.txt") from exc

        config = open_api_models.Config(
            access_key_id=self.settings.app_key,
            access_key_secret=self.settings.app_secret,
            region_id="cn-shanghai",
        )
        endpoint = _aliyun_endpoint(self.settings.base_url)
        if endpoint:
            config.endpoint = endpoint
        return OutboundBotClient(config), models


def get_call_provider(provider: str | None, settings: EffectiveCallProviderSettings | None = None) -> BaseCallProvider:
    provider_name = (provider or get_settings().call_provider or "mock").strip().lower()
    if provider_name == "mock":
        return MockCallProvider()
    if provider_name in {"aliyun", "aliyun_outboundbot", "aliyun-outboundbot"}:
        return AliyunOutboundBotProvider(settings)
    raise CallProviderError(f"Call provider '{provider_name}' is not configured yet.")


def _mask_phone(phone: str) -> str:
    if len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


def _json_dumps(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _response_ok(body) -> bool:
    if body is None:
        return False
    success = getattr(body, "success", None)
    code = str(getattr(body, "code", "") or "").upper()
    status_code = getattr(body, "http_status_code", None)
    return bool(success) or code == "OK" or status_code == 200


def _response_message(body) -> str:
    if body is None:
        return "empty response"
    message = getattr(body, "message", None) or "unknown error"
    code = getattr(body, "code", None)
    request_id = getattr(body, "request_id", None)
    pieces = [str(message)]
    if code:
        pieces.append(f"code={code}")
    if request_id:
        pieces.append(f"request_id={request_id}")
    return ", ".join(pieces)


def _sdk_error_message(exc: Exception) -> str:
    for attr in ("message", "msg", "code"):
        value = getattr(exc, attr, None)
        if value:
            return str(value)
    return str(exc) or exc.__class__.__name__


def _aliyun_endpoint(value: str | None) -> str | None:
    if not value:
        return None
    endpoint = value.strip()
    endpoint = re.sub(r"^https?://", "", endpoint, flags=re.IGNORECASE)
    endpoint = endpoint.strip("/")
    return endpoint or None


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_clean_text(value) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = _clean_text(item)
            if text:
                return text
    return _clean_text(value)


def _aliyun_query_jobs(body) -> list:
    jobs = getattr(body, "jobs", None)
    return list(getattr(jobs, "list", None) or [])


def _pick_aliyun_query_job(jobs: list, job_id: str | None, reference_id: str | None):
    if not jobs:
        return None
    for item in jobs:
        if job_id and _clean_text(getattr(item, "id", None)) == job_id:
            return item
    for item in jobs:
        contact = getattr(getattr(item, "latest_task", None), "contact", None)
        if reference_id and _clean_text(getattr(contact, "reference_id", None)) == reference_id:
            return item
    return jobs[0]


def _pick_aliyun_task(tasks, query_task):
    task_list = list(tasks or [])
    if not task_list:
        return None
    query_status = _clean_text(getattr(query_task, "status", None))
    if query_status:
        for task in reversed(task_list):
            if _clean_text(getattr(task, "status", None)) == query_status:
                return task
    return task_list[-1]


def _aliyun_duration_seconds(query_task, task) -> int | None:
    call_duration = getattr(query_task, "call_duration", None)
    if call_duration is not None:
        return _milliseconds_to_seconds(int(call_duration))
    for attr in ("total_duration", "duration"):
        value = getattr(task, attr, None)
        if value is None:
            continue
        value = int(value)
        return _milliseconds_to_seconds(value) if value > 1000 else max(0, value)
    return None


def _milliseconds_to_seconds(value: int) -> int:
    return max(0, (value + 999) // 1000)


def _aliyun_transcript(task) -> str | None:
    lines = []
    for item in list(getattr(task, "conversation", None) or []):
        text = _clean_text(getattr(item, "script", None))
        if not text:
            continue
        speaker = _clean_text(getattr(item, "speaker", None)) or "Unknown"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines) or None


def _aliyun_failure_reason(query_job, query_task, described_job, task) -> str | None:
    pieces = [
        _clean_text(getattr(query_task, "status_name", None)),
        _clean_text(getattr(query_task, "task_end_reason", None)),
        _clean_text(getattr(task, "end_reason", None)),
        _clean_text(getattr(query_job, "job_failure_reason", None)),
        _clean_text(getattr(described_job, "failure_reason", None)),
    ]
    return " / ".join(dict.fromkeys(piece for piece in pieces if piece)) or None


def _aliyun_status_terminal(status: str | None) -> bool:
    normalized = _clean_text(status) or ""
    return normalized not in {"Scheduling", "Executing", "Drafted", "Paused"}


def _aliyun_status_to_robot_status(status: str | None, query_task, described_job) -> str:
    normalized = _clean_text(status) or ""
    if normalized in {"Scheduling", "Executing", "Drafted"}:
        return "dialing"
    if normalized == "Busy":
        return "busy"
    if normalized in {"NoAnswer", "PoweredOff", "OutOfService", "NotConnected"}:
        return "no_answer"
    if normalized in {"NotExist", "EmptyNumber", "OutOfServiceNoCall"}:
        return "empty_number"
    if normalized.startswith("Succeeded"):
        return "completed"
    if normalized == "Succeeded":
        return "completed"
    if normalized == "Paused":
        return "dialing"
    if bool(getattr(query_task, "has_answered", False)):
        return "completed"
    if _clean_text(getattr(described_job, "status", None)) == "Succeeded":
        return "completed"
    return "failed"


def _model_to_map(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_model_to_map(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _model_to_map(item) for key, item in value.items()}
    to_map = getattr(value, "to_map", None)
    if callable(to_map):
        try:
            return to_map()
        except Exception:
            pass
    return str(value)
