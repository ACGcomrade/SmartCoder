# SmartCoder 文件索引

> 新成员从 [TEACHING.md](./TEACHING.md) 开始；贡献规则见 [AGENTS.md](./AGENTS.md)。

---

## 项目根目录（4 个核心文件）

| 文件 | 用途 |
|---|---|
| [README.md](./README.md) | 项目目标、完整数学推导、版本历史 |
| [AGENTS.md](./AGENTS.md) | 贡献规则：每次修改前必读 |
| [TEACHING.md](./TEACHING.md) | 新成员入门手册（数学基础 + 手算例子 + 练习题） |
| [INDEX.md](./INDEX.md) | 本文件：所有文档的导航图 |

---

## docs/ — 版本化研究记录

每个版本都有 `RESEARCH.md → PLAN.md → RESULTS.md` 的追溯链。

```
docs/
├── v1_base_case/         v0.1–v0.2：一维 base case，构造 A/B 验证
│   ├── RESEARCH.md       数学来源与推导
│   └── MVP_SPEC.md       最小实现规格 + 手算复现
│
├── v3_photo_2d/          v0.3：6 张照片写入同一个二维 base
│   ├── RESEARCH.md       二维 CRT 推导
│   ├── PLAN.md           预注册假设 H1–H7
│   └── RESULTS.md        实测结果（PSNR 46.33–46.39 dB）
│
├── v4_streaming/         v0.4：12 张照片 + 动态扩域 + 按需 RAM
│   ├── RESEARCH.md       流式分块研究
│   ├── PLAN.md           预注册假设 S1–S7
│   └── RESULTS.md        实测结果（ROI 峰值 RAM 34.55 MiB）
│
└── v5_compression/       v0.5：余数平面分离 + delta+lzma 压缩
    ├── RESEARCH.md       压缩策略推导
    ├── PLAN.md           预注册假设 C1–C6
    └── RESULTS.md        实测结果（K=6 压缩比 2.79×）
```

---

## 实验目录 — 方向性研究

每个目录内部也有 `RESEARCH.md → PLAN.md → RESULTS.md` 链。

### field_crop_recall/  ← Direction 1 v1

```
field_crop_recall/
├── RESEARCH.md     理论推导：Pearson ρ(p) 公式，手算 base case
├── PLAN.md         预注册假设 H1–H4
├── RESULTS.md      实测结果（12 张照片，H1–H4 全 PASS）
└── run_crop_recall.py
```

### field_corruption_v2/  ← Direction 1 v2

```
field_corruption_v2/
├── RESEARCH.md     随机掩码 vs 裁剪的理论对比
├── PLAN.md         预注册假设 H5–H9
├── RESULTS.md      实测结果（380 张，掩码辨别力 1.79× 优于裁剪）
└── run_corruption_v2.py
```

### coupling_capacity/  ← Direction 2

```
coupling_capacity/
├── RESEARCH.md     s-槽耦合理论，错误传播分析
├── PLAN.md         预注册假设 H_A1–H_A5
├── metrics.json    实测数据
└── run_coupling_exp.py
```

### per_residue_delta_zstd/  ← v0.5 实现

```
per_residue_delta_zstd/
├── field_factory.py           (原样副本)
├── stream_memory_cmp.py       压缩版存储引擎
├── verify_compression_base_case.py
├── download_bench_photos.py
├── bench_compress.py
└── run_compression_demo.py
```

---

## 核心源代码（根目录）

| 文件 | 功能 |
|---|---|
| `field_factory.py` | 素数生成 + CRT 权重（不要修改） |
| `stream_memory.py` | v0.4 分块存储引擎 |
| `verify_base_case.py` | 手算 base case 的自动验证 |
| `run_stream_demo.py` | 12 张照片的端到端演示 |
| `run_photo_demo.py` | 6 张照片的 v0.3 演示 |

---

## 数据目录

| 路径 | 说明 |
|---|---|
| `data/photos/` | 12 张原始测试照片 |
| `data/bench_photos/` | 368 张 Picsum 基准测试照片 |
| `data/sources.json` | 前 6 张照片来源 |
| `data/sources_expanded.json` | 后 6 张照片来源 |

---

## 运行命令速查

```bash
python3 verify_base_case.py                        # 手算验证（<1秒）
python3 run_stream_demo.py                         # v0.4 主演示
python3 field_crop_recall/run_crop_recall.py       # Direction 1 v1
python3 field_corruption_v2/run_corruption_v2.py   # Direction 1 v2
python3 coupling_capacity/run_coupling_exp.py      # Direction 2
python3 per_residue_delta_zstd/run_compression_demo.py --skip-download  # v0.5
```
