# Rolling production workflow

Use this when a Bilibili corpus run has passed a small smoke test and you want unattended staged processing.

## Loop

1. Keep a durable `metadata/videos_master.jsonl` with `bvid`, `title`, `url`, `duration_sec`, `pubdate`, `up`, and `uid` when available.
2. Select only videos without `transcripts/txt/<BVID>.txt`.
3. Run a bounded stage, usually 20-100 videos depending on duration and machine capacity.
4. Write append-only `metadata/processing_status.jsonl` events.
5. At stage end, produce `status_summary.json`, `status_report.csv`, and transcript artifacts under `transcripts/`.
6. Ingest completed stages into the corpus repo immediately; do not leave successful outputs only in `/tmp`.
7. Before commit, reject media extensions and scan changed text files for obvious secret labels.
8. Commit/push successes and failure reports together.
9. Start the next stage only after the previous stage has been ingested or explicitly marked skipped/deferred.

## Failure policy

- Do not delete or rebuild a whole stage just because a few selected videos failed.
- Preserve successful transcripts.
- Record failed `BVID`, title, stage, and error in `status_report.csv`.
- Defer failures from automatic selection by default; only retry when explicitly approved.
- Make manual retry allowlists one-shot to avoid infinite loops on permanently failing videos.

## Git hygiene

Commit scripts, docs, public metadata, transcript text/jsonl/srt/raw ASR JSON, and status summaries/reports.
Do not commit audio/video files, cookies, tokens, browser profiles, QR-login state, `.env`, BBDown data files, or large temporary logs with credentials/request headers.
