# 研究：随机像素抹除 vs 剪裁对余数平面相关性的影响

检索日 2026-09-08。扩展于 field_crop_recall/RESEARCH_FIELD_MI.md。前置数学已在 v1 建立；本文件仅补充随机抹除的新推导和比较框架。

## 1. 新元素的理论推导

### 1.1 随机掩码模型

设原始量化平面 $X \in [0,63]^{H \times W \times 3}$（均值 $\mu$，方差 $\sigma^2$）。

**随机掩码**（masking rate $p$，即抹除 $p$ 比例的像素）：

$$Y_{\text{mask}}[i] = \begin{cases} X[i] & \text{w.p. } (1-p) \\ 0 & \text{w.p. } p \end{cases}$$

逐像素独立，使用固定随机排列（nested 结构）。

**协方差**：

$$\text{Cov}(X, Y_{\text{mask}}) = (1-p)\sigma^2$$

**$Y_{\text{mask}}$ 的方差**：

$$\text{Var}(Y_{\text{mask}}) = (1-p)(\sigma^2 + p\mu^2)$$

**Pearson 相关**：

$$\boxed{\rho_{\text{mask}}(p) = \frac{\sqrt{1-p}\cdot\sigma}{\sqrt{\sigma^2 + p\mu^2}}}$$

### 1.2 剪裁 vs 掩码的理论对比

$$\rho_{\text{crop}}(p) = \frac{(1-p)\,\sigma}{\sqrt{\sigma^2 + \mu^2 p(2-p)}}$$

同一 $p$ 下保留的像素数：
- 剪裁：$(1-p)^2 n$（面积比例）
- 掩码：$(1-p) n$（线性比例）

因此 $\rho_{\text{mask}}$ vs $\rho_{\text{crop}}$ 的大小关系由参数决定：

对 $\mu=22, \sigma=17$（v1 实测值）：

| $p$ | 剪裁保留像素 | 掩码保留像素 | $\rho_{\text{crop}}^{\text{theory}}$ | $\rho_{\text{mask}}^{\text{theory}}$ |
|---|---|---|---|---|
| 0.10 | 81% | 90% | 0.82 | 0.93 |
| 0.20 | 64% | 80% | 0.67 | 0.87 |
| 0.30 | 49% | 70% | 0.56 | 0.79 |
| 0.40 | 36% | 60% | 0.46 | 0.69 |
| 0.50 | 25% | 50% | 0.37 | 0.57 |

**理论预测**：在同一 $p$ 下，$\rho_{\text{mask}} > \rho_{\text{crop}}$，因为掩码保留了更多像素。

### 1.3 不相关基线的理论差异

| 污染类型 | 零区域来源 | 不相关基线特性 |
|---|---|---|
| 剪裁 | canvas 边缘对称区域 | 所有照片共享相同零边框 → 不相关对之间有**共享结构** → $\rho_{\text{unrel}}$ 偏高 |
| 掩码 | 每张照片独立随机位置 | 零位置互不重叠 → $\rho_{\text{unrel}}$ 接近 0 |

因此掩码的**辨别差值** $\Delta = \rho_{\text{related}} - \rho_{\text{unrelated}}$ 可能比剪裁更高——尽管绝对 $\rho_{\text{related}}$ 较低。这是本实验最核心的对比点。

### 1.4 hand-calculable base case（掩码）

取 $4 \times 1 \times 1$ canvas（单通道 4 个像素），$\hat{I} = [4, 20, 36, 20]$。
掩码 $p=0.5$（mask 后两个像素）：$Y = [4, 20, 0, 0]$。

$\bar{X} = 20, \quad \bar{Y} = 6$

$\text{Cov} = \frac{1}{4}[4 \times 4 + 20 \times 20 + 36 \times 0 + 20 \times 0] - 20 \times 6 = \frac{416}{4} - 120 = 104 - 120 = -16$

负数！因为 mask 保留了小值像素（$4, 20$）而抹除了大值像素（$36, 20$）。

这说明**随机掩码的方差对特定采样路径可以为负**；对于足够大的图像（大数定律），期望值为正（$(1-p)\sigma^2 > 0$），但在 4 像素小样本下出现负值是正常的。

对 $4 \times 4$ canvas 取多次平均（10 个随机排列）才能稳定。本实验在 $256 \times 256 \times 3 \approx 196608$ 像素上计算，远超单次随机涨落。

## 2. 不适用条件和反例

1. **极小图像**（< 64 像素）：掩码的 Pearson 相关方差很大，单次实验不可靠。
2. **p=0.5 剪裁**（保留 25% 像素）与 **p=0.5 掩码**（保留 50% 像素）在信息量上不对等，不能称为"相同程度的污染"——仅称为"相同标称 $p$ 值"。
3. **纯噪声图像**（$\sigma \to$ uniform）：剪裁和掩码的 $\rho_{\text{related}}$ 均主要由零填充均值效应决定，差值趋近于零。
