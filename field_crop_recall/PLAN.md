# PLAN_FIELD_CROP.md — 预注册：裁剪级别与余数平面相关性实验

2026-09-08；前置研究 RESEARCH.md。

## 实验设置

- 照片来源：12 张已有照片（data/photos/），涵盖人像、动物、航天、天文、纹理等内容
- 裁剪档位：$p \in \{0.10, 0.20, 0.30, 0.40, 0.50\}$（center crop，保留 $(1-p)^2$ 比例的像素）
- 不 resize 回原尺寸；crop 在 canvas 中 aligned 放置（保持原坐标，四周补零）
- 基线：每张照片与其他11张照片在相同裁剪级别下的平均相关（不相关对）
- 重复测量：对每张照片独立计算，报告均值 ± std（n=12）

## Hypothesis（可证伪）

| 编号 | 假设 | 指标 | 验收阈值 | 失败条件 |
|---|---|---|---|---|
| H1 | $\rho_{\text{related}}$ 随 $p$ 单调递减 | 12 张照片各自 $\rho(p)$ 曲线斜率符号 | ≥ 10/12 照片呈单调趋势 | < 10/12 |
| H2 | $\rho_{\text{related}}(p) > \rho_{\text{unrelated}}(p)$，对所有 $p$ | difference = related − unrelated 均值 | difference > 0 for all 5 crop levels | 任意一个 $p$ 差值 ≤ 0 |
| H3 | 实测 $\rho$ > 理论 $\rho_{\text{theory}}(p)$ | 实测均值 vs 公式预测 | 实测 > 理论值（由空间结构解释） | 实测 ≤ 理论值 |
| H4 | $\rho(p=0.1) - \rho(p=0.5) > 0.1$ | related 曲线的总降幅 | > 0.10 | ≤ 0.10 |

所有阈值在运行前锁定，不得事后修改。

## 实现文件

```
field_crop_recall/
  RESEARCH.md    ← 已完成
  PLAN_FIELD_CROP.md      ← 本文件
  run_crop_recall.py      ← 端到端实验（含照片准备、计算、日志、结论）
  RESULTS.md   ← 运行后写入
```

## 报告格式

RESULTS.md 中分别报告：
- 每张照片在每个裁剪档位的 $\rho_{\text{related}}$ 与 $\rho_{\text{unrelated}}$
- 群体均值曲线与理论预测曲线对比
- H1–H4 逐条 PASS/FAIL 及实测值
- 成因分析：零填充效应、空间结构贡献、内容类型差异
