# Bilibili Transcript Pipeline

A reusable pipeline for turning public Bilibili videos from any UP主 into timestamped transcripts.

Core workflow:

```text
UP/video list → download audio → ASR transcription → txt/jsonl/srt outputs → processing status → retry/resume
```

## What this repo does

- Discover videos from a Bilibili UP space or a prepared `videos.jsonl`
- Download best available audio with `yt-dlp`
- Transcribe audio with `faster-whisper` or compatible ASR tools
- Save outputs with clear source metadata:
  - original video title
  - BV ID
  - URL
  - UP name / UID when available
  - ASR engine and model
  - transcription timestamp
- Keep processing status so the pipeline can resume after failures

## Recommended storage policy

- Commit to Git:
  - scripts
  - metadata
  - transcript `.txt/.jsonl/.srt`
  - small examples only
- Do **not** commit full audio/video downloads.
- Audio is an intermediate local artifact:
  - keep locally while transcribing
  - archive small files if useful
  - delete large files after transcript verification

## Directory layout

```text
project/
  metadata/
    videos_master.jsonl
    processing_status.jsonl
  transcripts/
    txt/
    jsonl/
    srt/
  logs/
    download_errors.jsonl
    asr_errors.jsonl
  local_audio/          # gitignored
  local_audio_archive/  # gitignored
  scripts/
```

## Status tracking

The batch runner appends events to:

```text
metadata/processing_status.jsonl
logs/pipeline_errors.jsonl
```

Each video can be in one of these states:

- `pending`: in the master list but not processed yet
- `download_status=done, asr_status=pending`: audio downloaded, not transcribed
- `download_status=done, asr_status=running`: ASR is running
- `download_status=done, asr_status=done`: transcript generated
- `asr_status=failed` or `download_status=failed`: needs retry/debug

Generate a summary report anytime:

```bash
python scripts/status_report.py \
  --videos metadata/videos_master.jsonl \
  --status metadata/processing_status.jsonl
```

This writes:

```text
metadata/status_report.csv
metadata/status_summary.json
```

## Install

```bash
pip install yt-dlp requests faster-whisper
```

You also need `ffmpeg` installed.

## Usage

### 1. Probe subtitles for known BV IDs

```bash
python scripts/probe_subtitles.py --bvid BV1xxxx --bvid BV2xxxx
```

### 2. Download one video audio

```bash
python scripts/download_audio.py \
  --bvid BV1xxxx \
  --out local_audio
```

### 3. Transcribe one audio file

```bash
python scripts/transcribe_audio.py \
  --audio local_audio/BV1xxxx.m4a \
  --bvid BV1xxxx \
  --title "Video title" \
  --url "https://www.bilibili.com/video/BV1xxxx/" \
  --out transcripts \
  --model small
```

### 4. Run batch pipeline

Prepare `metadata/videos_master.jsonl`:

```json
{"bvid":"BVxxxx","title":"视频标题","url":"https://www.bilibili.com/video/BVxxxx/","up":"UP主名","uid":"123"}
```

Then:

```bash
python scripts/run_pipeline.py \
  --videos metadata/videos_master.jsonl \
  --workdir . \
  --model small \
  --limit 20
```

## Notes on Bilibili access

Anonymous access can work for individual public videos, but full UP-space crawling may trigger Bilibili anti-bot checks or HTTP 412.

For full and stable UP video list extraction, run locally with your browser login cookies:

```bash
yt-dlp --cookies-from-browser chrome --flat-playlist --dump-json \
  "https://space.bilibili.com/UID/video" \
  > metadata/videos_master.jsonl
```

## Legal / ethical note

Use this for personal research, indexing, accessibility, and authorized datasets. Respect Bilibili terms, creator rights, and copyright restrictions. Do not redistribute copyrighted transcripts/audio without permission.


## 2026 production update: FunASR rolling batches

This repo now includes the newer production-tested Bilibili/FunASR workflow:

- `scripts/funasr_batch_pipeline.py`: loads FunASR once per batch, downloads Bilibili audio with `yt-dlp`, writes txt/jsonl/srt/raw_funasr outputs, and emits `processing_status.jsonl`, `status_summary.json`, and `status_report.csv`.
- `scripts/continuous_funasr_autorun_template.py`: generic watchdog template for staged ingest, safety scan, commit/push, and starting the next batch.
- `docs/rolling-production.md`: operational rules for long rolling corpus jobs, including failure deferral and no-audio Git hygiene.
- `docs/bbdown-upspace-export.md`: QR-login full submission export fallback when UP-space listing hits Bilibili anti-bot controls.

Recommended split:

- Keep this repo public and generic: scripts, templates, docs, small examples.
- Keep creator-specific corpora private when needed: transcripts, status ledgers, metadata, and local automation config.
- Never commit audio/video intermediates or cookies/tokens.
