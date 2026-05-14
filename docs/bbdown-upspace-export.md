# BBDown QR-login UP-space export fallback

Bilibili UP-space listing often hits anti-bot controls such as HTTP 412 or WBI `-352` when using anonymous API calls or `yt-dlp --flat-playlist`.

A practical fallback is to use BBDown QR login to export the full submission URL list, then hydrate public metadata separately.

## Flow

```bash
./BBDown login
./BBDown "https://space.bilibili.com/<UID>/video" --only-show-info > space_info.txt 2>&1
```

Look for a generated text file named like `<UP主名>的投稿视频.txt`; it usually contains `av...` URLs.

Then convert `aid`/`av` entries to public metadata with:

```text
https://api.bilibili.com/x/web-interface/view?aid=<aid>
```

Store the hydrated rows as JSONL with fields such as:

```json
{"bvid":"BV...","aid":123,"title":"...","url":"https://www.bilibili.com/video/BV.../","duration_sec":123,"pubdate":1234567890,"up":"...","uid":123}
```

## Safety rules

- Never commit or print BBDown login data, cookies, QR-login state, browser profiles, or raw request headers.
- Commit only public video URLs and hydrated public metadata.
- Use the master JSONL as the input to downstream audio/ASR stages.
