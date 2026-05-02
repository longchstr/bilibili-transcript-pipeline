#!/usr/bin/env python3
import argparse, csv, json
from collections import Counter
from pathlib import Path


def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def latest_by_bvid(rows):
    latest = {}
    for row in rows:
        bvid = row.get("bvid")
        if bvid:
            latest[bvid] = row
    return latest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, help="master videos JSONL")
    ap.add_argument("--status", default="metadata/processing_status.jsonl")
    ap.add_argument("--out", default="metadata/status_report.csv")
    ap.add_argument("--json", default="metadata/status_summary.json")
    args = ap.parse_args()

    videos = read_jsonl(args.videos)
    status = latest_by_bvid(read_jsonl(args.status))

    rows = []
    counts = Counter()
    for v in videos:
        bvid = v.get("bvid")
        s = status.get(bvid, {})
        download_status = s.get("download_status", "pending")
        asr_status = s.get("asr_status", "pending")
        if not s:
            overall = "unprocessed"
        elif download_status == "done" and asr_status == "done":
            overall = "transcribed"
        elif download_status == "done" and asr_status != "done":
            overall = "downloaded_not_transcribed"
        elif asr_status == "failed" or download_status == "failed":
            overall = "failed"
        else:
            overall = "incomplete"
        counts[overall] += 1
        rows.append({
            "bvid": bvid,
            "title": v.get("title", s.get("title", "")),
            "url": v.get("url", s.get("url", f"https://www.bilibili.com/video/{bvid}/")),
            "download_status": download_status,
            "asr_status": asr_status,
            "overall_status": overall,
            "audio_path": s.get("audio_path", ""),
            "transcript_txt": s.get("transcript_txt", ""),
            "cleanup_action": s.get("cleanup_action", ""),
            "error": s.get("error", ""),
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["bvid"])
        writer.writeheader()
        writer.writerows(rows)

    summary = {"total": len(videos), **dict(counts)}
    json_out = Path(args.json)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False))
    print(f"CSV: {out}")
    print(f"JSON: {json_out}")


if __name__ == "__main__":
    main()
