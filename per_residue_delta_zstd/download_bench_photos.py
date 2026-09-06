"""Download benchmark photos from multiple sources for compression testing.

Primary source: Picsum Photos (https://picsum.photos) — free, diverse, no auth.
  URL pattern: https://picsum.photos/id/{id}/{width}/{height}.jpg

Generates ~400 photos across diverse sizes (100–1500 px), aspect ratios, and content.

Usage:
    python3 download_bench_photos.py [--count 400] [--outdir ../data/bench_photos]
"""
import argparse
import hashlib
import json
import os
import random
import threading
import time
import urllib.request
from pathlib import Path
from collections import Counter

# Picsum Photos serves real Unsplash photos; follows redirects automatically
PICSUM_URL = "https://picsum.photos/id/{id}/{w}/{h}.jpg"
TIMEOUT = 30
MAX_WORKERS = 8

# Picsum IDs known to exist (1–1052, some missing); use a broad range
PICSUM_ID_RANGE = (1, 1052)

# Diverse size/aspect-ratio combinations for the benchmark
SIZE_GRID = [
    (100, 75),    # small landscape
    (150, 200),   # small portrait
    (200, 200),   # small square
    (320, 240),   # QVGA landscape
    (240, 320),   # QVGA portrait
    (400, 300),   # medium landscape
    (300, 400),   # medium portrait
    (500, 375),   # medium landscape
    (640, 480),   # VGA landscape
    (480, 640),   # VGA portrait
    (640, 640),   # VGA square
    (800, 450),   # HD-ish wide
    (450, 800),   # tall
    (800, 600),   # SVGA landscape
    (600, 800),   # SVGA portrait
    (1024, 576),  # 16:9
    (1024, 768),  # XGA
    (768, 1024),  # XGA portrait
    (1280, 720),  # 720p
    (1500, 1000), # large landscape
    (1000, 1500), # large portrait
    (1200, 1200), # large square
    (2000, 500),  # ultrawide
    (500, 2000),  # very tall
    (300, 100),   # panorama-ish small
]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def download_url(url, timeout=TIMEOUT, follow_redirects=True):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def generate_tasks(n, seed=42):
    """Generate n (id, w, h) tasks covering diverse sizes and IDs."""
    rng = random.Random(seed)
    id_range = list(range(PICSUM_ID_RANGE[0], PICSUM_ID_RANGE[1] + 1))
    rng.shuffle(id_range)

    tasks = []
    size_cycle = SIZE_GRID * (n // len(SIZE_GRID) + 2)
    for i in range(n):
        pid = id_range[i % len(id_range)]
        w, h = size_cycle[i]
        tasks.append({'id': pid, 'w': w, 'h': h,
                      'file': f'picsum_{pid:04d}_{w}x{h}.jpg'})
    return tasks


def _worker(task, out_dir, results, lock, errs):
    fn = task['file']
    url = PICSUM_URL.format(id=task['id'], w=task['w'], h=task['h'])
    out = out_dir / fn
    if out.exists():
        with lock:
            results.append({'file': str(out), 'name': fn,
                            'width': task['w'], 'height': task['h'], 'cached': True})
        return
    try:
        data = download_url(url)
        out.write_bytes(data)
        with lock:
            results.append({'file': str(out), 'name': fn,
                            'width': task['w'], 'height': task['h'],
                            'sha256': sha256(data), 'cached': False})
    except Exception as exc:
        with lock:
            errs.append((fn, str(exc)))


def download_parallel(tasks, out_dir, max_workers=MAX_WORKERS):
    out_dir.mkdir(parents=True, exist_ok=True)
    results, errs, lock = [], [], threading.Lock()
    threads = []
    sem = threading.Semaphore(max_workers)

    def bounded(task):
        sem.acquire()
        try:
            _worker(task, out_dir, results, lock, errs)
        finally:
            sem.release()

    for task in tasks:
        t = threading.Thread(target=bounded, args=(task,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.02)

    for t in threads:
        t.join()

    return results, errs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=400)
    parser.add_argument('--outdir', type=str, default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_dir = Path(args.outdir) if args.outdir else root / 'data' / 'bench_photos'

    tasks = generate_tasks(args.count)
    print(f"Downloading {len(tasks)} photos from Picsum Photos (diverse sizes)...")

    # Show size diversity
    cnt = Counter(
        ('small' if t['w']*t['h'] < 300*300 else
         'large' if t['w']*t['h'] > 1200*1200 else 'medium')
        + '/'
        + ('portrait' if t['h'] > t['w']*1.25 else
           'landscape' if t['w'] > t['h']*1.25 else 'square')
        for t in tasks
    )
    for k, v in sorted(cnt.items()):
        print(f"  {k}: {v}")

    results, errs = download_parallel(tasks, out_dir, MAX_WORKERS)
    print(f"\nDownloaded: {len(results)} | Errors: {len(errs)}")
    if errs:
        for fn, msg in errs[:5]:
            print(f"  FAIL {fn}: {msg}")

    manifest = {'source': 'Picsum Photos (Unsplash)', 'count': len(results),
                 'images': results}
    manifest_path = root / 'data' / 'bench_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest written to {manifest_path}")
    print(f"Output dir: {out_dir}")


if __name__ == '__main__':
    main()
