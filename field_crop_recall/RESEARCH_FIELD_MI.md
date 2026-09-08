# 方向1研究：裁剪级别与余数平面相关性

检索日 2026-09-08。先于 PLAN_FIELD_CROP.md 和实现代码。

## 1. 检索记录

| 来源 | 日期 | 阅读范围 | 本轮采用 / 不采用 |
|---|---|---|---|
| Kornblith et al.，*Similarity of Neural Network Representations Revisited*，arXiv:1905.00414v4，ICML 2019，2019-07-19 | 摘要+方法 | 采用 CKA 的动机：两组向量之间的相关性度量；本轮不引入完整 CKA 流程，改用空间 Pearson 相关（更简单，物理意义更直接） |
| Hopfield, J.J.，*Neural networks and physical systems with emergent collective computational abilities*，PNAS 1982, 79(8):2554–2558 | 全文要点 | 分布式记忆在部分激活下仍能恢复原记忆的直觉来源；本轮不实现 Hopfield 动力学，仅借用「部分输入→联想恢复」的概念框架 |
| Pearson, K.，*Notes on regression and inheritance in the case of two parents*，Proc. Roy. Soc. Lond. 1895 | 标准教材 | Pearson 相关系数定义，无需引用原文 |
| Python `numpy.corrcoef` 文档，同日查阅 | 接口说明 | 用于计算展平后余数平面的线性相关系数 |

检索词：residue plane spatial correlation, partial occlusion memory recall, CKA representation similarity 2024 2025 2026，未发现 2026 年直接针对 CRT 余数平面遮挡实验的新成果。以 Pearson 相关+零填充画布为理论基础。

## 2. 实验设置的数学形式

### 2.1 对象定义

固定 $Q=64$，canvas 大小 $H \times W$（为当前照片最大尺寸）。

原始照片 $I \in [0, 255]^{H \times W \times 3}$，量化为 $\hat{I} = \lfloor I/4 \rfloor \in [0, 63]^{H \times W \times 3}$。

**center crop 操作**，裁剪比例 $p \in (0,1)$：

$$\text{crop}_p(I) = I\!\left[\frac{pH}{2}:\frac{(2-p)H}{2},\; \frac{pW}{2}:\frac{(2-p)W}{2},\; :\right]$$

裁剪后尺寸 $(1-p)H \times (1-p)W$，保留 $(1-p)^2$ 比例的像素，**不 resize 回原尺寸**。

**余数平面**（aligned 放置，保持原坐标）：

$$X[i,j,c] = \hat{I}[i,j,c] \qquad (i,j) \in [0,H) \times [0,W)$$

$$Y_p[i,j,c] = \begin{cases} \hat{I}[i,j,c] & (i,j) \in \left[\frac{pH}{2},\frac{(2-p)H}{2}\right) \times \left[\frac{pW}{2},\frac{(2-p)W}{2}\right) \\ 0 & \text{otherwise} \end{cases}$$

### 2.2 理论预测

设像素值近似 i.i.d.，均值 $\mu$，方差 $\sigma^2$。设 $n = HW$，$n_c = (1-p)^2 n$。

**协方差**：仅重叠区域对 $\sum x_i y_i$ 有贡献（重叠区 $x_i = y_i$）：

$$\text{Cov}(X, Y_p) = \frac{n_c}{n}(\sigma^2 + \mu^2) - \mu \cdot \frac{n_c \mu}{n} = (1-p)^2 \sigma^2$$

**方差**：

$$\text{Var}(X) = \sigma^2, \qquad \text{Var}(Y_p) = (1-p)^2 \sigma^2 + (1-p)^2 \mu^2 p(2-p)$$

**Pearson 相关**：

$$\boxed{\rho_{\text{theory}}(p) = \frac{(1-p)\,\sigma}{\sqrt{\sigma^2 + \mu^2 p(2-p)}}}$$

对典型 6-bit 量化图像（$\mu \approx 25$，$\sigma \approx 12$，实验值）：

| $p$ | 理论 $\rho$ |
|---|---|
| 0 | 1.000 |
| 0.10 | ≈ 0.56 |
| 0.20 | ≈ 0.43 |
| 0.30 | ≈ 0.34 |
| 0.40 | ≈ 0.27 |
| 0.50 | ≈ 0.22 |

两个特殊性质：
1. $\rho_{\text{theory}}$ 关于 $p$ **严格递减**（对 $\sigma > 0$）
2. 对于不相关的照片对（$Y_p$ 来自不同照片），$\text{Cov} \approx 0$，因此 $\rho_{\text{unrelated}} \approx 0$

**注意**：理论公式假设 i.i.d. 像素值，真实图像有空间相关结构，可能使 $\rho_{\text{measured}} > \rho_{\text{theory}}$（同一图像的相邻像素值接近，即使经过零填充，结构相关性仍高于 i.i.d. 假设）。

### 2.3 手算 base case

取 $4 \times 4$ canvas，单通道，$p = 0.50$（保留 $2 \times 2$ 中心）。

已量化的原始像素 $\hat{I}$（直接取整数，无需除 4 操作）：

$$X = \begin{bmatrix} 4 & 8 & 12 & 16 \\ 20 & 24 & 28 & 32 \\ 36 & 40 & 44 & 48 \\ 20 & 24 & 28 & 32 \end{bmatrix}$$

50% crop（center）保留 $[1:3, 1:3]$，aligned 放置：

$$Y_{0.5} = \begin{bmatrix} 0 & 0 & 0 & 0 \\ 0 & 24 & 28 & 0 \\ 0 & 40 & 44 & 0 \\ 0 & 0 & 0 & 0 \end{bmatrix}$$

$\bar{X} = 416/16 = 26$，$\bar{Y} = 136/16 = 8.5$

$\text{Cov}(X,Y) = \frac{1}{16}\sum x_i y_i - 26 \times 8.5$
$= \frac{24^2+28^2+40^2+44^2}{16} - 221$
$= \frac{576+784+1600+1936}{16} - 221 = \frac{4896}{16} - 221 = 306 - 221 = 85$

$\text{Var}(X) = \frac{\sum x_i^2}{16} - 26^2 = \frac{9280}{16} - 676 = 580 - 676$... 

（此 case 的 $\text{Var}(X)$ 重算：$\sum x_i^2 = 16+64+144+256+400+576+784+1024+1296+1600+1936+2304+400+576+784+1024 = 13184$，$\text{Var}(X) = 13184/16 - 676 = 824 - 676 = 148$）

$\text{Var}(Y) = \frac{576+784+1600+1936}{16} - 8.5^2 = 306 - 72.25 = 233.75$

$$\rho = \frac{85}{\sqrt{148 \times 233.75}} = \frac{85}{\sqrt{34595}} = \frac{85}{185.9} \approx 0.457$$

理论预测（$\mu=26$，$\sigma=\sqrt{148}=12.17$，$p=0.5$）：
$\rho_{\text{theory}} = \frac{0.5 \times 12.17}{\sqrt{148 + 676 \times 0.5 \times 1.5}} = \frac{6.09}{\sqrt{148+507}} = \frac{6.09}{\sqrt{655}} = \frac{6.09}{25.6} \approx 0.238$

实际手算值 0.457 高于理论 0.238，因为该 $4\times 4$ 例子存在强空间结构（值从左上到右下单调递增），符合「空间结构使实测 $\rho$ > 理论预测」的预期。

### 2.4 不相关基线的手算

如果 $Y_p$ 来自一张值全为 32 的不相关照片（均匀灰色图，同样 50% crop aligned）：

$$Y_{\text{unrelated}} = \begin{bmatrix} 0 & 0 & 0 & 0 \\ 0 & 32 & 32 & 0 \\ 0 & 32 & 32 & 0 \\ 0 & 0 & 0 & 0 \end{bmatrix}$$

$\bar{Y}_u = 128/16 = 8$，$\text{Cov}(X,Y_u) = \frac{32(24+28+40+44)}{16} - 26 \times 8 = \frac{32 \times 136}{16} - 208 = 272 - 208 = 64$

$\text{Var}(Y_u) = \frac{4 \times 32^2}{16} - 64 = 256 - 64 = 192$

$\rho_{\text{unrelated}} = \frac{64}{\sqrt{148 \times 192}} = \frac{64}{\sqrt{28416}} = \frac{64}{168.6} \approx 0.38$

这比 $\rho_{\text{related}} = 0.457$ 低，但不是 0。说明当不相关图像内容（灰色均匀）与零背景共同存在时，由于均值效应（两者均值都在 $\mu/2$ 左右）仍有一定相关性。

**重要结论**：零填充 canvas 中，相关照片和不相关照片都可能产生正 $\rho$。区分相关/不相关的关键是 $\rho_{\text{related}} - \rho_{\text{unrelated}}$ 的差值，而不是绝对值。

## 3. 反例与非适用条件

1. **低方差（均匀纯色）图像**：$\sigma \to 0$ 时分母 $\to 0$，Pearson 相关不适定；量化后纯色像素方差很低，可能产生数值不稳定。
2. **极小裁剪区域**（$p > 0.9$，保留 $<1\%$ 像素）：统计量不可靠；本实验最大 $p = 0.5$，保留 25% 像素，在合理范围。
3. **非方形 canvas 对非方形图像**：canvas 的 3W 列（因为 RGB 三通道展平）会引入额外零区域，需用 `photo_active_mask` 排除 canvas 中既无原图又无裁剪图的部分——或直接在完整 canvas 上计算，接受零区域对两个平面对称的贡献。

本实验选择在完整 canvas 上计算（两个平面均有相同零区域背景），对称处理保证比较的一致性。
