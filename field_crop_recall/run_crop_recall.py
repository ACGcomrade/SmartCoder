"""
Experiment: Crop-level residue plane correlation (Direction 1, base case)

For each of 12 photos, we:
  1. Build the full-image residue plane (quantised pixels, zero-padded to canvas).
  2. Build 5 cropped residue planes at p in {0.10, 0.20, 0.30, 0.40, 0.50}.
     Crop = center crop keeping (1-p)H x (1-p)W pixels; placed at ORIGINAL
     canvas coordinates (aligned), remainder zero.
  3. Measure Pearson r between full and each crop level ("related" pair).
  4. Measure Pearson r between the full image and every OTHER photo's crop
     at the same level ("unrelated" baseline).
  5. Compare with the i.i.d. theoretical prediction.
  6. Log everything and write RESULTS_FIELD_CROP.md.

Usage:
    python3 field_crop_recall/run_crop_recall.py
"""
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


# ── helpers ──────────────────────────────────────────────────────────────────

def load_sources():
    s = json.loads((ROOT / 'data' / 'sources.json').read_text())
    s += json.loads((ROOT / 'data' / 'sources_expanded.json').read_text())
    return s


def load_rgb(path):
    with Image.open(path) as img:
        return np.array(ImageOps.exif_transpose(img).convert('RGB'))


def quantize(rgb):
    """Map uint8 → 6-bit (divide by 4); same rounding as SmartCoder."""
    return (rgb // 4).astype(np.uint8)


def center_crop(img_q, p):
    """
    Center crop at fraction p (remove p from each side).
    Returns (cropped_array, y0, x0) where (y0, x0) is the canvas offset.
    """
    h, w = img_q.shape[:2]
    new_h = max(1, int(round(h * (1 - p))))
    new_w = max(1, int(round(w * (1 - p))))
    y0 = (h - new_h) // 2
    x0 = (w - new_w) // 2
    return img_q[y0:y0 + new_h, x0:x0 + new_w], y0, x0


def make_plane(img_q, canvas_H, canvas_W, y0=0, x0=0):
    """Place quantised image on zero canvas at (y0, x0). Returns float64."""
    plane = np.zeros((canvas_H, canvas_W, 3), dtype=np.float64)
    h, w = img_q.shape[:2]
    h_put = min(h, canvas_H - y0)
    w_put = min(w, canvas_W - x0)
    if h_put > 0 and w_put > 0:
        plane[y0:y0 + h_put, x0:x0 + w_put] = img_q[:h_put, :w_put]
    return plane


def pearson(x, y):
    """Pearson r between two arrays of any shape (flattened)."""
    xf, yf = x.ravel(), y.ravel()
    xm, ym = xf - xf.mean(), yf - yf.mean()
    denom = math.sqrt(float(np.dot(xm, xm)) * float(np.dot(ym, ym)))
    return float(np.dot(xm, ym)) / denom if denom > 0 else 0.0


def rho_theory(p, mu, sigma):
    """i.i.d. theoretical prediction (RESEARCH_FIELD_MI.md §2.2)."""
    if sigma <= 0:
        return 0.0
    denom = math.sqrt(sigma ** 2 + mu ** 2 * p * (2 - p))
    return (1 - p) * sigma / denom if denom > 0 else 0.0


# ── main ─────────────────────────────────────────────────────────────────────

CROP_LEVELS = [0.10, 0.20, 0.30, 0.40, 0.50]


def run():
    sources = load_sources()
    assert len(sources) == 12, f"Expected 12 photos, got {len(sources)}"

    # Load all photos (quantised)
    photos = []
    for s in sources:
        rgb = load_rgb(ROOT / 'data' / 'photos' / s['file'])
        photos.append({'name': s['name'], 'q': quantize(rgb),
                       'h': rgb.shape[0], 'w': rgb.shape[1]})

    canvas_H = max(ph['h'] for ph in photos)
    canvas_W = max(ph['w'] for ph in photos)
    print(f"Canvas: {canvas_H} x {canvas_W}  ({len(photos)} photos)")

    # Full-image planes
    full_planes = [make_plane(ph['q'], canvas_H, canvas_W) for ph in photos]

    # Stats for theoretical prediction
    all_vals = np.concatenate([p.ravel() for p in full_planes if p.max() > 0])
    mu_global = float(all_vals[all_vals > 0].mean())  # exclude zero-padding
    sigma_global = float(all_vals[all_vals > 0].std())
    print(f"Pixel stats (non-zero): mu={mu_global:.2f}  sigma={sigma_global:.2f}")

    log_rows = []   # one dict per (photo, crop_level)
    results = {}    # photo_name -> {crop_level -> {related, unrelated_mean, ...}}

    for i, ph in enumerate(photos):
        results[ph['name']] = {}
        q_full = ph['q']
        mu_i = float(q_full[q_full > 0].mean()) if q_full.max() > 0 else mu_global
        sigma_i = float(q_full[q_full > 0].std()) if q_full.max() > 0 else sigma_global

        for p in CROP_LEVELS:
            crop_q, y0, x0 = center_crop(q_full, p)
            plane_crop = make_plane(crop_q, canvas_H, canvas_W, y0, x0)

            r_related = pearson(full_planes[i], plane_crop)
            r_theory = rho_theory(p, mu_i, sigma_i)

            # Unrelated baseline: same crop level applied to every OTHER photo,
            # correlated with THIS photo's full plane
            unrel_rs = []
            for j, other in enumerate(photos):
                if j == i:
                    continue
                other_crop_q, oy0, ox0 = center_crop(other['q'], p)
                other_plane = make_plane(other_crop_q, canvas_H, canvas_W, oy0, ox0)
                unrel_rs.append(pearson(full_planes[i], other_plane))

            r_unrel_mean = statistics.mean(unrel_rs)
            r_unrel_std = statistics.stdev(unrel_rs)
            diff = r_related - r_unrel_mean

            row = dict(
                photo=ph['name'],
                crop_p=p,
                kept_frac=round((1 - p) ** 2, 4),
                r_related=round(r_related, 4),
                r_theory=round(r_theory, 4),
                r_unrel_mean=round(r_unrel_mean, 4),
                r_unrel_std=round(r_unrel_std, 4),
                diff=round(diff, 4),
                crop_h=crop_q.shape[0],
                crop_w=crop_q.shape[1],
            )
            log_rows.append(row)
            results[ph['name']][p] = row

            print(f"  {ph['name']:25s} p={p:.2f}  "
                  f"r_rel={r_related:+.4f}  r_unrel={r_unrel_mean:+.4f}  "
                  f"diff={diff:+.4f}  theory={r_theory:.4f}")

    # ── aggregate statistics ──────────────────────────────────────────────────
    print("\n=== Group statistics per crop level ===")
    agg = {}
    for p in CROP_LEVELS:
        rows_p = [r for r in log_rows if r['crop_p'] == p]
        rel   = [r['r_related'] for r in rows_p]
        unrel = [r['r_unrel_mean'] for r in rows_p]
        diff  = [r['diff'] for r in rows_p]
        th    = [r['r_theory'] for r in rows_p]
        agg[p] = dict(
            p=p, kept_pct=round((1-p)**2*100, 1),
            rel_mean=round(statistics.mean(rel), 4),
            rel_std=round(statistics.stdev(rel), 4),
            unrel_mean=round(statistics.mean(unrel), 4),
            diff_mean=round(statistics.mean(diff), 4),
            theory_mean=round(statistics.mean(th), 4),
        )
        a = agg[p]
        print(f"  p={p:.2f} ({a['kept_pct']:4.1f}% pixels): "
              f"rel={a['rel_mean']:.4f}±{a['rel_std']:.4f}  "
              f"unrel={a['unrel_mean']:.4f}  diff={a['diff_mean']:+.4f}  "
              f"theory={a['theory_mean']:.4f}")

    # ── H1–H4 evaluation ─────────────────────────────────────────────────────
    print("\n=== Hypothesis evaluation ===")

    # H1: ≥10/12 photos show monotone decrease
    h1_count = 0
    for ph in photos:
        vals = [results[ph['name']][p]['r_related'] for p in CROP_LEVELS]
        if all(vals[i] >= vals[i+1] for i in range(len(vals)-1)):
            h1_count += 1
    H1 = 'PASS' if h1_count >= 10 else 'FAIL'
    print(f"  H1 (monotone decrease ≥10/12): {h1_count}/12 → {H1}")

    # H2: diff > 0 for all 5 crop levels
    H2 = 'PASS' if all(agg[p]['diff_mean'] > 0 for p in CROP_LEVELS) else 'FAIL'
    diffs_str = '  '.join(f"p={p:.1f}:{agg[p]['diff_mean']:+.4f}" for p in CROP_LEVELS)
    print(f"  H2 (related > unrelated all levels): {diffs_str} → {H2}")

    # H3: measured > theory for all levels
    H3 = 'PASS' if all(agg[p]['rel_mean'] > agg[p]['theory_mean'] for p in CROP_LEVELS) else 'FAIL'
    print(f"  H3 (measured > theory): {H3}")

    # H4: total drop > 0.10
    drop = agg[CROP_LEVELS[0]]['rel_mean'] - agg[CROP_LEVELS[-1]]['rel_mean']
    H4 = 'PASS' if drop > 0.10 else 'FAIL'
    print(f"  H4 (drop p=0.1→0.5 > 0.10): {drop:.4f} → {H4}")

    # ── cause analysis ────────────────────────────────────────────────────────
    print("\n=== Cause analysis ===")

    # Zero-padding effect: theoretical prediction vs measured gap
    for p in CROP_LEVELS:
        a = agg[p]
        gap = a['rel_mean'] - a['theory_mean']
        zero_frac = 1 - (1 - p) ** 2
        print(f"  p={p:.2f}: zero_fraction={zero_frac:.2f}  "
              f"measured-theory={gap:+.4f}  "
              f"(positive gap = spatial structure contribution)")

    # Per-photo breakdown: which content types hold correlation best?
    print("\n  Per-photo r_related at p=0.50:")
    p50 = [(ph['name'], results[ph['name']][0.50]['r_related']) for ph in photos]
    for name, r in sorted(p50, key=lambda x: -x[1]):
        print(f"    {name:25s}: {r:.4f}")

    # ── save outputs ──────────────────────────────────────────────────────────
    out_dir = THIS
    metrics = dict(
        canvas=(canvas_H, canvas_W),
        n_photos=len(photos),
        mu_global=round(mu_global, 3),
        sigma_global=round(sigma_global, 3),
        aggregate=agg,
        hypotheses=dict(H1=H1, H2=H2, H3=H3, H4=H4, H1_count=h1_count, H4_drop=round(drop, 4)),
        rows=log_rows,
    )
    (out_dir / 'metrics.json').write_text(json.dumps(metrics, indent=2))
    print(f"\nMetrics saved to {out_dir / 'metrics.json'}")

    _write_results_md(metrics, agg, H1, H2, H3, H4, h1_count, drop)
    return metrics


def _write_results_md(metrics, agg, H1, H2, H3, H4, h1_count, drop):
    lines = ["# RESULTS_FIELD_CROP.md — 裁剪级别与余数平面相关性\n",
             f"2026-09-08；研究 RESEARCH_FIELD_MI.md，预注册 PLAN_FIELD_CROP.md。\n",
             f"\nCanvas: {metrics['canvas'][0]}×{metrics['canvas'][1]}，"
             f"μ={metrics['mu_global']:.2f}，σ={metrics['sigma_global']:.2f}\n",
             "\n## 群体平均相关系数\n",
             "| 裁剪比例 p | 保留像素% | r_related | r_unrelated | diff | r_theory |",
             "|---|---|---|---|---|---|"]
    for p in CROP_LEVELS:
        a = agg[p]
        lines.append(f"| {p:.2f} | {a['kept_pct']:.1f}% | "
                     f"{a['rel_mean']:.4f}±{a['rel_std']:.4f} | "
                     f"{a['unrel_mean']:.4f} | "
                     f"{a['diff_mean']:+.4f} | "
                     f"{a['theory_mean']:.4f} |")

    lines += ["\n## Hypothesis 验收\n",
              "| 编号 | 假设 | 阈值 | 实测 | 结论 |",
              "|---|---|---|---|---|",
              f"| H1 | r_related 单调递减 | ≥10/12 | {h1_count}/12 | **{H1}** |",
              f"| H2 | related > unrelated 所有档位 | diff>0 全部 | "
              f"{'全部>0' if H2=='PASS' else '存在≤0'} | **{H2}** |",
              f"| H3 | 实测 > 理论（空间结构贡献） | 全部 | "
              f"{'全部满足' if H3=='PASS' else '存在不满足'} | **{H3}** |",
              f"| H4 | p=0.1→0.5 降幅 > 0.10 | >0.10 | {drop:.4f} | **{H4}** |",
              ]

    lines += ["\n## 成因分析\n",
              "### 零填充效应",
              "随裁剪比例 p 增大，canvas 中零区域比例为 $1-(1-p)^2$：",
              "",
              "| p | 零区域比例 | 实测均值 | 理论均值 | 超出量（空间结构贡献） |",
              "|---|---|---|---|---|"]
    for p in CROP_LEVELS:
        a = agg[p]
        zf = 1 - (1 - p) ** 2
        gap = a['rel_mean'] - a['theory_mean']
        lines.append(f"| {p:.2f} | {zf:.2f} | {a['rel_mean']:.4f} | "
                     f"{a['theory_mean']:.4f} | {gap:+.4f} |")

    lines += ["",
              "理论公式假设 i.i.d. 像素值。实测高于理论的部分来自自然图像的空间相关结构",
              "（同一照片的相邻像素值接近，零填充区域被跨像素相关性部分补偿）。",
              "",
              "### 内容类型对 p=0.50 相关性的影响",
              "",
              "结构型内容（纹理、天文图）与平滑内容（人像、动物）在高裁剪比例下的相关性差异",
              "反映了像素空间方差 σ 的差异：σ 高的照片，理论 ρ 更高（公式分子 (1-p)σ 更大）。",
              ]

    # Per-photo table at p=0.50
    lines += ["",
              "| 照片 | r_related (p=0.50) |",
              "|---|---|"]
    rows50 = sorted(
        [(r['photo'], r['r_related']) for r in metrics['rows'] if r['crop_p'] == 0.50],
        key=lambda x: -x[1]
    )
    for name, r in rows50:
        lines.append(f"| {name} | {r:.4f} |")

    lines += ["",
              "## 复现",
              "```sh",
              "python3 field_crop_recall/run_crop_recall.py",
              "```",
              ""]

    (THIS / 'RESULTS_FIELD_CROP.md').write_text('\n'.join(lines))
    print(f"Results written to {THIS / 'RESULTS_FIELD_CROP.md'}")


if __name__ == '__main__':
    run()
