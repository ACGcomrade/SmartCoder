# v0.4 研究：按需 RAM 与可增长的统一域生成法

检索日 2026-09-06。先建立本研究及 PLAN.md，运行小算例之后再扩展照片实验。用户本轮明确区分持久记忆容量与运行 RAM，并要求 systematic methodology，而不是手工设计 n 个方法。

## 1. 原实现的问题与本轮研究

v0.3 的素数已有 next-prime 规则，但数量、槽数和 decoder 接口固定为 3/6；不支持动态增长。`np.load(mmap_mode='r')` 后仍进行全 base 比较，并在解码时 `base.astype(int64)`，所以文件映射不等于有界 RAM。这个事实来自 memory2d.py 代码检查，不是先前测过的 RAM 结果。

| 一手来源与阅读范围 | 支持及本轮采用/不采用 |
|---|---|
| [Larger than memory image processing](https://arxiv.org/html/2601.18407v1)，Sporring、Stansby，2026-01-26；摘要、流式/window/tiling 相关正文 | 图像处理的工作集与访问次序需共同设计。本轮采用有界块流，不把该论文的 PB 级系统或速度成绩当成我们的结果 |
| [Zarr 最新分块/分片性能文档](https://zarr.readthedocs.io/en/latest/user-guide/performance/)，同日查阅 | chunk 是独立读取单位；chunk/shard 粒度影响读取放大及写入成本。本轮仅借鉴分块原则，使用小型自描述 CRT 字节块+zlib；不宣称文件符合 Zarr 标准 |
| [NumPy memmap](https://numpy.org/doc/stable/reference/generated/numpy.memmap.html)，同日查阅 | 支持访问文件局部，但整数组运算仍可分配整数组。新实现不用全 base ndarray，也不依赖操作系统按需分页来掩盖全扫描 |
| [Python zlib](https://docs.python.org/3/library/zlib.html)、[resource](https://docs.python.org/3/library/resource.html)，同日查阅 | 块压缩/解压接口、资源高水位统计。分别统计磁盘压缩字节、解压工作集、进程峰值 RSS；不把 OS 文件缓存等同于 Python 堆或进程私有 RAM |
| [Sage 有限域构造器](https://doc.sagemath.org/html/en/reference/finite_rings/sage/rings/finite_rings/finite_field_constructor.html)，同日查阅；Milne R1 沿用 | 有限域可由素数幂阶构造，扩域需不可约多项式；同阶不同多项式通常只是同构表示，并不自动创造不同信息容量。本轮选择无限素域序列，不需要手写每个域 |
| [Pseudo-Deterministic Construction of Irreducible Polynomials over Finite Fields](https://arxiv.org/abs/2410.04071)，Rai，2024-10-05 v1；摘要/版本 | 研究自动构造不可约多项式的算法；此次最新检索未找到可直接取代当前小素域生成器的已读 2026 成果。保留为将来扩域的算法依据，不谎称已实现其算法 |
| [Improvement of a Montgomery Multiplication Algorithm in Single-Base Residue Number System](https://globals.ieice.org/en_transactions/fundamentals/10.1587/transfun.2025DMP0006/_f)，Kawamura、Komano、Fujimoto；2026-03-26 在线公开、2026-09-01 出版；§2.3/§5.4/§6 | 研究 RNS 基转换与模乘开销。其通常保留同一整数的额外余数；**本项目下面是增加一个独立且初值为零的记忆分量，不是同一整数的标准 base extension**，证明独立给出 |

检索词：finite fields construction irreducible polynomials 2025/2026、RNS base extension 2025/2026、out-of-core image processing 2026、Zarr chunked memory、NumPy memmap。非穷尽性综述。最新 qCRT 文献沿用 RESEARCH_2D，不引入无关加密/生成模型来代替可行性证明。

## 2. 一个生成族，不是 n 段解码程序

固定量化精度 b=6、Q=2^b，每域承载 s=2 个数字。定义

    p_0 = 最小的 ≥ Q² 的素数
    p_(k+1) = 最小的 > p_k 的素数
    F_k = Z/p_kZ
    D(k,B,ROI) = unpack_Q(canonical(B[ROI] mod p_k))

试除到 √p 是确定性素性验证；素数无限保证数学构造可继续。一个通用 `FieldFactory` 根据数量生成任意所需前缀，一个通用 decoder 接受工厂签发的序号。不同实例仍计为 K 个 decoder / K 个域，不能因为共用函数就计为 1。输入照片只决定入库次序、尺寸，不提供专属数学函数/权重。每次收到一对新照片，容量策略自动分配下一个域，K=N/2；不接受奇数照片的已提交批次，避免违反域数上限。

这是**容量事件驱动的结构增长**：入库事件→生成素域→登记尺寸→写入局部空间块。生成规则固定但结构数目动态。尚不是从图像内容学出域、学习记忆关系或自发智能。有限域都是已有数学对象，本轮自动生成可计算表示及关联 decoder，不宣称发明新的域论。

## 3. 同一个二维 base 的延迟扩展

K 个域对应 M_K=∏p_i，逻辑 B_K∈(Z/M_K Z)^(H×3W)。K 增长后乘积很快超过 uint64；使用 Python 精确大整数，仅在活动块内展开。每 cell 固定字节宽 w_K=ceil(bit_length(M_K−1)/8)。不把多个 uint64 分组伪称一个相同的 CRT base。

增加素数 p，旧 cell b∈[0,M) 映射为

    L(b) = b + M·((-b·M^(-1)) mod p),  0≤L(b)<Mp.

于是 L(b) mod M=b，L(b) mod p=0。旧全部余数不变，新域初始化为零；由 CRT 唯一。加入新域不是“原 b 直接再 mod p”，后者通常误读出非零假记忆。

磁盘每个空间 tile 保存其 schema K_t 及旧精确 cell；当前逻辑值定义为对 K_t→K 的 L 复合。旧域可直接取旧 b 的余数，新域若超过 K_t 则返回 0；这与显式 L 后投影相同。只在该块发生写入时实体化 L。这是一张二维 base 的版本化延迟序列化，不是每域各存一份图片。append 只改 metadata，不读写旧像素块；旧文件 hash 应保持。空间画布同样用固定 tile 网格增长，未建立块表示零，边缘块固定尺寸无需重排旧数据。

局部槽写入仍用 CRT 幂等元更新：r′=r+Q^s(q′−q)，B′=(B+e_k((r′−r) mod p_k)) mod M_K。块级压缩导致触及整个命中 tile，而不再声称磁盘只写 3hw cell。块文件采用 zlib level=1 + 标头(schema、raw 大小、CRC32)，每次访问校验该块，不在 open 时全量校验。CRC32 只检测意外损坏，不是对抗篡改认证；单块原子替换，跨块/并发事务不在本轮实现。

## 4. 手算和 RAM 边界

Q=2：前三素数为5、7、11。先在 M=35 存 r=(1,2)，b=16。新增 p=11，35^(-1) mod11=6，所以 L(16)=16+35·3=121；投影=(1,2,0)。新域写 r=3：e_11=210，B′=(121+3·210) mod385=366，投影=(1,2,3)。前四位仍是(1,0,0,1)，后两位为(1,1)。新域再次追加后的旧块读出同样由归纳成立。

若 tile 为 T×T 像素，活动 cell≤3T²，单块精确整数占 O(T²·log M_K) 位外加 Python 对象开销；局部输出占 O(ROI面积)，流式全图每次只返回两个 tile，不积累所有图。metadata 占 O(K)，不是 O(1)。因此 RAM 对画布面积可以有界，但对记忆数 K/单 cell 位宽并非严格常数。读取小 ROI 需要全部命中块，各块必须解压才能投影一个域；不是只读取所选域的理论信息位数。

输出完整 PNG 的编码器和输入 JPEG/PNG 的解码器可能需要单张图缓冲。本轮核心流 API/内存基准只消费块并产生校验和，不把图片展示/评估时的全图缓冲隐藏在核心 RAM 数字里。分块/按需读取是已有系统也能使用的机制；RAM 相对全量加载的优势不等于 CRT 独有优势。
