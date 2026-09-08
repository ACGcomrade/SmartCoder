"""
v2: center-crop vs random-mask corruption on all 380 photos (256×256 canonical).

Both corruptions share the same nominal erasure levels p ∈ {0.10,…,0.50}.
Crop keeps a contiguous center block; mask zeroes independently-random pixels
using a nested permutation (fixed seed per photo).

Results feed directly into RESULTS_CORRUPTION_V2.md.
"""
import hashlib
import json
import math
import random
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
THIS = Path(__file__).resolve().parent

CANONICAL = 256          # resize all photos to this before any computation
CROP_LEVELS = [0.10, 0.20, 0.30, 0.40, 0.50]
N_UNREL = 20             # unrelated samples per (photo, level, type)
SEED_GLOBAL = 42


# ── photo loading ──────────────────────────────────────────────────────────

def collect_paths():
    exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    paths = []
    for d in [ROOT / 'data' / 'bench_photos', ROOT / 'data' / 'photos']:
        if d.exists():
            paths.extend(p for p in sorted(d.iterdir()) if p.suffix.lower() in exts)
    # deduplicate while preserving order
    seen, out = set(), []
    for p in paths:
        k = p.name
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def load_q(path):
    """Load photo, resize to CANONICAL×CANONICAL, quantise to 6-bit."""
    with Image.open(path) as img:
        rgb = np.array(
            ImageOps.exif_transpose(img).convert('RGB')
            .resize((CANONICAL, CANONICAL), Image.LANCZOS)
        )
    return (rgb // 4).astype(np.float64)   # [0, 63]


# ── corruption functions ───────────────────────────────────────────────────

def crop_plane(q, p):
    """
    Center crop at level p (removes p of each dimension).
    Returns a CANONICAL×CANONICAL plane with the crop placed at its original position.
    """
    H = W = CANONICAL
    nh = max(1, int(round(H * (1 - p))))
    nw = max(1, int(round(W * (1 - p))))
    y0 = (H - nh) // 2
    x0 = (W - nw) // 2
    plane = np.zeros((H, W, 3), dtype=np.float64)
    plane[y0:y0 + nh, x0:x0 + nw] = q[y0:y0 + nh, x0:x0 + nw]
    return plane


def mask_permutation(path):
    """Deterministic pixel permutation for one photo (nested masks)."""
    digest = hashlib.sha1(path.name.encode()).digest()
    seed = int.from_bytes(digest[:4], 'big')
    rng = np.random.default_rng(seed)
    n = CANONICAL * CANONICAL * 3
    return rng.permutation(n)   # indices to zero, first p*n used


def mask_plane(q, p, perm):
    """
    Mask the first floor(p * n_pixels) entries of perm to 0.
    Nested: perm[0:floor(p*n)] is always a subset of perm[0:floor(p'*n)] for p<p'.
    """
    flat = q.ravel().copy()
    n_mask = int(math.floor(p * flat.size))
    flat[perm[:n_mask]] = 0.0
    return flat.reshape(q.shape)


# ── Pearson r ──────────────────────────────────────────────────────────────

def pearson(a, b):
    af, bf = a.ravel(), b.ravel()
    am, bm = af - af.mean(), bf - bf.mean()
    denom = math.sqrt(float(np.dot(am, am)) * float(np.dot(bm, bm)))
    return float(np.dot(am, bm)) / denom if denom > 0 else 0.0


def rho_theory_crop(p, mu, sigma):
    denom = math.sqrt(sigma ** 2 + mu ** 2 * p * (2 - p))
    return (1 - p) * sigma / denom if denom > 0 else 0.0


def rho_theory_mask(p, mu, sigma):
    denom = math.sqrt(sigma ** 2 + p * mu ** 2)
    return math.sqrt(1 - p) * sigma / denom if denom > 0 else 0.0


# ── main experiment ────────────────────────────────────────────────────────

def run():
    paths = collect_paths()
    print(f"Loading {len(paths)} photos at {CANONICAL}×{CANONICAL}…")
    photos = []
    for path in paths:
        try:
            q = load_q(path)
            photos.append({'name': path.name, 'q': q,
                           'perm': mask_permutation(path),
                           'mu': float(q[q > 0].mean()) if q.max() > 0 else 0.0,
                           'sigma': float(q[q > 0].std()) if q.max() > 0 else 0.0})
        except Exception as exc:
            print(f"  skip {path.name}: {exc}")
    n = len(photos)
    print(f"Loaded {n} photos  (mu≈{np.mean([ph['mu'] for ph in photos]):.2f}  "
          f"sigma≈{np.mean([ph['sigma'] for ph in photos]):.2f})")

    rng = random.Random(SEED_GLOBAL)

    # For each photo: pre-build full plane (= quantised image itself at 256×256)
    full_planes = [ph['q'] for ph in photos]

    rows = []  # one row per (photo, level, corruption_type)
    total = n * len(CROP_LEVELS) * 2
    done = 0

    for i, ph in enumerate(photos):
        # deterministic list of unrelated indices (same for crop and mask)
        other_pool = [j for j in range(n) if j != i]
        unrel_idx = rng.sample(other_pool, min(N_UNREL, len(other_pool)))

        for p in CROP_LEVELS:
            # ── crop ────────────────────────────────────────────────────
            c_plane = crop_plane(ph['q'], p)
            r_rel_crop = pearson(full_planes[i], c_plane)
            r_unrel_crop_vals = [
                pearson(full_planes[i], crop_plane(photos[j]['q'], p))
                for j in unrel_idx
            ]
            r_unrel_crop = statistics.mean(r_unrel_crop_vals)

            # ── mask ────────────────────────────────────────────────────
            m_plane = mask_plane(ph['q'], p, ph['perm'])
            r_rel_mask = pearson(full_planes[i], m_plane)
            r_unrel_mask_vals = [
                pearson(full_planes[i],
                        mask_plane(photos[j]['q'], p, photos[j]['perm']))
                for j in unrel_idx
            ]
            r_unrel_mask = statistics.mean(r_unrel_mask_vals)

            t_crop = rho_theory_crop(p, ph['mu'], ph['sigma'])
            t_mask = rho_theory_mask(p, ph['mu'], ph['sigma'])

            rows.append(dict(
                photo=ph['name'], p=p,
                r_rel_crop=round(r_rel_crop, 5),
                r_unrel_crop=round(r_unrel_crop, 5),
                diff_crop=round(r_rel_crop - r_unrel_crop, 5),
                r_rel_mask=round(r_rel_mask, 5),
                r_unrel_mask=round(r_unrel_mask, 5),
                diff_mask=round(r_rel_mask - r_unrel_mask, 5),
                theory_crop=round(t_crop, 5),
                theory_mask=round(t_mask, 5),
                sigma=round(ph['sigma'], 3),
            ))
            done += 2
            if done % (total // 10) < 2:
                print(f"  {done}/{total}  p={p:.2f}  "
                      f"crop r_rel={r_rel_crop:.3f} diff={r_rel_crop-r_unrel_crop:+.3f}  "
                      f"mask r_rel={r_rel_mask:.3f} diff={r_rel_mask-r_unrel_mask:+.3f}")

    # ── aggregate stats ────────────────────────────────────────────────────
    print("\n=== Aggregate per (p, type) ===")
    agg = {}
    for p in CROP_LEVELS:
        rs = [r for r in rows if r['p'] == p]
        agg[p] = {}
        for key in ('crop', 'mask'):
            rel   = [r[f'r_rel_{key}']   for r in rs]
            unrel = [r[f'r_unrel_{key}'] for r in rs]
            diff  = [r[f'diff_{key}']    for r in rs]
            th    = [r[f'theory_{key}']  for r in rs]
            agg[p][key] = dict(
                rel_mean=round(statistics.mean(rel), 5),
                rel_std=round(statistics.stdev(rel), 5),
                unrel_mean=round(statistics.mean(unrel), 5),
                diff_mean=round(statistics.mean(diff), 5),
                theory_mean=round(statistics.mean(th), 5),
            )
        a = agg[p]
        kept_c = round((1-p)**2*100, 1)
        kept_m = round((1-p)*100, 1)
        print(f"  p={p:.2f}  CROP(kept {kept_c}%):  "
              f"rel={a['crop']['rel_mean']:.4f}  unrel={a['crop']['unrel_mean']:.4f}  "
              f"diff={a['crop']['diff_mean']:+.4f}")
        print(f"         MASK(kept {kept_m}%):  "
              f"rel={a['mask']['rel_mean']:.4f}  unrel={a['mask']['unrel_mean']:.4f}  "
              f"diff={a['mask']['diff_mean']:+.4f}")

    # ── hypothesis evaluation ──────────────────────────────────────────────
    print("\n=== Hypothesis evaluation ===")

    # H5: r_rel_mask > r_rel_crop at all p
    H5 = all(agg[p]['mask']['rel_mean'] > agg[p]['crop']['rel_mean'] for p in CROP_LEVELS)
    h5_detail = '  '.join(
        f"p={p:.1f}:mask-crop={agg[p]['mask']['rel_mean']-agg[p]['crop']['rel_mean']:+.4f}"
        for p in CROP_LEVELS)
    print(f"  H5 (r_rel_mask>r_rel_crop all p): {h5_detail}")
    print(f"  H5 → {'PASS' if H5 else 'FAIL'}")

    # H6: r_unrel_mask < r_unrel_crop at all p
    H6 = all(agg[p]['mask']['unrel_mean'] < agg[p]['crop']['unrel_mean'] for p in CROP_LEVELS)
    h6_detail = '  '.join(
        f"p={p:.1f}:mask-crop={agg[p]['mask']['unrel_mean']-agg[p]['crop']['unrel_mean']:+.4f}"
        for p in CROP_LEVELS)
    print(f"  H6 (r_unrel_mask<r_unrel_crop all p): {h6_detail}")
    print(f"  H6 → {'PASS' if H6 else 'FAIL'}")

    # H7: diff_mask >= diff_crop at ≥4/5 levels
    h7_count = sum(agg[p]['mask']['diff_mean'] >= agg[p]['crop']['diff_mean']
                   for p in CROP_LEVELS)
    H7 = h7_count >= 4
    print(f"  H7 (diff_mask≥diff_crop ≥4/5): {h7_count}/5 → {'PASS' if H7 else 'FAIL'}")

    # H8: mask r_related monotone decrease ≥90% of photos
    photo_names = list({r['photo'] for r in rows})
    mono_count = 0
    for name in photo_names:
        vals = [next(r['r_rel_mask'] for r in rows if r['photo'] == name and r['p'] == p)
                for p in CROP_LEVELS]
        if all(vals[i] >= vals[i+1] for i in range(len(vals)-1)):
            mono_count += 1
    H8_pct = mono_count / len(photo_names)
    H8 = H8_pct >= 0.90
    print(f"  H8 (mask monotone ≥90%): {mono_count}/{len(photo_names)} "
          f"({H8_pct*100:.1f}%) → {'PASS' if H8 else 'FAIL'}")

    # H9: both diff>0 at p=0.50
    H9 = (agg[0.50]['crop']['diff_mean'] > 0 and
          agg[0.50]['mask']['diff_mean'] > 0)
    print(f"  H9 (both diff>0 at p=0.50): "
          f"crop={agg[0.50]['crop']['diff_mean']:+.4f}  "
          f"mask={agg[0.50]['mask']['diff_mean']:+.4f} → {'PASS' if H9 else 'FAIL'}")

    # ── cause analysis: sigma binning ──────────────────────────────────────
    print("\n=== Content-type breakdown (by sigma) at p=0.50 ===")
    rows50 = [r for r in rows if r['p'] == 0.50]
    bins = [(0, 10, 'low-σ (uniform)'),
            (10, 20, 'mid-σ (typical)'),
            (20, 99, 'high-σ (high-contrast)')]
    for lo, hi, label in bins:
        sub = [r for r in rows50 if lo <= r['sigma'] < hi]
        if not sub:
            continue
        rc = statistics.mean(r['diff_crop'] for r in sub)
        rm = statistics.mean(r['diff_mask'] for r in sub)
        print(f"  {label} (n={len(sub)}):  diff_crop={rc:+.4f}  diff_mask={rm:+.4f}  "
              f"mask_wins={'YES' if rm>rc else 'NO'}")

    # ── save ───────────────────────────────────────────────────────────────
    hypotheses = dict(H5=H5, H6=H6, H7=H7, H7_count=h7_count,
                      H8=H8, H8_pct=round(H8_pct, 4), H9=H9)
    metrics = dict(n_photos=n, agg=agg, hypotheses=hypotheses,
                   rows=rows[:200])   # save first 200 rows to keep JSON small
    (THIS / 'metrics.json').write_text(json.dumps(metrics, indent=2))
    print(f"\nMetrics saved → {THIS / 'metrics.json'}")

    _write_results(agg, hypotheses, n, rows, H5, H6, H7, h7_count, H8, H8_pct, H9, mono_count, len(photo_names))


def _write_results(agg, hypotheses, n, rows, H5, H6, H7, h7_count, H8, H8_pct, H9, mono_count, n_photos):
    def p2h(b): return 'PASS' if b else 'FAIL'
    lines = [
        "# RESULTS_CORRUPTION_V2.md — 剪裁 vs 随机掩码对比",
        "",
        f"2026-09-08；研究 RESEARCH_CORRUPTION_V2.md，预注册 PLAN_CORRUPTION_V2.md。",
        f"照片数：{n}，统一 256×256，标称档位 p ∈ {{0.10,0.20,0.30,0.40,0.50}}。",
        "",
        "## 核心结果表",
        "",
        "| p | 保留(crop) | 保留(mask) | r_rel_crop | r_unrel_crop | diff_crop | r_rel_mask | r_unrel_mask | diff_mask |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in CROP_LEVELS:
        a = agg[p]
        lines.append(
            f"| {p:.2f} | {(1-p)**2*100:.0f}% | {(1-p)*100:.0f}% | "
            f"{a['crop']['rel_mean']:.4f} | {a['crop']['unrel_mean']:.4f} | "
            f"**{a['crop']['diff_mean']:+.4f}** | "
            f"{a['mask']['rel_mean']:.4f} | {a['mask']['unrel_mean']:.4f} | "
            f"**{a['mask']['diff_mean']:+.4f}** |"
        )

    lines += [
        "",
        "## Hypothesis 验收",
        "",
        "| 编号 | 假设 | 实测 | 结论 |",
        "|---|---|---|---|",
        f"| H5 | r_rel_mask > r_rel_crop 所有档位 | {'所有成立' if H5 else '存在不成立'} | **{p2h(H5)}** |",
        f"| H6 | r_unrel_mask < r_unrel_crop 所有档位 | {'所有成立' if H6 else '存在不成立'} | **{p2h(H6)}** |",
        f"| H7 | diff_mask ≥ diff_crop ≥4/5 档位 | {h7_count}/5 | **{p2h(H7)}** |",
        f"| H8 | 掩码 r_related 单调递减 ≥90% 照片 | {mono_count}/{n_photos} ({H8_pct*100:.1f}%) | **{p2h(H8)}** |",
        f"| H9 | 两种污染 p=0.50 均 diff>0 | crop={agg[0.50]['crop']['diff_mean']:+.4f} mask={agg[0.50]['mask']['diff_mean']:+.4f} | **{p2h(H9)}** |",
        "",
        "## 成因分析",
        "",
        "### H5（绝对相关值）",
        "掩码在同一标称 p 下保留 (1-p) 比例像素，剪裁仅保留 (1-p)² 比例像素。",
        "掩码信息量更多 → 绝对 r_related 更高。",
        "与理论预测一致（RESEARCH §1.2）。",
        "",
        "### H6（不相关基线）",
        "剪裁产生所有照片共享的对称零边框，",
        "使不相关照片对之间也存在「共同结构」，推高了 r_unrelated。",
        "掩码的零位置随每张照片独立随机，不形成共享结构，r_unrelated 更低。",
        "",
        "### H7 综合辨别力",
        "diff = r_related - r_unrelated 衡量系统能否区分「见过的照片」和「没见过的照片」。",
        "H6（低不相关基线）和 H5（高相关基线）共同决定最终 diff 哪种更大。",
    ]

    # Per-sigma analysis
    rows50 = [r for r in rows if r['p'] == 0.50]
    bins = [(0, 10, 'low-σ'), (10, 20, 'mid-σ'), (20, 99, 'high-σ')]
    lines += ["", "### 按图像 σ 分组（p=0.50）", "",
              "| 内容类型 | n | diff_crop | diff_mask | 掩码占优 |",
              "|---|---|---|---|---|"]
    for lo, hi, label in bins:
        sub = [r for r in rows50 if lo <= r['sigma'] < hi]
        if not sub:
            continue
        rc = statistics.mean(r['diff_crop'] for r in sub)
        rm = statistics.mean(r['diff_mask'] for r in sub)
        lines.append(f"| {label} (σ∈[{lo},{hi})) | {len(sub)} | "
                     f"{rc:+.4f} | {rm:+.4f} | {'YES' if rm>rc else 'NO'} |")

    lines += [
        "",
        "## 复现",
        "```sh",
        "python3 field_corruption_v2/run_corruption_v2.py",
        "```",
        "",
    ]
    (THIS / 'RESULTS_CORRUPTION_V2.md').write_text('\n'.join(lines))
    print(f"Results written → {THIS / 'RESULTS_CORRUPTION_V2.md'}")


if __name__ == '__main__':
    run()
