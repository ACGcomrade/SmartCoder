# 二维照片记忆：研究门槛记录

版本 v0.3；检索日 2026-09-06。本文在照片实验实现和测量之前建立，承接 RESEARCH.md 的 R1–R10。用户已确认：6 张输入、3 个固定域 decoder，每个 decoder 返回两张照片；编号仅选择返回值，不生成专属 decoder。

## 1. 检索与证据边界

本轮检索 finite field image storage、Chinese remainder codes 2026、image compression random access 2025/2026、finite scalar quantization 2026、NumPy integer promotion、Pillow image orientation。覆盖数学基础、近年编码研究和实际技术栈；不是系统综述，不声称穷尽最新成果。论文仅阅读摘要时不得将摘要当成已复现的结论。

| 来源、时间、阅读范围 | 文献支持什么 | 对本轮的作用与限制 |
|---|---|---|
| [Milne, Fields and Galois Theory](https://www.jmilne.org/math/CourseNotes/FT.pdf)，v5.10/2022；沿用 R1 的域定义、CRT 定理阅读 | 素数商环是域，互素模数的 CRT 分解 | 实际可行性的基础；本项目逐像素构造是初等应用，不是新定理 |
| [Linearized Polynomial Chinese remainder codes](https://arxiv.org/html/2505.15720v2)，初稿 2025-05-21，v2 2026-07-04；摘要及 HTML 构造/适用范围 | 线性化多项式上的 CRT 与秩/和秩码，部分实例有解码算法 | 最新相关代数研究，但不是本文的整数 CRT，也不能直接证明照片记忆或纠错 |
| [RAGE for the Machine](https://arxiv.org/abs/2402.05974)，2024-02-07 v1；摘要 | 兼顾像素随机访问与有损/无损压缩的图像框架 | 本次检索到的直接相关访问基准；不能把我们的局部读写等同于达到其压缩/性能成绩 |
| [PIC-DNA](https://arxiv.org/abs/2505.15632)，2025-05-21 v1；摘要 | JPEG2000 渐进编码与 DNA 图片池随机读取 | 支持将读取范围、质量、成本分开评估；不采用 DNA 或 JPEG2000 算法 |
| [iFSQ](https://arxiv.org/abs/2601.17124v2)，初稿 2026-01-23，修订 2026-01-27；摘要及版本信息 | 学习潜变量上的分布匹配有限标量量化 | FSQ 不是 finite field。本轮不用神经网络；原始像素误差上界由下文独立推导，不借用其潜变量实验结论 |
| [NumPy 数值提升规则](https://numpy.org/doc/stable/reference/arrays.promotion.html)，2026-09-06 查阅 | int64 与 uint64 混合可能提升为浮点 | 中间模乘显式 int64，并证明乘积上界；不依赖隐式提升 |
| [NumPy 文件 I/O](https://numpy.org/doc/stable/user/how-to-io.html)、[Pillow ImageOps](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html)，同日查阅 | NPY、内存映射；EXIF 方向变换 | 无 pickle 持久化；照片按 EXIF 方向解释再转 RGB，无缩放。像素访问计数不冒称磁盘页 I/O |
| [scikit-image 官方照片说明](https://scikit-image.org/docs/stable/api/skimage.data.html)、[v0.25.2 哈希注册表](https://github.com/scikit-image/scikit-image/blob/v0.25.2/skimage/data/_registry.py)，同日查阅 | 示例照片、尺寸及来源信息 | 固定版本下载五张图并核对官方 SHA256；另用 Matplotlib 固定版本 Grace Hopper 肖像 |

没有发现能直接保证“更少数学域 + 任意照片 + 更少总存储 + 智能涌现”的已读结论。本阶段只建立可核验的二维多记忆编码；不添加训练、纠错、跨图空间共享或自动语义检索。

## 2. 系统性构建，而非逐照片拟合

设每像素每通道 x∈{0,…,255}。选 Q=64，q=⌊x/4⌋；反量化 x̂=4q+2。因为 x=4q+t，t∈{0,1,2,3}，误差 2−t∈{2,1,0,−1}，故 max|x̂−x|≤2，MSE≤4，PSNR≥20log10(255/2)=42.1102 dB。这是确定性上界，不是照片测量后选阈值。

每个域存两个六位数字 r_i=q_(2i)+64q_(2i+1)，0≤r_i<4096。**按容量规则**取从 4096 起的前三个素数 p_i（程序试除验证）；F_(p_i) 的加乘为模 p_i 加乘。域本身不是 decoder；固定 decoder 是投影、规范整数代表、基数拆位和反量化的复合。拆位不是域同态。

M=p_0p_1p_2，e_i=(M/p_i)·((M/p_i)^−1 mod p_i) mod M，e_i mod p_j=δ_ij。二维 base 是 B∈(Z/MZ)^(H×3W)，B[y,3x+c]=Σe_i r_i[y,x,c] mod M。RGB 通道沿第二轴交错，不隐藏第三个存储轴。H、W 为所有图片最大高宽；各图保持原比例，越界位置填 q=0，恢复按尺寸裁去填充。Z/MZ 是环，不能称为域。

D_i(B) 同时返回 (4(r_i mod64)+2, 4⌊r_i/64⌋+2)，其中 r_i=B mod p_i，规范代表必须<4096。随后按两张图的尺寸裁去填充。所有运算参数由 Q 和域序号决定，与照片内容无关。三域、三固定 decoder；无逐照片权重/字典。metadata 只有尺寸、槽位及命名等，不保存像素。

CRT 保证整个量化照片组与合法 base（固定尺寸和规范填充）一一对应；单个 D_i 不能确定另外两个域的状态。对原始 8 位图有损，当然不满足原图的严格单射。这保留 README 构造 B 的边界，不替换构造 A 的强命题。二维化只增加空间索引，尚未证明二维相邻关系能产生额外智能。

## 3. 写入与局部性推导

更新域 i 的槽 s∈{0,1}，原数字 q_old，目标 q_new：r′=r+64^s(q_new−q_old)，Δ=(r′−r) mod p_i，B′=(B+e_iΔ) mod M。因此其他域的余数不变；同域另一数字也不变。仅在 ROI 的 3hw 个 cell 运算，其他空间坐标不读不写。

策略：已知改动位置使用 ROI；首次写入或没有位置提示的整张替换，处理该照片完整矩形；初建时也可用全 base 批量 CRT。当前不引入凭经验选的覆盖率阈值，不声称未知改动可以免扫描发现。改变尺寸/画布或增加域需重建，当前 API 拒绝越界。全图写入与全 base 重建不是同一件事。

NumPy 数组持久化 uint64，中间运算转 int64。要求 M·max(p_i)<2^63，保证 e_i·Δ+B 及批量逐项累加取模安全；用 Python 任意精度整数作独立对照。当前不是紧凑位流：每 cell 用 64 物理位，量化信息仅 36 位，模数占用约 37 位，另有填充/metadata 开销。必须报告与原始 RGB、量化直接数组、下载文件大小的比较。恢复时需临时余数/输出数组，不计作持久记忆但应披露。

## 4. 最小手算（运行通过后才开始照片实验）

取 Q=2、p=(5,7,11)、M=385、e=(231,330,210)。六个二值记忆按对打包为 r=(1,2,3)，B=(231+660+630) mod385=366。读取得到 366 mod(5,7,11)=(1,2,3)，拆位分别为 (1,0)、(0,1)、(1,1)。

将第一域高位从 0 改成 1，则 r_0=3，Δ=2，B′=(366+462) mod385=58；58 mod(5,7,11)=(3,2,3)，另五个数字不变。把该 cell 放入 [[366,0],[0,0]] 的左上角，更新后为 [[58,0],[0,0]]。程序穷举 64 种六位状态及各六个单槽翻转（384 次），再验证真实 Q 下的整数安全和量化边界。

## 5. 变更追踪

| 新功能/运算 | 依据 | 最小算例 | 预注册 |
|---|---|---|---|
| 二维 CRT、多图基数打包、域生成 | Milne、qCRT 对照；§2 项目推导 | §4 的 64 状态 | H1/H2/H4/H6 |
| 六位量化、RGB 与尺寸保留 | iFSQ 区分；Pillow；§2 误差证明 | 全部 256 通道值 | H1 |
| ROI / 整图写入 | RAGE/PIC-DNA 访问代价对照；§3 | 384 次局部变化 | H3/H4 |
| 整数实现、文件独立恢复与评测 | NumPy/Pillow 官方文档 | Python 大整数 oracle、禁止源图读取 | H5/H6/H7 |

H 编号与失败条件在 [PLAN_2D.md](./PLAN_2D.md) 固定。以上组合是项目工程推导，不以文献为未经验证的性能担保。
