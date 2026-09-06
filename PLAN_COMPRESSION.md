# PLAN_COMPRESSION.md — 预注册：per-residue-plane delta+lzma 压缩

2026-09-06；前置研究 RESEARCH_COMPRESSION.md。实现目录：`per_residue_delta_zstd/`。

## 实现策略

**策略名**：`per_residue_delta_zstd`（实际 Python stdlib 使用 lzma；名称保留 zstd 以标识后期可替换位置）

**核心变化**：将每个 tile 的存储从"大整数字节序列 + zlib"改为"2K 个 uint8 余数平面（行 delta 过滤）+ lzma"。编码接口保持与原 StreamMemory 兼容。不修改 field_factory.py。

## Hypothesis（可证伪）

| 编号 | 假设 | 指标 | 验收阈值 | 失败条件 |
|---|---|---|---|---|
| C1 | 中位 tile 压缩比 ≥ 2.5× | compressed_bytes / new_bytes，中位数 | ≥ 2.5 | < 2.5 |
| C2 | 精确量化重建 | max_channel_error | ≤ 2（与 v0.4 相同） | > 2 |
| C3 | 平滑内容（PSNR > 46 dB 原始）压缩比 ≥ 3× | per-photo ratio 子集 | ≥ 3.0 | < 3.0 |
| C4 | 噪声/细粒度内容（Gravel/Brick 类）压缩比 ≥ 1.5× | per-photo ratio 子集 | ≥ 1.5 | < 1.5 |
| C5 | 任意尺寸/纵横比 300+ 张测试，C2 全部满足 | max_channel_error × N张 | 全为 0（精确量化）| 任意一张 > 0 |
| C6 | 格式扩域：append_pair 后旧 tile 仍可精确读 | 旧域 max_channel_error | ≤ 2 | > 2 |

阈值依据：C1/C3/C4 来自 §2.3 推论（PNG Sub 滤波 + entropy coding 文献典型值 1.5–3×）；C2/C5 继承 v0.4 量化设计保证；C6 来自 §2.1 命题 C1 的零初始化等价性。若 C1/C3/C4 失败，报告实测值及可能原因（噪声内容比例过高，或 lzma 对该数据特征不适用），不修改阈值迁就数据。

## 输入约束

- 照片入库仍须成对（保持域数 = N/2 的硬性规则）
- 量化精度 b=6，Q=64，不变
- tile 大小 T=64（与原实现相同）
- delta 滤波：Sub（行水平差分），第一列 delta = 原值（前方虚拟值=0）
- delta 存为 uint8（模 256），重建时模 64 接受（值域 [0,64) 保证 delta 模 64 精确）

## 实现文件列表

```
per_residue_delta_zstd/
  field_factory.py          # 原样复制，不修改
  stream_memory_cmp.py      # 修改：新 codec=2，per-plane 格式
  verify_compression_base_case.py  # 手算验证：K=2，3 cells
  download_bench_photos.py  # 下载 COCO val2017 子集（300+ 张）
  bench_compress.py         # 对比两个实现的 tile 大小、速度、PSNR
  run_compression_demo.py   # 完整 demo：12 张已有图 + 300+ 张下载图
```

## 报告格式

最终输出 RESULTS_COMPRESSION.md，分别报告：
- 每张照片的 PSNR、压缩比
- 按内容类型（平滑/纹理/噪声）分类统计
- 按图像尺寸（小/中/大）分类统计
- 总 tile 字节数对比
- 读写时间对比
- H-C1 至 H-C6 逐条通过/失败
