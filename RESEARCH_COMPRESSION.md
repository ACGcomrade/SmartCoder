# 压缩研究：CRT base 的无损压缩效率

检索日 2026-09-06。先于 PLAN_COMPRESSION.md 和实现。

## 1. 检索记录

| 来源 | 检索词/链接 | 日期 | 阅读范围 | 本轮采用 / 不采用 |
|---|---|---|---|---|
| [Numcodecs](https://numcodecs.readthedocs.io/en/stable/)，zarr-developers；持续维护，2026-09-06查阅 | Delta、PackBits pre-compression filters | 首页、filter API | 采用 Delta 行滤波原理；不引入 Numcodecs 依赖，改用 Python stdlib |
| [Zarr chunked storage performance](https://zarr.readthedocs.io/en/stable/user-guide/performance/)，2026-09-06查阅 | chunk shape、codec pipeline、ByteShuffle | 全文 | 借鉴分块与 codec pipeline 设计；不引入 Zarr 依赖 |
| [Larger than memory image processing](https://arxiv.org/abs/2601.18407)，Sporring/Stansby，2026-01-26 | tile-based streaming, I/O-bound | 摘要与分块部分 | v0.4已采用分块思路；本轮不新增结论 |
| [Linearized Polynomial CRT codes](https://arxiv.org/abs/2505.15720v2)，Gaborit et al.，2025-05-21/2026-07-04修订 | CRT codes for rank metrics | 摘要 | 面向误差码而非存储压缩；本轮不采用其 polynomial CRT 结构 |
| PNG specification, ISO/IEC 15948:2003 §6.5 | prediction filters: None/Sub/Up/Average/Paeth | 规范全文 | 采用 Sub（行 delta）滤波原则；PNG 是已有工业标准，不声称本轮发明 |
| Python `lzma` module, Python 3.9 docs，2026-09-06查阅 | FORMAT_XZ, PRESET_DEFAULT, decompress | stdlib 文档 | 采用 `lzma.compress/decompress`；无需额外依赖 |
| [RNS-based Montgomery multiplication](https://globals.ieice.org/en_transactions/fundamentals/10.1587/transfun.2025DMP0006/)，Kawamura et al.，2026-03-26/2026-09-01 | RNS base extension overhead | §2.3/§5.4 | 确认余数分量独立存储在信息论上等价；不是同一整数的传统 base extension |

检索词：lossless compression integer arrays delta coding residue number system RNS, per-channel scientific array compression 2025 2026, PNG filter predictor lossless。未找到2026年直接针对 CRT residue plane 分离存储的新论文；以 PNG/Delta+entropy 这一已有组合为理论基础。

## 2. 数学理论对照

### 2.1 CRT 环同构与信息等价

**定理（中国剩余定理，R1 Milne）**：设 $p_0,\ldots,p_{K-1}$ 为两两互素的正整数，$M_K=\prod p_k$，则
$$\phi:\mathbb{Z}/M_K\mathbb{Z} \xrightarrow{\sim} \prod_{k=0}^{K-1}\mathbb{Z}/p_k\mathbb{Z},\quad b\mapsto(b\bmod p_0,\ldots,b\bmod p_{K-1})$$
是环同构，逆映射由 CRT 权重显式给出。

**应用**：每个 cell $b$ 与其 $K$ 元余数组 $(r_0,\ldots,r_{K-1})$ 之间是严格一一对应。存储一侧选用任何一种表示，信息内容不变。

### 2.2 有效状态数与当前格式的位浪费

当前有效 cell 值满足 $r_k \in [0,Q^2)$ 对所有 $k$。有效状态数精确为 $Q^{2K}$，信息量 $I = 2K\log_2 Q = 12K$ 位。

当前格式按字节宽 $w_K = \lceil\log_2 M_K/8\rceil$ 存储。对 $K=6$，$\log_2 M_6 \approx 73.3$ 位，$w_K=10$ 字节 $= 80$ 位。有效信息 $12K=72$ 位，固定格式浪费 $80-72=8$ 位/cell。不存在压缩时，该浪费为 $8/72 \approx 11\%$。

大整数 zlib level=1 的实测压缩效果：v0.4 结果显示 tile 文件 ~120KB ≈ 原始大整数字节数，实际接近无压缩。

### 2.3 余数平面分离后的可压缩性

**命题 C1（平面分离等价）**：设每个 cell 值 $b$ 对应余数组 $(r_k)_{k<K}$，再设 $d_k^{(0)} = r_k \bmod Q$，$d_k^{(1)} = r_k \mathbin{/\!/} Q$（整除）。则 $2K$ 个函数 $d_k^{(s)}$ 构成 cell 的完整等价表示：已知全部 $d_k^{(s)}$ 可唯一重建 $b$。

**证明**：$r_k = d_k^{(0)} + Q d_k^{(1)}$ 唯一确定 $r_k$，由 CRT 同构唯一确定 $b$。$\square$

**命题 C2（空间相关性）**：数字 $d_k^{(s)}$ 恰好是第 $2k+s$ 张照片在该位置的量化像素值 $\lfloor\text{px}/4\rfloor \in [0,Q)$。相邻位置的相同照片像素值受自然图像空间相关性约束，Markov 条件熵 $H(d_{i,j}^{(k,s)}|d_{i,j-1}^{(k,s)})$ 在自然图像上通常远小于 $\log_2 Q = 6$ 位/像素（文献记录值约 3–5 位/像素，PNG Sub 滤波后约 1.5–3 位/像素）。

**推论**：对每个 $2K$ 平面分别施行行 delta 滤波后，delta 值集中于零附近，lzma 熵编码可将每平面有效压缩；而混合 $K$ 个来自不同照片的大整数字节后，局部相关性被破坏，lzma/zlib 难以找到重复模式。

### 2.4 手算 base case

取 $K=2$，$Q=4$（简化，仅2位），$p_0=17 \geq Q^2=16$，$p_1=19$，$M=323$，$w=2$ 字节。

**3 个 cell，2 张照片/域：**

| 位置 | $d_0^{(0)}$ | $d_0^{(1)}$ | $d_1^{(0)}$ | $d_1^{(1)}$ | $r_0=d_0^{(0)}+4d_0^{(1)}$ | $r_1=d_1^{(0)}+4d_1^{(1)}$ | $b=\text{CRT}(r_0,r_1)$ |
|---|---|---|---|---|---|---|---|
| 0 | 1 | 2 | 3 | 0 | 9 | 3 | 9·e₀+3·e₁ mod 323 |
| 1 | 1 | 3 | 3 | 1 | 13 | 7 | |
| 2 | 2 | 3 | 2 | 1 | 14 | 6 | |

其中 $e_0=(323/17)\cdot(323/17)^{-1}\bmod323$，$e_1=(323/19)\cdot(323/19)^{-1}\bmod323$。

**行 delta（第0行，前一值=0）**：$\Delta d_0^{(0)}=[1,0,1]$，$\Delta d_0^{(1)}=[2,1,0]$，$\Delta d_1^{(0)}=[3,0,-1\equiv3]$，$\Delta d_1^{(1)}=[0,1,0]$。

delta 值均在 $[0,3]$，原始值在 $[0,3]$ 也小，但相邻差更小→熵更低。重建：前缀累加（mod Q）→原始平面→CRT→$b$，逐步验证精确匹配。

### 2.5 反例与非适用条件

1. **随机内容图像**（纯噪声）：相邻像素无相关，delta 值均匀分布 $[0,Q)$，压缩比 ≈ 1，平面分离不带来增益。
2. **K=1（2 张照片）**：平面数 2K=2，delta 空间 $[0,Q)$ 无额外收益，行 delta + lzma 可能仅勉强压缩（因 lzma 本身仍会尝试 LZ 匹配）；Q=64 时期望仍有 1.5–2× 压缩。
3. **大量不相关照片放入同一 base**：K 很大时 M_K 增长但每域照片仍只有 2 张；压缩按平面独立进行，总字节随 K 线性增长，不额外恶化。
4. **细节丰富的照片**（显微、颗粒噪声）：v0.4 结果显示 Brick wall/Gravel PSNR 已接近量化下界；delta 压缩仍有效但比率更低（预期 1.5–2×）。

## 3. 本轮不采用的替代方向

- **算术编码（per cell probability model）**：需精确建立联合概率模型，工程复杂度高，不是首选。
- **专用图像格式（HEIF、AVIF）**：有损，不符合本项目精确重建要求。
- **Blosc / zstd**：需要外部依赖；stdlib lzma 可行，后续可换为 zstd 进行速度比较。
- **差分打包（bijection from valid states to [0, Q^(2K))）**：节省约11%空间，实现复杂且非主要瓶颈，不在本轮引入。
