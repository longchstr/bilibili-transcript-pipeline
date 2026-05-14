#!/usr/bin/env python3
"""Generic continuous Bilibili/FunASR autorun watchdog template.

Copy this file into your own automation environment and edit CONFIG below.
It is intentionally conservative:
- ingest completed stage outputs before starting the next stage;
- commit only text/metadata/transcript artifacts;
- reject audio/video files and obvious secret labels before git commit;
- do not print tokens/cookies.
"""
import json, os, re, shutil, subprocess
from pathlib import Path

CONFIG = {
    "repo": "/path/to/corpus-repo",
    "corpus_dir": "creator_slug",
    "master_jsonl": "metadata/videos_master.jsonl",
    "stage_prefix": "/tmp/bilibili_funasr_stage",
    "python": "/path/to/venv/bin/python",
    "yt_dlp": "/path/to/venv/bin/yt-dlp",
    "pipeline_script": "scripts/funasr_batch_pipeline.py",
    "batch_size": 50,
    "git_branch": "main",
}

MEDIA_EXT = {'.m4a','.mp3','.wav','.mp4','.flac','.aac','.webm','.mov','.mkv','.ogg'}
SECRET_RE = re.compile(r'(SESSDATA\s*[=:]|bili_jct\s*[=:]|DedeUserID\s*[=:]|GITHUB_TOKEN\s*[=:]|API_KEY\s*[=:]|PASSWORD\s*[=:]|cookie\s*[=:])', re.I)


def run(cmd, cwd=None, timeout=180, check=True, env=None):
    p = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed {p.returncode}: {' '.join(map(str, cmd))}\n{p.stdout[-2000:]}")
    return p.stdout


def paths():
    repo = Path(CONFIG["repo"]).resolve()
    corpus = repo / CONFIG["corpus_dir"]
    return repo, corpus


def stage_num_from_path(p: Path):
    m = re.search(r'stage(\d+)', str(p))
    return int(m.group(1)) if m else None


def active_stage_processes():
    out = run(['ps','-eo','pid=,args='], timeout=30, check=False)
    prefix = CONFIG["stage_prefix"]
    return [line.strip() for line in out.splitlines() if 'run_stage_funasr.py' in line and prefix in line and 'python' in line]


def next_stage_number(corpus: Path):
    nums=[]
    for p in (corpus/'metadata').glob('stage*_funasr'):
        m = re.search(r'stage(\d+)_funasr', p.name)
        if m: nums.append(int(m.group(1)))
    return max(nums) + 1 if nums else 1


def completed_uningested_stages(corpus: Path):
    stages=[]
    pattern = Path(CONFIG["stage_prefix"]).name + '*'
    for base in sorted(Path('/tmp').glob(pattern), key=lambda p: stage_num_from_path(p) or 0):
        n = stage_num_from_path(base)
        if not n: continue
        summary_path = base/'metadata/status_summary.json'
        repo_summary = corpus/f'metadata/stage{n}_funasr/status_summary.json'
        if summary_path.exists() and not repo_summary.exists():
            summary=json.loads(summary_path.read_text(encoding='utf-8'))
            if summary.get('total') and summary.get('transcribed',0)+summary.get('failed',0)+summary.get('unprocessed',0)==summary.get('total'):
                stages.append((n, base, summary))
    return stages


def copy_stage(corpus: Path, n: int, base: Path):
    maps=[('transcripts/txt','transcripts/txt'),('transcripts/jsonl','transcripts/jsonl'),('transcripts/srt','transcripts/srt'),('transcripts/raw_funasr','transcripts/raw_funasr'),('metadata',f'metadata/stage{n}_funasr')]
    for srel,drel in maps:
        sdir=base/srel; ddir=corpus/drel; ddir.mkdir(parents=True, exist_ok=True)
        if not sdir.exists(): continue
        for root,_,files in os.walk(sdir):
            rel=Path(root).relative_to(sdir); (ddir/rel).mkdir(parents=True, exist_ok=True)
            for f in files: shutil.copy2(Path(root)/f, ddir/rel/f)


def safety_check_changed(repo: Path):
    changed=run(['git','status','--porcelain'], cwd=repo, timeout=30).splitlines()
    paths=[line[3:] for line in changed if len(line)>3]
    media=[p for p in paths if Path(p).suffix.lower() in MEDIA_EXT]
    hits=[]
    for p in paths:
        pp=repo/p
        if pp.is_file() and pp.stat().st_size < 2_000_000:
            try: txt=pp.read_text(errors='ignore')
            except Exception: continue
            if SECRET_RE.search(txt): hits.append(p)
    if media or hits:
        raise RuntimeError(f'safety check failed: media={media[:10]} secret_label_hits={hits[:10]}')


def ingest_stage(repo: Path, corpus: Path, n: int, base: Path, summary: dict):
    copy_stage(corpus, n, base)
    safety_check_changed(repo)
    rel = CONFIG["corpus_dir"]
    run(['git','add',f'{rel}/transcripts/txt',f'{rel}/transcripts/jsonl',f'{rel}/transcripts/srt',f'{rel}/transcripts/raw_funasr',f'{rel}/metadata/stage{n}_funasr'], cwd=repo)
    run(['git','commit','-m',f'data: add FunASR stage {n} transcripts'], cwd=repo)
    run(['git','push','origin',CONFIG['git_branch']], cwd=repo, timeout=300)
    return f"Stage {n} pushed: {summary.get('transcribed')}/{summary.get('total')} success, failed {summary.get('failed')}"


def prepare_next_stage(corpus: Path, n: int):
    master = corpus / CONFIG["master_jsonl"]
    allv=[json.loads(l) for l in master.read_text(encoding='utf-8').splitlines() if l.strip()]
    processed={p.stem for p in (corpus/'transcripts/txt').glob('*.txt')}
    remaining=[v for v in allv if v.get('bvid') not in processed]
    remaining.sort(key=lambda v: (int(v.get('duration_sec') or 10**9), int(v.get('pubdate') or 0), v.get('bvid','')))
    if not remaining: return None
    selected=remaining[:int(CONFIG['batch_size'])]
    base=Path(f"{CONFIG['stage_prefix']}{n}")
    if base.exists(): shutil.rmtree(base)
    for d in ['metadata','scripts','local_audio','logs','transcripts/txt','transcripts/jsonl','transcripts/srt','transcripts/raw_funasr']:
        (base/d).mkdir(parents=True, exist_ok=True)
    (base/'metadata/videos_master.jsonl').write_text('\n'.join(json.dumps(v, ensure_ascii=False) for v in selected)+'\n', encoding='utf-8')
    shutil.copy2(CONFIG['pipeline_script'], base/'scripts/run_stage_funasr.py')
    return base, len(selected), len(remaining)


def start_stage(base: Path):
    log=base/'logs/runner.log'
    cmd=[CONFIG['python'], str(base/'scripts/run_stage_funasr.py'), '--base', str(base), '--yt-dlp', CONFIG['yt_dlp']]
    with log.open('ab') as f:
        p=subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
    return p.pid


def main():
    repo, corpus = paths()
    messages=[]
    for n, base, summary in completed_uningested_stages(corpus):
        messages.append(ingest_stage(repo, corpus, n, base, summary))
    if not active_stage_processes():
        prep=prepare_next_stage(corpus, next_stage_number(corpus))
        if prep is None:
            messages.append('No remaining videos.')
        else:
            base, selected, remaining_before=prep
            pid=start_stage(base)
            messages.append(f"Started {base.name}: {selected} videos, remaining before start {remaining_before}, pid {pid}")
    if messages:
        print('\n'.join(messages))

if __name__ == '__main__':
    main()
