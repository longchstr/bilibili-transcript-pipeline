#!/usr/bin/env python3
import argparse, subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bvid", required=True)
    ap.add_argument("--out", default="local_audio")
    ap.add_argument("--cookies-from-browser", default=None, help="chrome/firefox/edge; optional")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    url = f"https://www.bilibili.com/video/{args.bvid}/"
    cmd = ["yt-dlp", "-f", "bestaudio/best", "--no-playlist", "-o", str(out / "%(id)s.%(ext)s")]
    if args.cookies_from_browser:
        cmd += ["--cookies-from-browser", args.cookies_from_browser]
    cmd.append(url)
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
