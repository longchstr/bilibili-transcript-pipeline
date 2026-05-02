#!/usr/bin/env python3
import argparse, json, subprocess, traceback, datetime
from pathlib import Path


def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def find_audio(audio_dir, bvid):
    for p in Path(audio_dir).glob(f"{bvid}.*"):
        if p.suffix.lower() in {".m4a", ".mp3", ".webm", ".wav"}:
            return p
    return None


def append_jsonl(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def latest_status_map(status_path):
    latest = {}
    for rec in read_jsonl(status_path) or []:
        bvid = rec.get("bvid")
        if bvid:
            latest[bvid] = rec
    return latest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, help="JSONL with bvid,title,url,up,uid")
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--model", default="small")
    ap.add_argument("--language", default="zh")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--cookies-from-browser", default=None)
    ap.add_argument("--delete-audio-after-success", action="store_true")
    args = ap.parse_args()

    workdir = Path(args.workdir)
    audio_dir = workdir / "local_audio"
    transcripts_dir = workdir / "transcripts"
    status_path = workdir / "metadata" / "processing_status.jsonl"
    error_path = workdir / "logs" / "pipeline_errors.jsonl"
    for d in [audio_dir, transcripts_dir, status_path.parent, error_path.parent]:
        d.mkdir(parents=True, exist_ok=True)

    latest = latest_status_map(status_path)
    done = {bvid for bvid, rec in latest.items() if rec.get("asr_status") == "done"}

    videos = list(read_jsonl(args.videos) or [])
    if args.limit:
        videos = videos[: args.limit]

    for video in videos:
        bvid = video["bvid"]
        if bvid in done:
            print("SKIP", bvid)
            continue
        base = {**video, "bvid": bvid, "updated_at": now_iso()}
        try:
            audio = find_audio(audio_dir, bvid)
            if audio:
                append_jsonl(status_path, {
                    **base,
                    "download_status": "done",
                    "asr_status": "pending",
                    "audio_path": str(audio),
                    "event": "audio_already_exists",
                    "error": None,
                })
            else:
                append_jsonl(status_path, {
                    **base,
                    "download_status": "running",
                    "asr_status": "pending",
                    "event": "download_started",
                    "error": None,
                })
                cmd = ["python", "scripts/download_audio.py", "--bvid", bvid, "--out", str(audio_dir)]
                if args.cookies_from_browser:
                    cmd += ["--cookies-from-browser", args.cookies_from_browser]
                subprocess.run(cmd, cwd=workdir, check=True)
                audio = find_audio(audio_dir, bvid)
                if not audio:
                    raise RuntimeError("audio not found after download")
                append_jsonl(status_path, {
                    **base,
                    "updated_at": now_iso(),
                    "download_status": "done",
                    "asr_status": "pending",
                    "audio_path": str(audio),
                    "event": "download_done",
                    "error": None,
                })

            append_jsonl(status_path, {
                **base,
                "updated_at": now_iso(),
                "download_status": "done",
                "asr_status": "running",
                "audio_path": str(audio),
                "event": "asr_started",
                "asr_engine": "faster-whisper",
                "asr_model": args.model,
                "error": None,
            })
            subprocess.run([
                "python", "scripts/transcribe_audio.py",
                "--audio", str(audio),
                "--bvid", bvid,
                "--title", video.get("title", ""),
                "--url", video.get("url", f"https://www.bilibili.com/video/{bvid}/"),
                "--up", video.get("up", ""),
                "--uid", str(video.get("uid", "")),
                "--out", str(transcripts_dir),
                "--model", args.model,
                "--language", args.language,
            ], cwd=workdir, check=True)

            cleanup = "kept"
            if args.delete_audio_after_success:
                Path(audio).unlink(missing_ok=True)
                cleanup = "deleted"

            append_jsonl(status_path, {
                **base,
                "updated_at": now_iso(),
                "download_status": "done",
                "asr_status": "done",
                "audio_path": str(audio),
                "transcript_txt": str(transcripts_dir / "txt" / f"{bvid}.txt"),
                "transcript_jsonl": str(transcripts_dir / "jsonl" / f"{bvid}.jsonl"),
                "transcript_srt": str(transcripts_dir / "srt" / f"{bvid}.srt"),
                "cleanup_action": cleanup,
                "event": "asr_done",
                "asr_engine": "faster-whisper",
                "asr_model": args.model,
                "error": None,
            })
            print("DONE", bvid)
        except Exception as e:
            append_jsonl(error_path, {**base, "updated_at": now_iso(), "error": repr(e), "traceback": traceback.format_exc()})
            append_jsonl(status_path, {
                **base,
                "updated_at": now_iso(),
                "download_status": "failed" if not find_audio(audio_dir, bvid) else "done",
                "asr_status": "failed",
                "event": "failed",
                "error": repr(e),
            })
            print("FAILED", bvid, e)


if __name__ == "__main__":
    main()
