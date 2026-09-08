# 研究：s-槽 CRT 耦合容量与错误传播边界

检索日 2026-09-08。先于 PLAN_COUPLING.md 和实现。

## 1. 检索记录

| 来源 | 内容 | 本轮采用 |
|---|---|---|
| Watson & Hastings (1966), *Self-checked computation using residue arithmetic*, Proc. IEEE 54(12):1920–1931 | 首次系统性 RNS 可靠性分析；单个余数出错的检测条件 | 引用为 RNS 错误传播的经典来源；"合法范围"定理 |
| Barsi & Maestrini (1973), *Error correcting properties of redundant residue number systems*, IEEE Trans. Computers 22(3):307–315 | 冗余模的错误纠正能力；非冗余系统无法检测 | 确认：非冗余 CRT 系统（无冗余模）错误不可纠正 |
| Milne R1（项目一直引用），CRT 环同构定理 | φ: Z/M_K Z → ∏ Z/p_k Z 是精确环同构 | 证明：字段间信息完全独立，字段内信息精确耦合 |
| 本项目 RESEARCH_STREAMING.md，Kawamura et al. (2026) | RNS base extension 开销 | 确认 s 越大 CRT 运算代价越高 |

**2026 arxiv 检索**（关键词：RNS coupling, CRT slot interference, s-slot residue storage）：未找到直接对应本项目 s-槽图像存储耦合度测量的新论文。以下推导是本项目在已有数学基础上的原创应用，不声称新定理。

## 2. 关键数学澄清：两种错误扩散方式

### 2.1 字段内耦合（字段级 = s 张照片同步降级）

对 $s$-槽字段 $k$，当该字段的残数 $r_k$ 被污染：

$$r_k \in [0, Q^s) \;\xrightarrow{\text{pollution}}\; r_k' \in [0, Q^s) \text{ (随机)}$$

解包后所有 $s$ 张照片的像素同时错误：

$$d_j' = \left\lfloor r_k' / Q^j \right\rfloor \bmod Q \neq d_j \quad \forall\, j \in \{0,\ldots,s-1\}$$

**结果**：一次字段残数污染 → **恰好** $s$ 张照片的同一空间位置同时出错（"字段级联"，amplification = $s$）。

### 2.2 字段间独立性（照片-字段归属不同 → 零交叉污染）

对字段 $k \neq k'$，$r_k$ 的污染**不影响** $r_{k'}$（CRT 环同构保证各字段残数代数独立）。

因此：只有属于字段 $k$ 的 $s$ 张照片降级，其余 $N - s$ 张照片的 PSNR **精确不变**。

### 2.3 per-photo PSNR 不受 $s$ 影响（重要但反直觉）

对同等的**字段级**污染率 $\varepsilon_{\text{field}}$：
- 每张照片属于一个字段，该字段的残数以概率 $\varepsilon_{\text{field}}$ 被污染
- 每张照片的像素错误率 = $\varepsilon_{\text{field}}$，**与 $s$ 无关**
- 因此 PSNR($s=1$, $\varepsilon$) $\approx$ PSNR($s=2$, $\varepsilon$) $\approx$ PSNR($s=4$, $\varepsilon$)

$s$ 的影响**不在**每张照片的质量（PSNR），而在错误的**耦合结构**。

### 2.4 真正的耦合效应：错误位置的完全相关

对 $s=2$（照片 $2k$ 和 $2k+1$ 在字段 $k$）：

$$\text{ErrorMask}(2k) = \text{ErrorMask}(2k+1) \quad \text{（完全相同的错误位置）}$$

$$\Rightarrow \text{IoU}(\text{errors}_{2k}, \text{errors}_{2k+1}) \approx 1.0$$

对 $s=1$（照片 $2k$ 和 $2k+1$ 在不同字段）：

$$\text{IoU}(\text{errors}_{2k}, \text{errors}_{2k+1}) \approx \varepsilon^2 \approx 0$$

**这是 s ≥ 2 的唯一可测量的耦合特征**：同一字段的照片错误位置 100% 相关（"耦合失效"）；不同字段的照片错误位置不相关（"独立失效"）。

## 3. 边界的精确计算

| 量 | 公式 | 可否先验计算 |
|---|---|---|
| s=1 与 s≥2 的分类边界 | s≥2 → 非平凡耦合 | **可以，精确** |
| 字段级联宽度 | 每次字段污染影响恰好 $s$ 张照片 | **可以，精确** |
| 错误位置 IoU（同字段） | = 1.0 | **可以，精确** |
| 错误位置 IoU（跨字段） | = $\varepsilon^2$ ≈ 0 | **可以，近似** |
| per-photo PSNR（$s$ 函数） | PSNR 与 $s$ 无关 | **可以，精确** |
| 安全字段污染率上限 | $\varepsilon_{\max}(s) = \delta$ 与 $s$ 无关 | **可以，精确** |

**需要实验测量的**：在实际图像内容上，"耦合失效"（同位置 $s$ 张照片同时出错）的感知质量是否比"独立失效"更差（视觉上更显眼的错误斑点）。理论不能预测这一感知差异。

## 4. base case 手算

取 $s=2$，$Q=4$，2 个像素位置，照片 0：$d_0=[3,1]$，照片 1：$d_1=[2,3]$。

字段残数：$r_0=[3+4\times2, 1+4\times3]=[11, 13]$

污染字段 0 位置 0（$r_0[0]=11 \to 7$）：
- 恢复：$d_0'[0]=7\bmod4=3$（正确！），$d_1'[0]=7//4=1$（错误，原值 2）
- 注意：污染 $r_0$ 不一定同时损坏两个槽——取决于污染后的值

污染字段 0 位置 0（$r_0[0]=11 \to 6$）：
- 恢复：$d_0'[0]=6\bmod4=2$（错误，原值 3），$d_1'[0]=6//4=1$（错误，原值 2）
- 两个槽都错 ✓

这说明 $r_k$ 被替换为随机值时，两个槽均以高概率出错（因为随机值几乎不满足 $r_k'=d_0+4d_1$ 对原 $d_0, d_1$ 成立）。
精确计算：槽 $j$ 出错的概率 = $1 - 1/Q^{s-j}$；对 $s=2,Q=4$：$\Pr[\text{任意槽出错}] = 1 - 1/Q^{s}(s\text{项正确概率})$，在实际随机替换下≈$(Q^s-1)/Q^s$（高于 $3/4$）。
