from pydantic import BaseModel


class CallRecordingUploadResponse(BaseModel):
    recording_id: int
    upload_record_id: int
    status: str
    duplicate: bool = False
    duplicate_of_id: int | None = None


class CallTranscriptUpdate(BaseModel):
    transcript: str


class CallTranscriptResponse(BaseModel):
    recording_id: int
    upload_record_id: int
    transcription_status: str
