# SmartCoder 文件索引

> 快速定位任何文件的用途。新成员请先读 [TEACHING.md](./TEACHING.md)，规则请看 [AGENTS.md](./AGENTS.md)。

---

## 核心入口

| 文件 | 说明 |
|---|---|
| [TEACHING.md](./TEACHING.md) | **新成员入门手册**：数学基础、手算 base case、代码阅读、练习题 |
| [README.md](./README.md) | 项目目标、完整数学推导、版本历史 |
| [AGENTS.md](./AGENTS.md) | **贡献规则**：每次修改前必读，研究门槛要求 |

---

## 实验版本线（时间顺序）

| 版本 | 研究 | 计划 | 结果 | 运行入口 |
|---|---|---|---|---|
| v0.1–v0.2 一维 base case | [RESEARCH.md](./RESEARCH.md) | [MVP_SPEC.md](./MVP_SPEC.md) | MVP_SPEC.md §3 | `verify_base_case.py` |
| v0.3 二维照片存储 | [RESEARCH_2D.md](./RESEARCH_2D.md) | [PLAN_2D.md](./PLAN_2D.md) | [RESULTS_2D.md](./RESULTS_2D.md) | `run_photo_demo.py` |
| v0.4 动态扩域 + 按需 RAM | [RESEARCH_STREAMING.md](./RESEARCH_STREAMING.md) | [PLAN_STREAMING.md](./PLAN_STREAMING.md) | [RESULTS_STREAMING.md](./RESULTS_STREAMING.md) | `run_stream_demo.py` |
| v0.5 per-residue 压缩 | [RESEARCH_COMPRESSION.md](./RESEARCH_COMPRESSION.md) | [PLAN_COMPRESSION.md](./PLAN_COMPRESSION.md) | [RESULTS_COMPRESSION.md](./RESULTS_COMPRESSION.md) | `per_residue_delta_zstd/run_compression_demo.py` |
| Direction 1 v1 裁剪遮挡 | [field_crop_recall/RESEARCH_FIELD_MI.md](./field_crop_recall/RESEARCH_FIELD_MI.md) | [field_crop_recall/PLAN_FIELD_CROP.md](./field_crop_recall/PLAN_FIELD_CROP.md) | [field_crop_recall/RESULTS_FIELD_CROP.md](./field_crop_recall/RESULTS_FIELD_CROP.md) | `field_crop_recall/run_crop_recall.py` |
| Direction 1 v2 裁剪+随机掩码 | [field_corruption_v2/RESEARCH_CORRUPTION_V2.md](./field_corruption_v2/RESEARCH_CORRUPTION_V2.md) | [field_corruption_v2/PLAN_CORRUPTION_V2.md](./field_corruption_v2/PLAN_CORRUPTION_V2.md) | [field_corruption_v2/RESULTS_CORRUPTION_V2.md](./field_corruption_v2/RESULTS_CORRUPTION_V2.md) | `field_corruption_v2/run_corruption_v2.py` |
| Direction 2 s-槽耦合容量 | [coupling_capacity/RESEARCH_COUPLING.md](./coupling_capacity/RESEARCH_COUPLING.md) | [coupling_capacity/PLAN_COUPLING.md](./coupling_capacity/PLAN_COUPLING.md) | coupling_capacity/metrics.json | `coupling_capacity/run_coupling_exp.py` |

---

## 核心源代码

| 文件 | 功能 |
|---|---|
| `field_factory.py` | 素数序列生成、CRT 权重计算（不要修改） |
| `stream_memory.py` | v0.4 分块存储引擎（主实现） |
| `per_residue_delta_zstd/stream_memory_cmp.py` | v0.5 压缩版存储引擎 |
| `per_residue_delta_zstd/field_factory.py` | field_factory.py 的副本（不修改） |

---

## 数据与资源

| 路径 | 说明 |
|---|---|
| `data/photos/` | 12 张原始测试照片（可通过 `data/sources.json` 重新下载） |
| `data/bench_photos/` | 368 张 Picsum 基准测试照片（运行 `per_residue_delta_zstd/download_bench_photos.py` 下载） |
| `data/sources.json` | 6 张原始照片的来源清单 |
| `data/sources_expanded.json` | 另外 6 张照片的来源清单 |

---

## 实验产出（artifacts）

| 路径 | 说明 |
|---|---|
| `artifacts/photo_demo/` | v0.3 demo 结果（bundle + comparison.png） |
| `artifacts/stream_demo/` | v0.4 demo 结果（tiles + recovered） |
| `artifacts/compression_demo/` | v0.5 压缩 demo 结果 |

---

## 后续研究方向登记

见 `/memories/repo/future_directions.md`（在 GitHub Copilot 的记忆系统中，不在仓库里）。

已登记方向：
- **方向 1**（进行中）：域间相关性 → 裁剪/掩码遮挡实验（v1、v2 已完成）
- **方向 2**（进行中）：$s$-槽耦合容量（已完成）
- **方向 3**（待探索）：base 动力学 / Hopfield 类比
- **「一个域能还原」的真正含义**（待形式化）：Kolmogorov 复杂性框架

---

## 常见问题

**Q：要新增一个方向，从哪里开始？**  
A：读 AGENTS.md 第一条，再看 TEACHING.md 第 7 章。

**Q：验证某个 base case 的代码在哪？**  
A：`verify_base_case.py`（v0.1–v0.2），或各实验目录的 `verify_*` 文件。

**Q：为什么有些照片比 base 更小（bytes）？**  
A：base 使用 Python 大整数，每 cell 约 $1.5K$ 字节（$K$ = 域数）。照片是 JPEG/PNG，有各自的压缩。Base 的目的不是节省空间，而是研究这种共享结构能做什么。
