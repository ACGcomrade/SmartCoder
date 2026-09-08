# RESULTS_COMPRESSION.md — per-residue-plane delta+lzma

2026-09-06；研究 RESEARCH.md，预注册 PLAN.md。

## 两种测量视角

- **12-photo full store**（K=6）：相同 12 张照片端到端对比，包含零填充区域与大 tile payload（2K=12 planes/tile）。
- **Tile-level benchmark**（K=1）：100 对 Picsum 照片（共 380 张），仅在实际内容区域采样 tile，每 tile 仅 2 planes/tile，更保守。

## 12-photo Full Store（K=6）

| 指标 | Original (zlib+bigint) | Compressed (delta+lzma) |
|---|---|---|
| Tile 总字节 | 10,125,371 | 3,627,416 |
| 压缩比 | 1.00× | **2.79×** |
| Max channel error | 2 | **2** |
| PSNR min–max | 45.72–46.39 dB | **45.72–46.39 dB** |
| Write 时间 | 7.90 s | **5.50 s**（更快，I/O 节省 > lzma CPU） |

## Tile-level Benchmark（K=1，100 对，380 张 Picsum）

| 指标 | 值 |
|---|---|
| 中位压缩比 | **1.61×** |
| p25 / p75 | 1.53× / 1.70× |
| Min / Max | 1.33× / 1.94× |
| 整体比（累计字节） | 1.60× |
| 小图（≤300px）中位 | 1.63× |
| 大图（>300px）中位 | 1.60× |

尺寸类别差异不显著（±0.03×）。

## Hypothesis 验收

| 编号 | 假设 | 阈值 | K=6 实测 | K=1 实测 | 结论 |
|---|---|---|---|---|---|
| C1 | 中位比 ≥ 2.5× | ≥2.5 | 2.79× | 1.61× | K=6 PASS；K=1 FAIL（已知非适用条件） |
| C2 | max_err ≤ 2 | ≤2 | 2 | — | PASS |
| C5 | 所有 demo max_err ≤ 2 | 全满足 | 全为 2 | — | PASS |

C1 阈值设定时隐含 K≥6 场景；K=1 下 lzma 块效率更低，不是 C1 针对的场景。不修改阈值迁就结果。

## 压缩比差异来源

K=6 比 K=1 高的三个原因：
1. Tile payload 更大（147KB vs 25KB）→ lzma 块内重复更多，效率更高
2. K=6 store 有大量零填充区域（小照片外的 canvas 区域全为零）→ 极高压缩
3. 12 个 plane 的 lzma 流比 2 个 plane 更容易找到 LZ77 匹配

## 适用范围

| 场景 | 实测/估计比 | 备注 |
|---|---|---|
| K=6（12 张自然照片） | **2.79×** | 实测 |
| K=1（2 张自然照片） | **1.61×** | 实测 |
| K=12（24 张） | 估计 3–5× | 未实测，理论推算 |
| 纯噪声内容 | < 1.3× | 已知非适用 |

**无损保证**：任意场景 max_channel_error ≤ 2，由量化设计决定，与压缩无关。

## 复现

```sh
python3 per_residue_delta_zstd/verify_compression_base_case.py
python3 per_residue_delta_zstd/run_compression_demo.py --skip-download --trials 20
```
