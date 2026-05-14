#!/usr/bin/env python3
"""
Reusable FunASR batch pipeline for Bilibili transcript corpora.

Input:  metadata/videos_master.jsonl with at least bvid,title,url,up,uid fields.
Output: transcripts/{txt,jsonl,srt,raw_funasr}/ plus metadata/processing_status.jsonl,
        metadata/status_summary.json, metadata/status_report.csv.
Audio:  downloaded to local_audio/ and should be ignored by Git.

Usage:
  cd <workspace>
  python scripts/funasr_batch_pipeline.py --base . --yt-dlp /path/to/yt-dlp

Notes:
- Load FunASR AutoModel once per batch.
- Request sentence_timestamp=True, but fall back to punctuation splitting if sentence_info is missing.
- Keep raw_funasr immutable; create cleaned/final outputs in later review steps.
"""

import argparse, datetime as dt, json, re, subprocess, sys, time
from pathlib import Path

DEFAULT_HOTWORDS = "卡秃噜皮君 峰哥 皮子 b友 石头 富婆 王哥 挂逼房 咸鱼栗 深圳 白领 姜子牙 守株待兔"


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def append_jsonl(path: Path, rec: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run(cmd, log_path=None):
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(p.stdout, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"command failed {p.returncode}: {' '.join(cmd)}\n{p.stdout[-2000:]}")
    return p.stdout


def ffprobe_duration(path: Path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "json", str(path)])
    data = json.loads(out).get("format", {})
    return float(data.get("duration") or 0), int(data.get("size") or 0)


def fmt_srt_time(sec: float):
    sec = max(0.0, sec)
    ms = int(round(sec * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def fmt_txt_time(sec: float):
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02}"


def split_sentences(text: str):
    text = re.sub(r"\s+", "", text or "").strip()
    if not text:
        return []
    parts = re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text)
    return [p.strip() for p in parts if p.strip()]


def segments_from_result(res, duration):
    # Prefer sentence timestamps if provided by FunASR.
    segs = []
    items = res if isinstance(res, list) else [res]
    for item in items:
        for s in item.get("sentence_info") or []:
            text = (s.get("text") or "").strip()
            if not text:
                continue
            start = float(s.get("start") or 0) / 1000.0
            end = float(s.get("end") or 0) / 1000.0
            if end <= start:
                end = min(duration, start + max(1.0, len(text) / 8))
            segs.append({"start": start, "end": end, "text": text})
    if segs:
        return segs

    # Fallback: split final text by punctuation and allocate approximate times.
    text = "".join((item.get("text") or "") for item in items)
    sents = split_sentences(text)
    if not sents:
        return []
    total_chars = sum(max(1, len(s)) for s in sents)
    cur = 0.0
    out = []
    for i, sent in enumerate(sents):
        end = duration if i == len(sents) - 1 else cur + duration * max(1, len(sent)) / total_chars
        out.append({"start": cur, "end": max(end, cur + 0.5), "text": sent})
        cur = end
    return out


def write_outputs(base: Path, video: dict, audio_path: Path, duration: float, size: int, res, elapsed: float, hotwords: str):
    bvid = video["bvid"]
    header = {
        "source": "bilibili",
        "up": video.get("up"),
        "uid": video.get("uid"),
        "bvid": bvid,
        "title": video.get("title"),
        "url": video.get("url"),
        "pubdate": video.get("pubdate"),
        "published_at": video.get("published_at"),
        "duration_sec": duration,
        "audio_size_bytes": size,
        "audio_path": str(audio_path),
        "asr_engine": "funasr",
        "asr_model": "paraformer-zh",
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
        "hotwords": hotwords,
        "language": "zh",
        "device": "cpu",
        "transcribed_at": now(),
        "elapsed_seconds": round(elapsed, 2),
        "rtf_wall": round(elapsed / duration, 4) if duration else None,
    }
    segs = segments_from_result(res, duration)

    txt_path = base / "transcripts/txt" / f"{bvid}.txt"
    jsonl_path = base / "transcripts/jsonl" / f"{bvid}.jsonl"
    srt_path = base / "transcripts/srt" / f"{bvid}.srt"
    raw_path = base / "transcripts/raw_funasr" / f"{bvid}.json"
    for p in [txt_path, jsonl_path, srt_path, raw_path]:
        p.parent.mkdir(parents=True, exist_ok=True)

    txt_lines = [f"# {video.get('title')}"] + [f"# {k}: {v}" for k, v in header.items() if v is not None] + [""]
    jsonl_lines, srt_lines = [], []
    for idx, seg in enumerate(segs, 1):
        txt_lines.append(f"[{fmt_txt_time(seg['start'])} - {fmt_txt_time(seg['end'])}] {seg['text']}")
        rec = dict(header)
        rec.update({"segment_index": idx, "start": round(seg["start"], 3), "end": round(seg["end"], 3), "text": seg["text"]})
        jsonl_lines.append(json.dumps(rec, ensure_ascii=False))
        srt_lines += [str(idx), f"{fmt_srt_time(seg['start'])} --> {fmt_srt_time(seg['end'])}", seg["text"], ""]

    txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
    jsonl_path.write_text("\n".join(jsonl_lines) + "\n", encoding="utf-8")
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    raw_path.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "transcript_txt": str(txt_path.relative_to(base)),
        "transcript_jsonl": str(jsonl_path.relative_to(base)),
        "transcript_srt": str(srt_path.relative_to(base)),
        "raw_funasr": str(raw_path.relative_to(base)),
        "segments": len(segs),
        "chars": sum(len(s["text"]) for s in segs),
        "elapsed_seconds": round(elapsed, 2),
        "rtf_wall": round(elapsed / duration, 4) if duration else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=".")
    ap.add_argument("--yt-dlp", default="yt-dlp")
    ap.add_argument("--hotwords", default=DEFAULT_HOTWORDS)
    args = ap.parse_args()
    base = Path(args.base).resolve()
    videos_path = base / "metadata/videos_master.jsonl"
    videos = [json.loads(l) for l in videos_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    status = base / "metadata/processing_status.jsonl"
    errors = base / "logs/pipeline_errors.jsonl"

    print("loading FunASR model once...", flush=True)
    from funasr import AutoModel
    model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc", disable_update=True)

    latest = []
    for v in videos:
        bvid = v["bvid"]
        audio = base / "local_audio" / f"{bvid}.m4a"
        try:
            if not audio.exists():
                append_jsonl(status, {**v, "updated_at": now(), "event": "download_started", "download_status": "running", "asr_status": "pending"})
                run([args.yt_dlp, "-q", "--no-warnings", "-f", "bestaudio/best", "--no-playlist", "-o", str(base / "local_audio" / f"{bvid}.%(ext)s"), v["url"]], base / "logs" / f"{bvid}_download.log")
            append_jsonl(status, {**v, "updated_at": now(), "event": "download_done", "download_status": "done", "asr_status": "pending", "audio_path": str(audio.relative_to(base))})
            duration, size = ffprobe_duration(audio)
            append_jsonl(status, {**v, "updated_at": now(), "event": "asr_started", "download_status": "done", "asr_status": "running", "audio_path": str(audio.relative_to(base)), "asr_engine": "funasr", "asr_model": "paraformer-zh"})
            t0 = time.perf_counter()
            res = model.generate(input=str(audio), language="zh", hotword=args.hotwords, sentence_timestamp=True)
            elapsed = time.perf_counter() - t0
            out = write_outputs(base, v, audio, duration, size, res, elapsed, args.hotwords)
            done = {**v, "updated_at": now(), "event": "asr_done", "download_status": "done", "asr_status": "done", "audio_path": str(audio.relative_to(base)), "cleanup_action": "kept_local", "asr_engine": "funasr", "asr_model": "paraformer-zh", **out}
            append_jsonl(status, done)
            latest.append(done)
            print(f"DONE {bvid} elapsed={out['elapsed_seconds']}s chars={out['chars']} segments={out['segments']}", flush=True)
        except Exception as e:
            rec = {**v, "updated_at": now(), "event": "failed", "download_status": "done" if audio.exists() else "failed", "asr_status": "failed", "error": str(e)}
            append_jsonl(status, rec)
            append_jsonl(errors, rec)
            latest.append(rec)
            print(f"FAILED {bvid}: {e}", file=sys.stderr, flush=True)

    total = len(videos)
    done_count = sum(1 for r in latest if r.get("asr_status") == "done")
    failed_count = sum(1 for r in latest if r.get("asr_status") == "failed")
    summary = {
        "updated_at": now(),
        "total": total,
        "transcribed": done_count,
        "failed": failed_count,
        "unprocessed": total - done_count - failed_count,
        "asr_engine": "funasr",
        "asr_model": "paraformer-zh",
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
    }
    (base / "metadata/status_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cols = ["bvid", "title", "duration_sec", "download_status", "asr_status", "segments", "chars", "elapsed_seconds", "rtf_wall", "transcript_txt", "error"]
    rows = [cols] + [[str(r.get(c, "")) for c in cols] for r in latest]
    (base / "metadata/status_report.csv").write_text("\n".join(",".join('"' + x.replace('"', '""') + '"' for x in row) for row in rows) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
