# Sales Audio Sync

Local MVP for syncing Android work-phone call recordings, transcribing them, generating follow-up summaries, and storing the results in SQLite.

## What This First Version Does

- Checks whether an Android phone is connected through ADB.
- Imports call recordings from a local sync folder.
- Detects synced WeChat screenshots and uploads them for OCR and intent analysis.
- Optionally lists and pulls call recording files through ADB.
- Converts recordings to 16 kHz mono WAV with FFmpeg.
- Optionally transcribes audio with FunASR.
- Optionally summarizes transcripts with a local Ollama model.
- Stores file paths, transcript text, summary text, and processing status in SQLite.

## Required Tools

- Python 3.10 or 3.11
- Android Platform Tools / ADB
- FFmpeg
- Optional: FunASR for speech-to-text
- Optional: Ollama for local summary generation

## Project Layout

```text
sales-audio-sync/
  app/
    config.py
    adb_sync.py
    audio_convert.py
    transcribe.py
    summarize.py
    database.py
    pipeline.py
    scheduler.py
  data/
    recordings/
    wav/
    transcripts/
  db/
    sales_audio.db
  logs/
  requirements.txt
```

## Quick Start

1. Install Python dependencies:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. Connect an Android work phone and verify ADB:

```powershell
adb devices
```

The recommended Huawei Wi-Fi sync mode does not need ADB. Put Syncthing or FolderSync output files here:

```text
data/inbox/
```

For the first deployment, prefer this path:

```text
Android call recorder
  -> Syncthing / FolderSync on the phone
  -> data/inbox on this PC
  -> python -m app.pipeline
```

WeChat long screenshots can use the same inbox. Share the phone screenshot
folder to `data/inbox/wechat` and the realtime watcher will upload supported
JPG, PNG, WebP, or BMP files once each. The backend then performs OCR and
intent analysis using its configured DashScope and DeepSeek keys.

For Huawei Mate 50 Pro, first discover the actual recording folder:

```powershell
.venv\Scripts\python.exe -m app.discover_phone
```

3. Edit environment variables if needed:

```powershell
$env:PHONE_RECORDING_DIRS="/sdcard/Recordings/Call,/sdcard/MIUI/sound_recorder/call_rec"
$env:SALESPERSON_ID="sales_001"
```

4. Check the local runtime:

```powershell
.venv\Scripts\python.exe -m app.doctor
```

5. Run one sync job:

```powershell
.venv\Scripts\python.exe -m app.pipeline
```

6. Run the nightly scheduler:

```powershell
.venv\Scripts\python.exe -m app.scheduler
```

## Important Config Variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `SYNC_MODE` | `local` | `local` imports from a synced PC folder; `adb` pulls from Android. |
| `LOCAL_INBOX_DIR` | `data/inbox` | Folder where Syncthing/FolderSync writes phone recordings. |
| `INBOX_STABLE_SECONDS` | `10` | Skip new inbox files until they have stopped changing for this many seconds. |
| `SALESPERSON_ID` | `sales_001` | Salesperson or phone owner ID. |
| `PHONE_RECORDING_DIRS` | common Android paths | Comma-separated phone folders to scan. |
| `SYNC_LOOKBACK_DAYS` | `2` | Pull files modified in the last N days. |
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | Local Ollama endpoint. |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Summary model name. |
| `ENABLE_TRANSCRIBE` | `0` | Set to `1` to enable FunASR transcription. |
| `FUNASR_RUNTIME` | `auto` | Use `docker` when Windows Smart App Control blocks native PyTorch. |
| `FUNASR_DOCKER_IMAGE` | `sales-ai-funasr:local` | Docker image used for local FunASR transcription. |
| `ENABLE_SUMMARY` | `0` | Set to `1` to enable Ollama summaries. |
| `ENABLE_SALES_AI_UPLOAD` | `0` | Set to `1` to upload imported recordings to the Sales AI backend. |
| `ENABLE_WAV_CONVERT` | `1` | Set to `0` to skip FFmpeg conversion and only import/upload original recordings. |
| `PIPELINE_POLL_SECONDS` | `15` | Realtime watcher interval; minimum 5 seconds. |
| `SALES_AI_BASE_URL` | `http://127.0.0.1:8000` | Sales AI backend base URL. |
| `SALES_AI_USERNAME` | `admin` | Sales AI login username. |
| `SALES_AI_PASSWORD` | `admin123` | Sales AI login password. |
| `SALES_AI_SALES_USERNAME` | empty | When an admin uploads on behalf of a salesperson, bind the recording to this sales username. |

## Notes

For continuous processing, run `python -m app.watcher`. The watcher executes the
same deduplicated pipeline every 15 seconds and keeps running after each scan.
The root-level `启动实时销售AI系统.bat` starts Docker, Syncthing, the backend, and
this watcher together.

- Use company-owned Android work phones only.
- Keep employee notice and customer recording notice clear.
- Store original recordings, transcript text, generated summary, and processing logs for review.
- For production, add authentication, access control, encryption at rest, backups, and retention rules.

## First Real-Phone Test

1. Enable automatic call recording on the company Android phone.
2. Make a short test call and confirm that the recording appears in the phone file manager.
3. Configure Syncthing or FolderSync to send that recording folder to `data/inbox`.
4. Wait until the file finishes syncing.
5. Run `.venv\Scripts\python.exe -m app.doctor`.
6. Run `.venv\Scripts\python.exe -m app.pipeline`.
7. Confirm that:

```text
data/recordings/ has the imported original file
data/wav/ has the converted WAV file
db/sales_audio.db has a call_records row with status converted or later
```

## Upload to Sales AI Backend

After the Sales AI backend is running, enable automatic upload:

```powershell
$env:ENABLE_SALES_AI_UPLOAD="1"
$env:SALES_AI_BASE_URL="http://127.0.0.1:8000"
$env:SALES_AI_USERNAME="admin"
$env:SALES_AI_PASSWORD="admin123"
$env:SALES_AI_SALES_USERNAME="sales01"
$env:ENABLE_WAV_CONVERT="0"
.venv\Scripts\python.exe -m app.pipeline
```

The pipeline will POST each new local recording to:

```text
POST /api/call-recordings
```

The local SQLite row will store `sales_ai_upload_id`, `sales_ai_recording_id`,
and `sales_ai_uploaded_at` to avoid duplicate uploads.

For normal use, prefer logging in with the salesperson's own Sales AI account.
If a shared admin account performs the upload, set `SALES_AI_SALES_USERNAME` to
the actual salesperson username so customer ownership remains correct.

## Transcript and Summary Flow

On Windows systems where Smart App Control blocks PyTorch DLLs, build and use
the local Linux container instead. Keep Docker Desktop running:

```powershell
docker build -f Dockerfile.funasr -t sales-ai-funasr:local .
$env:ENABLE_TRANSCRIBE="1"
$env:FUNASR_RUNTIME="docker"
$env:ENABLE_WAV_CONVERT="0"
.venv\Scripts\python.exe -m app.pipeline
```

The first transcription downloads the `paraformer-zh`, `fsmn-vad`, and
`ct-punc` models into the persistent `sales_ai_funasr_cache` Docker volume.
Both WAV and M4A inputs are supported by the container.

The first production milestone is `converted`: the phone recording has reached
SQLite and has a WAV file. Speech-to-text is optional and can be enabled later.

To let an external transcription tool feed this project before FunASR is ready,
put a UTF-8 text file in `data/transcripts` with the same base name as the
recording. Example:

```text
data/inbox/158 2141 5827_20260611171309.m4a
data/transcripts/158 2141 5827_20260611171309.txt
```

Then run:

```powershell
.venv\Scripts\python.exe -m app.pipeline
```

The transcript will be written back to SQLite. If Ollama is installed and
`ENABLE_SUMMARY=1`, the same pipeline can generate the sales follow-up summary.
When the recording has already been uploaded to Sales AI, the transcript is also
sent to `/api/call-recordings/{recording_id}/transcript`. The backend then reruns
intent analysis and updates the automatic follow-up record.

## Export Results

Export the current SQLite records to a CSV file:

```powershell
.venv\Scripts\python.exe -m app.export_records
```

The CSV is written under:

```text
data/exports/
```
