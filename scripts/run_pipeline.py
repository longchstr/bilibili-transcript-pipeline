#!/usr/bin/env python3
import argparse, json, subprocess, traceback, shutil
from pathlib import Path


def read_jsonl(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
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

    done = set()
    if status_path.exists():
        for rec in read_jsonl(status_path):
            if rec.get("asr_status") == "done":
                done.add(rec.get("bvid"))

    videos = list(read_jsonl(args.videos))
    if args.limit:
        videos = videos[: args.limit]

    for video in videos:
        bvid = video["bvid"]
        if bvid in done:
            print("SKIP", bvid)
            continue
        try:
            audio = find_audio(audio_dir, bvid)
            if not audio:
                cmd = ["python", "scripts/download_audio.py", "--bvid", bvid, "--out", str(audio_dir)]
                if args.cookies_from_browser:
                    cmd += ["--cookies-from-browser", args.cookies_from_browser]
                subprocess.run(cmd, cwd=workdir, check=True)
                audio = find_audio(audio_dir, bvid)
            if not audio:
                raise RuntimeError("audio not found after download")

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
                **video,
                "download_status": "done",
                "asr_status": "done",
                "audio_path": str(audio),
                "transcript_txt": str(transcripts_dir / "txt" / f"{bvid}.txt"),
                "cleanup_action": cleanup,
                "error": None,
            })
            print("DONE", bvid)
        except Exception as e:
            append_jsonl(error_path, {**video, "error": repr(e), "traceback": traceback.format_exc()})
            append_jsonl(status_path, {**video, "download_status": "unknown", "asr_status": "failed", "error": repr(e)})
            print("FAILED", bvid, e)


if __name__ == "__main__":
    main()
