# SmartCoder：数学依据、相关研究与构造选择

**当前 v0.4 研究**：[RESEARCH_STREAMING.md](./RESEARCH_STREAMING.md) 给出本轮最新流式图像处理、有限域自动构造、RNS转换文献与技术栈对照，并独立推导统一素域工厂、延迟CRT扩展及RAM边界。预注册 [PLAN_STREAMING.md](./PLAN_STREAMING.md)，结果 [RESULTS_STREAMING.md](./RESULTS_STREAMING.md)。不把生成数学域的通用算法误称为n个手工解码器，也不把分块RAM收益误称为数学压缩定理。

**新增 v0.3 二维照片研究**：[RESEARCH_2D.md](./RESEARCH_2D.md) 记录 2026-09-06 的最新检索、技术栈文档、三素域构建、量化误差证明和局部写入推导。先完成研究和 [预注册计划](./PLAN_2D.md)，再运行实际照片实验；[实测结果](./RESULTS_2D.md) 单独报告。以下保留 v0.2 的来源编号和研究结论。

版本：v0.2.0；检索日期：2026-09-06。研究顺序：先改写 README 的目标与术语 → 重新检索 → 完成本文件 → 补全 README 的有依据推导 → 编写最小实现规格与复算脚本。

## 1. 研究对象和证据等级

本轮的 field 指抽象代数中的域；list 暂指有限有序序列。研究对象是由共同 base 和域上的 decoder 共同确定的数学结果，不附加语义视图一致性。用户的 one-to-one 按强、弱两种性质分别检验，强性质不被静默降级。

- **文献结论**：仅报告所读原始材料支持的结论，注明适用条件。
- **本项目推导**：从域公理、计数、CRT 等已知结果推导下面的构造；不声称发明了这些定理。
- **研究假说**：局部动力学是否形成有用的联想记忆或智能，仍待实验。

检索使用数学及计算机科学 tag：finite fields、field homomorphisms、Chinese remainder theorem/codes、residue number systems、locally decodable/updatable/repairable codes、update efficiency、associative memory、test-time memorization。搜索范围覆盖 2025–2026，也保留决定可行性的经典定理。本轮不是穷尽性系统综述，不能据此宣称没有同类工作或本构造具有论文级原创性。

## 2. 核心来源与对设计的影响

### R1：域、域同态与 CRT 的基础

J. S. Milne，[Fields and Galois Theory，v5.10 (2022)](https://www.jmilne.org/math/CourseNotes/FT.pdf)，Definition 1.1、§1 的同态与特征、Theorem 8.1。已查阅相关定义与证明。

**已有结论**：非零元素可逆是域的必要条件；保单位域同态为单射；CRT 将适当商环分解成商结构的乘积。素数模数给出素域。**设计影响**：必须区分存储载体的环和 decoder 的目标域；不能把复合数模环称为域，也不能把域名称当作读出函数。

### R2：CRT 编码的教学基准

Stanford CS250/EE387，[Winter 2025 Class 11 Exercises](https://web.stanford.edu/class/archive/cs/cs250/cs250.1254/InClass/Class11_soln.pdf)，Theorem 1、Definition 1。已核对整数 CRT 编码的定义；这是课程材料，不是 2025 年的新发现。

**已有结论**：互素模数的完整余数组唯一确定有界整数；若消息范围小于总余数组的容量，多出来的空间可作为冗余。**设计影响**：一个整数与多个域的余数可以精确对应，但单独一个余数通常丢失信息；普通 CRT 双射没有自动纠错能力。

### R3：2025 初稿、2026 更新的多项式 CRT 研究

Gaborit、Garnier、Ruatta，[Linearized Polynomial Chinese Remainder codes, arXiv:2505.15720v2](https://arxiv.org/html/2505.15720v2)。初稿 2025-05-21，v2 为 2026-07-04。已查阅摘要、§3 的环结构、§3.3 的 CRT/lifting 与算法范围；按预印本引用。

**已有结论**：作者在有限域上线性化多项式的非交换运算环境中构造 qCRT 码；对指定子类给出概率解码，并分析规定错误模型下的失败率。**设计影响**：后续可以探索多项式 list 和更丰富的域上运算。它不是“任意不同域都是 decoder”的证明；非交换 CRT 的左右除法条件也不能直接套用到普通整数例子。

### R4：局部更新与局部纠错的代价

Mazumdar、Chandar、Wornell，[Update-Efficiency and Local Repairability Limits for Capacity Approaching Codes](https://arxiv.org/abs/1305.3224v3)，2013，页面注明 accepted to appear in JSAC。核对摘要及适用噪声/码率条件。

**已有结论**：在文中 BEC/BSC、非平凡码率及渐近消失错误概率的条件下，单信息 bit 改动引起的编码 bit 更新规模有对数级要求。**设计影响**：同时要求纠错、低冗余和极少写入并不免费。不能把该渐近结论用来否定没有噪声的小型可写存储，也不能把“修改一个大整数”计为只改一 bit。

### R5：明确研究“部分读、部分改”的编码

Chandran、Kanukurthi、Ostrovsky，[Locally Updatable and Locally Decodable Codes](https://web.cs.ucla.edu/~rafail/PUBLIC/159.html)，CRYPTO 2015，作者页面。已核对摘要，未在本轮复核完整证明。

**已有结论**：在特定 Prefix Hamming 噪声模型下，构造兼顾局部读写的编码；部分更强结果另外依赖共享秘密状态和计算受限对手。**设计影响**：给“部分激活、部分修改”分别定义读探测数与写入数，并明确损坏模型。这里的局部读取恢复的是所查询的消息部分，不要求一次局部回答标识整个存储库。

### R6：2026 年有限域局部修复码

Huang、Zhao，[Locally Repairable Codes with Availability via Elliptic Function Fields, arXiv:2605.06182v1](https://arxiv.org/html/2605.06182v1)，2026-05-07。已读引言、Definition 1 与构造结论；按预印本引用。

**已有结论**：利用椭圆函数域构造一组或两组恢复集合的 LRC。局部修复指从少量其他编码符号恢复一个擦除符号；并非恢复全部数据。文中回顾单恢复集合的 Singleton 型界 \(d\le n-k-\lceil k/r\rceil+2\)。**设计影响**：修复 locality 与读取 locality、更新 locality 分开测。首例可以先用明确的一次擦除校验关系，后续再考虑复杂曲线构造。

### R7：2026 年正式发表的码构造

Mondal、Hyun、Lee，[Locally repairable codes and minimal codes by homogenization of down-sets](https://link.springer.com/article/10.1007/s12095-026-00887-x)，Cryptography and Communications，2026-04-21。核对发表信息与摘要。

**已有结论**：通过 homogenization 构造若干 p 元 minimal、distance-optimal 与 locally repairable 码族。**设计影响**：有限域编码仍有活跃的结构设计空间；minimal code 是编码理论术语，不能误读成“最小 memory demo”，更不能由标题推出智能。

### R8：运行时可写记忆的邻接研究

Behrouz 等，[Titans](https://arxiv.org/abs/2501.00663)（初次提交 2024-12-31）与 [MIRAS](https://arxiv.org/abs/2504.13173)（初次提交 2025-04-17）。本轮重新核对论文页面摘要。

**已有结论**：Titans 研究运行时更新的神经记忆；MIRAS 将相关架构设计拆为记忆形式、内部目标、保留机制和学习算法。**设计影响**：未来把 decoder 状态和 base 状态都写入动力学方程。这些神经优化结果不提供有限域 decoder 或严格单射定理，不能用来证明当前代数构造。

### R9：2026 年组合性联想记忆

Kafraj、Krotov、Latham，[A Biologically Plausible Dense Associative Memory with Exponential Capacity, arXiv:2601.00984v2](https://arxiv.org/abs/2601.00984v2)，2026-01-02 初稿、2026-03-09 修订；按预印本引用。已核对摘要。

**已有结论**：作者在其阈值网络及可见层大小等条件下，以隐藏组件的组合形成多个稳定模式。**设计影响**：区别“许多吸引子/组合模式”和“独立写入任意许多随机消息”。论文标题的 exponential capacity 不能被转述为任意数据的指数无损压缩。

### R10：2026 年压缩状态与精确回忆的取舍

Lufkin 等，[Hybrid Associative Memories, arXiv:2603.22325v2](https://arxiv.org/abs/2603.22325v2)，2026-03-20 初稿、2026-03-27 修订；按预印本引用。已核对摘要。

**已有结论**：结合 RNN 状态与选择性存储的注意力 cache，通过阈值调节显式记忆增长，在实验中研究损失与容量的取舍。**设计影响**：后续将精确存储、压缩表示和按需增长分开评估；该工作不解决跨数学域的解码唯一性。

## 3. 本项目的数学判断

以下为依据 R1–R6 自行展开的推导方向，不是上述论文已经验证过的 SmartCoder 实验。

### 3.1 必须分清四个命题

设 \(\mathcal B\) 是 base 集合，\(\mathcal D\) 是 decoder 集合。

1. **确定性**：\(G(B,D)\) 是函数，每个输入对只有一个结果。
2. **固定 decoder 的单射**：\(D(B)=D(B')\Rightarrow B=B'\)。
3. **输入对的严格单射**：\(G(B,D)=G(B',D')\Rightarrow(B,D)=(B',D')\)。
4. **联合解码双射**：\(B\leftrightarrow(D_1(B),\ldots,D_s(B))\)。

CRT 原生支持第 4 条和第 1 条。不能以第 4 条冒充第 3 条。若结果生活在不同域中，先定义带类型的结果空间 \(\bigsqcup_D\mathcal Y_D\)；去掉类型再比较数字，是另外一个问题。README §3.4 另用像集不交的两个域上函数满足无标签严格单射，并明确其输出空间代价。

### 3.2 三个直接可证的限制

**部分读与全局单射**：对自由 list \(B\in A^N\)，确定性、无缓存读取若在某个输入上没探测一个坐标，就可以仅改变该坐标得到相同执行路径与输出。所以它不可能在所有 base 上全局单射。自适应寻址也一样：每次已探测值不变，下次地址选择就不变。冗余码限制了合法状态集合时，前提不再相同；必须另外分析码本。

**全局单射与非干扰**：若 \(D\) 单射且 \(B'\ne B\)，必有 \(D(B')\ne D(B)\)。因此不能同时要求每个 decoder 完整识别 base，又要求修改后某个 decoder 的完整结果保持不变。部分输出重叠当然允许。

**信息容量**：能精确区分 \(K\) 种可能记忆的固定长度持久状态至少需要 \(\lceil\log_2K\rceil\) bits，由 \(2^b\ge K\) 直接得到。可变 decoder 若保存了历史信息，也属于持久状态。CRT 重编码本身不减少可能状态数量。

### 3.3 为什么选择两个构造

| 构造 | 对 one-to-one 的保证 | 局部修改的含义 | 此例的作用 |
|---|---|---|---|
| A：有限 list 在两个素域上的可逆仿射读出 | 每个固定 decoder 单射；保留 decoder 类型时输入对单射 | 修改一个 list 坐标；每种解码的其余坐标保留 | 首要检查用户的强解释 |
| B：CRT 打包 + 域投影 | 完整余数组与 base 双射；单独投影不单射 | 修改一个 cell 的一个余数，其他域余数保留 | 对照独立记忆读写；明确不满足强解释 |

A 中两种结果都包含完整 base 的可恢复信息，这是严格单射本身的后果；结果不同不表示承载两组独立信息。B 能容纳独立余数，但从一个余数不能知道其他余数。应把这一区别展示出来，供课题选择，而非把两种优点混写为同一个已证明系统。

## 4. 从域运算到动力学，还缺什么

通用待研究形式为：
\[
(B_{t+1},\theta_{t+1})=U_{S_t}(B_t,\theta_t,x_t),\qquad
y_t=D_{\theta_t,F_t}(B_t|_{S_t},q_t).
\]

其中 \(S_t\) 是本步访问集合，\(\theta_t\) 包含 decoder 的实际数学参数。若要求确定性，查询、参数和任何随机种子都必须纳入函数输入。若要求严格单射，必须注明对象是局部 base \(B|_{S_t}\)、完整 base，还是等价类；这些不能替换使用。

有限域没有现成的实数大小、正定内积或微分结构。引入 gradient、cosine 或能量下降前，要另外定义实值评分/嵌入，并说明如何与有限域更新连接。当前的赋值读写证明不需要这些附加结构。

后续真正有研究价值的问题包括：如何让域上局部算子自行组织出稳定可恢复的编码；如何对错误给出可判定的接受/拒绝规则；如何学习算子并在未见任务上组合。现在只能把它们写为假说。

## 5. 本轮结论如何约束最小方案

先证明定义良好的读写和唯一性，再研究修复，最后研究自组织。README 给出 A、B 的手算与证明；MVP_SPEC 将它们转成穷举检查，正例与反例均必须出现。与 raw list 和直接余数存储对照，第一阶段只作构造存在性证明，不追求人为设定的 99% 指标。

“独立开发”在本项目的含义是：用户给出研究构想，本轮按该构想展开模型、限制证明与实验规格；不是对 CRT、可逆仿射变换或校验码主张原创性。没有来源支持的智能主张不会被写成已有成果。
