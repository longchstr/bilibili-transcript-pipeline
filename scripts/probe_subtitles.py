#!/usr/bin/env python3
import argparse, json, time
import requests

UA = "Mozilla/5.0"


def check_bvid(session, bvid):
    out = {"bvid": bvid}
    v = session.get("https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid}, timeout=20).json()
    out["view_code"] = v.get("code")
    data = v.get("data") or {}
    out.update({
        "title": data.get("title"),
        "cid": data.get("cid"),
        "owner": data.get("owner"),
        "duration": data.get("duration"),
    })
    cid = data.get("cid")
    if not cid:
        out["subtitle_count"] = None
        return out

    p = session.get(
        "https://api.bilibili.com/x/player/v2",
        params={"bvid": bvid, "cid": cid},
        headers={"User-Agent": UA, "Referer": f"https://www.bilibili.com/video/{bvid}/"},
        timeout=20,
    ).json()
    subs = (((p.get("data") or {}).get("subtitle") or {}).get("subtitles") or [])
    out["subtitle_count"] = len(subs)
    out["subtitles"] = [
        {"id": x.get("id"), "lan": x.get("lan"), "lan_doc": x.get("lan_doc"), "subtitle_url": x.get("subtitle_url")}
        for x in subs
    ]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bvid", action="append", required=True, help="BV id; can pass multiple times")
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    for bvid in args.bvid:
        print(json.dumps(check_bvid(s, bvid), ensure_ascii=False))
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
