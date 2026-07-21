from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.analysis import AIAnalysisResult
from app.models.call_recording import CallRecording
from app.models.followup import Followup
from app.models.upload import UploadRecord
from app.services.ai_service import AIService, build_analysis_result
from app.services.customer_service import find_or_create_customer, update_customer_from_analysis


def process_upload_record(upload_id: int) -> None:
    db: Session = SessionLocal()
    try:
        upload = db.get(UploadRecord, upload_id)
        if upload is None:
            return

        upload.status = "processing"
        db.commit()
        db.refresh(upload)

        payload = AIService().analyze_upload(upload)
        _save_analysis(db, upload, payload)
        upload.status = "completed"
        upload.error_message = None
        db.commit()
    except Exception as exc:
        _mark_upload_failed(db, upload_id, exc)
    finally:
        db.close()


def process_upload_transcript(upload_id: int, transcript: str) -> None:
    db: Session = SessionLocal()
    try:
        upload = db.get(UploadRecord, upload_id)
        if upload is None:
            return
        upload.status = "processing"
        db.commit()
        db.refresh(upload)
        payload = AIService().analyze_text(transcript, "audio")
        _save_analysis(db, upload, payload)
        upload.status = "completed"
        upload.error_message = None
        db.commit()
    except Exception as exc:
        _mark_upload_failed(db, upload_id, exc)
    finally:
        db.close()


def _save_analysis(db: Session, upload: UploadRecord, payload) -> None:
        existing_analysis = db.query(AIAnalysisResult).filter(AIAnalysisResult.upload_record_id == upload.id).first()
        if existing_analysis is not None:
            db.delete(existing_analysis)
            db.flush()
        customer = find_or_create_customer(
            db,
            owner_id=upload.uploader_id,
            tenant_id=upload.tenant_id,
            customer_id=upload.customer_id,
            phone=payload.customer_phone,
            name=payload.customer_name,
            wechat_id=payload.customer_wechat_id,
            wechat_nickname=payload.customer_wechat_nickname,
        )
        upload.customer_id = customer.id
        analysis = build_analysis_result(upload, payload)
        analysis.tenant_id = upload.tenant_id
        analysis.customer_id = customer.id
        db.add(analysis)
        db.flush()
        update_customer_from_analysis(customer, analysis)
        if upload.file_type == "audio":
            recording = db.query(CallRecording).filter(CallRecording.upload_record_id == upload.id).first()
            if recording is not None:
                recording.transcript = analysis.raw_text
                recording.transcription_status = "completed"
                recording.transcription_error = None
        _update_auto_followup_from_analysis(db, upload, analysis)


def _mark_upload_failed(db: Session, upload_id: int, exc: Exception) -> None:
    db.rollback()
    upload = db.get(UploadRecord, upload_id)
    if upload is not None:
        upload.status = "failed"
        upload.error_message = str(exc)
        db.commit()


def _update_auto_followup_from_analysis(db: Session, upload: UploadRecord, analysis: AIAnalysisResult) -> None:
    followup = (
        db.query(Followup)
        .filter(Followup.upload_record_id == upload.id)
        .filter(Followup.source.in_(("material_auto", "call_auto")))
        .order_by(Followup.created_at.desc())
        .first()
    )
    if followup is None:
        followup = Followup(
            tenant_id=upload.tenant_id,
            customer_id=analysis.customer_id,
            user_id=upload.uploader_id,
            content="",
            source="call_auto" if upload.file_type == "audio" else "material_auto",
            upload_record_id=upload.id,
        )
        db.add(followup)

    priority, next_followup_at = _followup_priority(analysis)
    followup.tenant_id = upload.tenant_id
    pieces = [
        f"跟进优先级：{priority}",
        f"AI摘要：{analysis.summary or '未提及'}",
        f"购买意向：{analysis.intent_level or '无法判断'} · {analysis.intent_score or 0}",
        f"客户需求：{analysis.customer_needs or '未提及'}",
        f"客户异议：{analysis.customer_objections or analysis.customer_questions or '未提及'}",
        f"下一步建议：{analysis.next_action or '未提及'}",
    ]
    followup.content = "\n".join(pieces)
    followup.next_followup_at = next_followup_at


def _followup_priority(analysis: AIAnalysisResult) -> tuple[str, datetime]:
    now = datetime.now()
    score = analysis.intent_score or 0
    level = analysis.intent_level or "无法判断"
    if level == "高意向" or score >= 80:
        return "紧急跟进，建议2小时内联系", now + timedelta(hours=2)
    if level == "中意向" or score >= 45:
        return "重点培育，建议明天回访", now + timedelta(days=1)
    if level == "低意向" or score >= 20:
        return "保持触达，建议3天后回访", now + timedelta(days=3)
    return "信息不足，建议补充聊天截图或录音", now + timedelta(days=7)
