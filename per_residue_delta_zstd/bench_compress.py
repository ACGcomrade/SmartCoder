"""Fast tile-level compression benchmark: zlib+bigint vs per-plane delta+lzma.

Samples tiles from photo pairs; no full store builds required.
Usage: python3 bench_compress.py [--pairs N]
"""
import argparse, json, lzma, math, random, statistics, sys, time, zlib
from pathlib import Path
import numpy as np

THIS = Path(__file__).resolve().parent
ROOT = THIS.parent
sys.path.insert(0, str(THIS)); sys.path.insert(0, str(ROOT))

from field_factory import FieldFactory
from stream_memory_cmp import _delta_encode
from PIL import Image, ImageOps


def load_photo(path, max_dim=512):
    with Image.open(path) as img:
        rgb = np.array(ImageOps.exif_transpose(img).convert('RGB'))
    h, w = rgb.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        nh, nw = max(1, int(h * scale)), max(1, int(w * scale))
        rgb = np.array(Image.fromarray(rgb).resize((nw, nh), Image.LANCZOS))
    return rgb


def bigint_tile_bytes(plane0, plane1, factory):
    Q, e, m, w = factory.q, factory.weights[0], factory.modulus, factory.cell_bytes
    flat0, flat1 = plane0.ravel().astype(int), plane1.ravel().astype(int)
    raw = bytearray(flat0.size * w)
    for i, (d0, d1) in enumerate(zip(flat0, flat1)):
        b = int((d0 + Q * d1) * e) % m
        raw[i*w:(i+1)*w] = b.to_bytes(w, 'little')
    return len(zlib.compress(bytes(raw), level=1))


def plane_tile_bytes(plane0, plane1):
    T = plane0.shape[0]
    planes = np.stack([plane0, plane1], axis=0)
    arr = np.empty((2, T * T, 3), dtype=np.uint8)
    for p in range(2):
        arr[p] = _delta_encode(planes[p]).reshape(T * T, 3)
    return len(lzma.compress(arr.tobytes(), format=lzma.FORMAT_XZ, preset=1))


def measure_pair(rgb0, rgb1, factory, T=64, max_tiles=12, rng=None):
    Q = factory.q
    H, W = max(rgb0.shape[0], rgb1.shape[0]), max(rgb0.shape[1], rgb1.shape[1])
    coords = [(ty, tx) for ty in range(0, H, T) for tx in range(0, W, T)]
    if rng and len(coords) > max_tiles:
        coords = rng.sample(coords, max_tiles)
    orig_b, cmp_b = 0, 0
    for ty, tx in coords:
        p0 = np.zeros((T, T * 3), dtype=np.uint8)
        p1 = np.zeros_like(p0)
        def fill(plane, rgb):
            if ty < rgb.shape[0] and tx < rgb.shape[1]:
                h = min(T, rgb.shape[0]-ty); ww = min(T, rgb.shape[1]-tx)
                plane[:h, :ww*3] = (rgb[ty:ty+h, tx:tx+ww] // 4).reshape(h, ww*3)
        fill(p0, rgb0); fill(p1, rgb1)
        orig_b += bigint_tile_bytes(p0, p1, factory)
        cmp_b  += plane_tile_bytes(p0, p1)
    return orig_b, cmp_b, orig_b / cmp_b if cmp_b else float('inf')


def run(photo_paths, n_pairs=150, verbose=True):
    factory = FieldFactory(1)
    rng = random.Random(42)
    photos = []
    for p in photo_paths:
        try: photos.append(load_photo(p, max_dim=512))
        except: pass
    if verbose:
        print(f"  Loaded {len(photos)} photos")
    rng.shuffle(photos)
    pairs = [(photos[i], photos[i+1]) for i in range(0, min(n_pairs*2, len(photos)-1), 2)]
    if verbose:
        print(f"  Measuring tile ratios on {len(pairs)} pairs...")
    results = []
    for i, (r0, r1) in enumerate(pairs):
        ob, cb, ratio = measure_pair(r0, r1, factory, rng=rng)
        sz = 'large' if max(r0.shape[:2]) > 300 else 'small'
        results.append({'ratio': ratio, 'bytes_orig': ob, 'bytes_cmp': cb, 'size': sz})
        if verbose and (i+1) % 50 == 0:
            print(f"    {i+1}/{len(pairs)}: ratio={ratio:.2f}×")
    ratios = [r['ratio'] for r in results]
    stats = {
        'n_pairs': len(results),
        'ratio_median': statistics.median(ratios),
        'ratio_min': min(ratios),
        'ratio_max': max(ratios),
        'ratio_p25': statistics.quantiles(ratios, n=4)[0],
        'ratio_p75': statistics.quantiles(ratios, n=4)[2],
        'overall_ratio': sum(r['bytes_orig'] for r in results) / sum(r['bytes_cmp'] for r in results),
        'C1_PASS': statistics.median(ratios) >= 2.5,
    }
    for cat in ('small', 'large'):
        sub = [r['ratio'] for r in results if r['size'] == cat]
        if sub: stats[f'ratio_median_{cat}'] = statistics.median(sub)
    if verbose:
        print(f"\n=== Tile Benchmark ({len(results)} pairs) ===")
        print(f"  Median ratio:  {stats['ratio_median']:.2f}×")
        print(f"  p25/p75:       {stats['ratio_p25']:.2f}× / {stats['ratio_p75']:.2f}×")
        print(f"  Min/Max:       {stats['ratio_min']:.2f}× / {stats['ratio_max']:.2f}×")
        print(f"  Overall:       {stats['overall_ratio']:.2f}×")
        for cat in ('small','large'):
            if f'ratio_median_{cat}' in stats:
                print(f"  {cat}:         {stats[f'ratio_median_{cat}']:.2f}×")
        print(f"  H-C1 (≥2.5×): {'PASS' if stats['C1_PASS'] else 'FAIL'}")
    return results, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--photos', default=None)
    parser.add_argument('--pairs', type=int, default=150)
    args = parser.parse_args()
    root = ROOT
    bench = root/'data'/'bench_photos'
    orig  = root/'data'/'photos'
    exts  = {'.jpg','.jpeg','.png','.bmp','.webp'}
    paths = sorted(p for p in (bench if bench.exists() else orig).rglob('*') if p.suffix.lower() in exts)
    paths += sorted(p for p in orig.glob('*') if p.suffix.lower() in exts)
    paths = list(dict.fromkeys(paths))
    print(f"Found {len(paths)} photos")
    results, stats = run(paths, n_pairs=args.pairs, verbose=True)
    out = root/'artifacts'/'compression_bench.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'stats': stats, 'sample': results[:20]}, indent=2))
    print(f"\nResults written to {out}")

if __name__ == '__main__':
    main()
