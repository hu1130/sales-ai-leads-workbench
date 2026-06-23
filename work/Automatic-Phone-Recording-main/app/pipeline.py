from __future__ import annotations

import logging
import sys
from pathlib import Path

from app import adb_sync, audio_convert, database, local_import, material_import
from app.config import ensure_directories, settings
from app.recording_metadata import RecordingMetadata


def setup_logging() -> None:
    ensure_directories()
    log_file = settings.logs_dir / "sync.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def sync_recordings() -> None:
    if settings.sync_mode == "adb":
        logging.info("Syncing recordings from Android phone through ADB")
        pulled = [
            (remote.source_file, local_path, remote.metadata)
            for remote, local_path in adb_sync.pull_new_recordings()
        ]
    elif settings.sync_mode == "local":
        logging.info("Importing recordings from local inbox: %s", settings.local_inbox_dir)
        pulled = [
            (recording.source_file, recording.local_file, recording.metadata)
            for recording in local_import.import_recordings()
        ]
    else:
        raise RuntimeError("Unsupported SYNC_MODE. Use 'local' or 'adb'.")

    for source_file, local_path, metadata in pulled:
        if not isinstance(metadata, RecordingMetadata):
            metadata = RecordingMetadata()
        database.upsert_pulled_record(
            source_file=source_file,
            local_file=local_path,
            salesperson_id=settings.salesperson_id,
            call_time=metadata.call_time,
            phone_number=metadata.phone_number,
        )
    logging.info("Pulled or found %s recordings", len(pulled))


def process_records() -> None:
    for record in database.iter_records_to_process():
        recording_id_for_sync = record.sales_ai_recording_id
        if settings.enable_sales_ai_upload and record.upload_status != "uploaded":
            try:
                from app.sales_ai_upload import upload_recording_to_sales_ai

                upload_result = upload_recording_to_sales_ai(record)
                database.mark_sales_ai_uploaded(
                    record.source_file,
                    upload_record_id=int(upload_result["upload_record_id"]),
                    recording_id=upload_result.get("recording_id"),
                )
                recording_id_for_sync = upload_result.get("recording_id")
                logging.info(
                    "Uploaded recording to Sales AI: source=%s upload_record_id=%s",
                    record.source_file,
                    upload_result.get("upload_record_id"),
                )
            except Exception as exc:  # noqa: BLE001
                logging.exception("Failed uploading %s to Sales AI", record.source_file)
                database.mark_sales_ai_upload_error(record.source_file, str(exc))

        try:
            logging.info("Processing record %s", record.source_file)
            wav_file = Path(record.wav_file) if record.wav_file else None

            if settings.enable_wav_convert and not wav_file:
                if not record.local_file:
                    raise RuntimeError("Missing local recording path")
                wav_file = audio_convert.convert_to_wav(Path(record.local_file))
                database.mark_wav(record.source_file, wav_file)
            elif not settings.enable_wav_convert:
                logging.info("WAV conversion disabled; leaving original recording as-is")

            transcript = record.transcript
            transcript_file = settings.transcripts_dir / f"{Path(record.source_file).stem}.txt"
            if not transcript and transcript_file.exists():
                transcript = transcript_file.read_text(encoding="utf-8").strip()
                if transcript:
                    database.mark_transcript(record.source_file, transcript)

            if settings.enable_transcribe and not transcript:
                from app.transcribe import transcribe_audio

                audio_input = wav_file or (Path(record.local_file) if record.local_file else None)
                if not audio_input:
                    raise RuntimeError("Missing local audio file path")
                transcript = transcribe_audio(audio_input)
                transcript_file.write_text(transcript, encoding="utf-8")
                database.mark_transcript(record.source_file, transcript)

            if settings.enable_summary and transcript and not record.summary:
                from app.summarize import summarize_transcript

                summary = summarize_transcript(transcript)
                database.mark_summary(record.source_file, summary)

            if transcript and recording_id_for_sync and not record.transcript_synced_at:
                try:
                    from app.sales_ai_upload import submit_transcript_to_sales_ai

                    submit_transcript_to_sales_ai(int(recording_id_for_sync), transcript)
                    database.mark_transcript_synced(record.source_file)
                    logging.info("Synced transcript to Sales AI: %s", record.source_file)
                except Exception as exc:  # noqa: BLE001
                    logging.exception("Failed syncing transcript for %s", record.source_file)
                    database.mark_transcript_sync_error(record.source_file, str(exc))

            if transcript and not settings.enable_summary:
                logging.info("Summary disabled; leaving record transcribed")
            elif not settings.enable_transcribe:
                logging.info("Transcription disabled; leaving record converted")
            elif not settings.enable_summary:
                logging.info("Summary disabled; leaving record transcribed")
            else:
                database.mark_done(record.source_file)

        except Exception as exc:  # noqa: BLE001
            logging.exception("Failed processing %s", record.source_file)
            database.mark_error(record.source_file, str(exc))


def sync_materials() -> None:
    materials = material_import.iter_inbox_materials()
    for path in materials:
        database.register_material(source_file=str(path), local_file=path)
    logging.info("Found %s synced customer images", len(materials))


def process_materials() -> None:
    if not settings.enable_sales_ai_upload:
        return
    from app.sales_ai_upload import upload_material_to_sales_ai

    for material in database.iter_materials_to_upload():
        try:
            result = upload_material_to_sales_ai(material)
            database.mark_material_uploaded(material.source_file, int(result["id"]))
            logging.info(
                "Uploaded customer image to Sales AI: source=%s upload_record_id=%s",
                material.source_file,
                result.get("id"),
            )
        except Exception as exc:  # noqa: BLE001
            logging.exception("Failed uploading customer image %s", material.source_file)
            database.mark_material_upload_error(material.source_file, str(exc))


def run_once() -> None:
    setup_logging()
    ensure_directories()
    database.init_db()
    sync_recordings()
    sync_materials()
    process_records()
    process_materials()


if __name__ == "__main__":
    run_once()
