#!/usr/bin/env python3
import argparse, json, subprocess, datetime
from pathlib import Path


def fmt_ts(seconds):
    seconds = int(seconds)
    return f"{seconds//3600:02}:{seconds%3600//60:02}:{seconds%60:02}"


def srt_ts(x):
    h = int(x) // 3600
    m = int(x) % 3600 // 60
    s = int(x) % 60
    ms = int(round((x - int(x)) * 1000))
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--bvid", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--up", default="")
    ap.add_argument("--uid", default="")
    ap.add_argument("--out", default="transcripts")
    ap.add_argument("--model", default="small")
    ap.add_argument("--language", default="zh")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    from faster_whisper import WhisperModel

    out = Path(args.out)
    txt_dir, jsonl_dir, srt_dir = out / "txt", out / "jsonl", out / "srt"
    for d in [txt_dir, jsonl_dir, srt_dir]:
        d.mkdir(parents=True, exist_ok=True)

    wav = out / f"{args.bvid}.wav"
    subprocess.run([
        "ffmpeg", "-y", "-i", args.audio, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)
    ], check=True)

    model = WhisperModel(args.model, device=args.device, compute_type="int8" if args.device == "cpu" else "float16")
    segments, info = model.transcribe(str(wav), language=args.language, vad_filter=True)
    created_at = datetime.datetime.now().isoformat()

    header = {
        "source": "bilibili",
        "bvid": args.bvid,
        "title": args.title,
        "url": args.url or f"https://www.bilibili.com/video/{args.bvid}/",
        "up": args.up,
        "uid": args.uid,
        "audio_path": args.audio,
        "asr_engine": "faster-whisper",
        "asr_model": args.model,
        "language": args.language,
        "detected_language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "device": args.device,
        "created_at": created_at,
    }

    txt_lines = [f"# {args.title or args.bvid}", *(f"# {k}: {v}" for k, v in header.items() if v), ""]
    jsonl_lines = []
    srt_chunks = []

    for i, seg in enumerate(segments, 1):
        text = seg.text.strip()
        if not text:
            continue
        txt_lines.append(f"[{fmt_ts(seg.start)} - {fmt_ts(seg.end)}] {text}")
        rec = dict(header)
        rec.update({"index": i, "start": seg.start, "end": seg.end, "text": text})
        jsonl_lines.append(json.dumps(rec, ensure_ascii=False))
        srt_chunks.append(f"{i}\n{srt_ts(seg.start)} --> {srt_ts(seg.end)}\n{text}\n")

    (txt_dir / f"{args.bvid}.txt").write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
    (jsonl_dir / f"{args.bvid}.jsonl").write_text("\n".join(jsonl_lines) + "\n", encoding="utf-8")
    (srt_dir / f"{args.bvid}.srt").write_text("\n".join(srt_chunks), encoding="utf-8")
    wav.unlink(missing_ok=True)
    print(json.dumps({"bvid": args.bvid, "segments": len(jsonl_lines), "txt": str(txt_dir / f"{args.bvid}.txt")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
