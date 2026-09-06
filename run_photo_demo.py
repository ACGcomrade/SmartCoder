"""Reproduce the preregistered six-photo experiment, including independent recovery."""
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFont, ImageOps

from memory2d import Memory2D, dequantize, quantize

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'artifacts' / 'photo_demo'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    # This gate runs on every reproduction, before loading any actual photo.
    test = subprocess.run([sys.executable, '-m', 'unittest', 'discover',
                           '-s', str(ROOT), '-p', 'test_memory2d.py', '-v'],
                          capture_output=True, text=True, check=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'base_case_test_log.txt').write_text(test.stdout + test.stderr)
    sources = json.loads((ROOT / 'data' / 'sources.json').read_text())
    photos = []
    for source in sources:
        path = ROOT / 'data' / 'photos' / source['file']
        source['actual_sha256'] = digest(path)
        if source['expected_sha256'] is not None:
            checked(source['actual_sha256'] == source['expected_sha256'], 'Pinned source hash mismatch')
        source['download_bytes'] = path.stat().st_size
        with Image.open(path) as image:
            source['original_mode'] = image.mode
            oriented = ImageOps.exif_transpose(image)
            photos.append(np.array(oriented.convert('RGB')))
        source['shape_hwc'] = list(photos[-1].shape)

    memory = Memory2D.bulk(photos)
    checked(len(memory.primes) == 3 and len(photos) == 6
            and len(memory.primes) <= len(photos)//2, 'H2 field budget failed')
    checked(all(len(memory.read_field(i)) == 2 for i in range(3)), 'H2 paired decoder failed')
    quantized = [quantize(p) for p in photos]
    for order in (list(range(6)), list(reversed(range(6)))):
        sequence = Memory2D(memory.shapes)
        for i in order:
            sequence.write(i, photos[i], whole=True)
        checked(np.array_equal(sequence.base, memory.base), 'Write-order mismatch')
    del sequence
    for a, b in zip(memory.read_all(), quantized):
        checked(np.array_equal(a, b), 'Quantized memory mismatch')

    local_stats, whole_stats = [], []
    for index in range(6):
        modified = Memory2D(memory.shapes, memory.base.copy())
        # A deterministic change to every selected channel, with no external editor.
        patch = np.bitwise_xor(photos[index][4:12, 5:14], np.uint8(252))
        stat = modified.write(index, patch, y=4, x=5)
        checked(stat['base_cells_read'] == 216 and stat['base_cells_written'] == 216,
                'ROI access count mismatch')
        mask = np.zeros(memory.base.shape, dtype=bool)
        mask[4:12, 15:42] = True
        checked(np.array_equal(memory.base[~mask], modified.base[~mask]), 'Nonlocal base mutation')
        expected = [a.copy() for a in quantized]
        expected[index][4:12, 5:14] = quantize(patch)
        checked(all(np.array_equal(a, b) for a, b in zip(expected, modified.read_all())),
                'ROI interference')
        local_stats.append(dict(photo=index, **stat))
        modified = Memory2D(memory.shapes, memory.base.copy())
        replacement = np.bitwise_xor(photos[index], np.uint8(252))
        stat = modified.write(index, replacement, whole=True)
        expected = [a.copy() for a in quantized]
        expected[index] = quantize(replacement)
        checked(all(np.array_equal(a, b) for a, b in zip(expected, modified.read_all())),
                'Whole-image interference')
        whole_stats.append(dict(photo=index, **stat))
    del modified, expected, mask

    bundle = OUT / 'bundle'
    memory.save(bundle)
    shutil.copyfile(ROOT / 'memory2d.py', bundle / 'memory2d.py')
    shutil.copyfile(ROOT / 'audit_recover.py', bundle / 'audit_recover.py')
    # -I isolates environment/user site; bundle explicitly placed on import path.
    command = ('import runpy,sys,json; deps=json.loads(sys.argv.pop(1)); '
               'sys.path.extend(deps); sys.path.insert(0,sys.argv[1]); '
               'p=sys.argv.pop(1); runpy.run_path(p+"/audit_recover.py",run_name="__main__")')
    dependencies = sorted({str(Path(np.__file__).resolve().parent.parent),
                           str(Path(PIL.__file__).resolve().parent.parent)})
    process = subprocess.run([sys.executable, '-I', '-B', '-c', command,
                              json.dumps(dependencies), str(bundle),
                              str(bundle), str(OUT / 'recovered'), str(ROOT / 'data' / 'photos')],
                             cwd=str(bundle), capture_output=True, text=True)
    if process.returncode:
        (OUT / 'recovery_failure.txt').write_text(process.stdout + process.stderr)
        raise RuntimeError(process.stderr)
    isolation = json.loads(process.stdout)
    recovered, metrics = [], []
    for i, (photo, source) in enumerate(zip(photos, sources)):
        with Image.open(OUT / 'recovered' / f'photo_{i}.png') as image:
            reconstruction = np.array(image)
        checked(reconstruction.shape == photo.shape, 'Size mismatch')
        checked(np.array_equal(reconstruction, dequantize(quantized[i])), 'Algebra introduced loss')
        error = reconstruction.astype(np.int16) - photo.astype(np.int16)
        mse = float(np.mean(error.astype(np.float64)**2))
        psnr = 10*math.log10(255**2/mse) if mse else float('inf')
        max_error = int(np.max(np.abs(error)))
        zero_mse = float(np.mean((photo.astype(np.float64)-2)**2))
        checked(max_error <= 2 and psnr >= 42.1102, 'H1 failed')
        checked(zero_mse > 4, 'H7 failed')
        metrics.append({'photo': i, 'name': source['name'], 'field_prime': memory.primes[i//2],
                        'shape_hwc': list(photo.shape), 'max_channel_error': max_error,
                        'mse': mse, 'psnr_db': psnr, 'zero_base_mse': zero_mse,
                        'quantized_mismatch_count': 0})
        recovered.append(reconstruction)

    storage = {'base_payload_bytes': memory.base.nbytes,
               'base_npy_bytes': (bundle/'base.npy').stat().st_size,
               'manifest_bytes': (bundle/'manifest.json').stat().st_size,
               'decoder_source_bytes': (bundle/'memory2d.py').stat().st_size,
               'audit_harness_bytes': (bundle/'audit_recover.py').stat().st_size,
               'input_rgb_bytes': sum(p.nbytes for p in photos),
               'direct_quantized_uint8_bytes': sum(p.nbytes for p in quantized),
               'direct_quantized_bitpacked_lower_bytes': math.ceil(sum(p.size for p in photos)*6/8),
               'download_bytes': sum(s['download_bytes'] for s in sources),
               'dense_crt_bitpacked_lower_bytes': math.ceil(memory.base.size*math.log2(memory.modulus)/8),
               'base_cells': memory.base.size,
               'decode_temporary_note': 'One full int64 residual is 8*base_cells bytes; '
                  'casts/modulo may overlap (~16*base_cells), plus cropped digit/output arrays. '
                  'Validation boolean arrays and library buffers add overhead. Not a measured peak RSS.'}
    results = {'version': '0.3.0', 'date': '2026-09-06',
               'runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'pillow': PIL.__version__},
               'base_shape': list(memory.base.shape), 'dtype': str(memory.base.dtype),
               'primes': memory.primes, 'modulus': memory.modulus, 'crt_weights': memory.weights,
               'int64_safety_bound': memory.modulus*max(memory.primes),
               'field_count': 3, 'fixed_decoder_count': 3, 'photo_count': 6,
               'hypotheses': {f'H{i}': 'PASS' for i in range(1,8)},
               'base_case': {'binary_states': 64, 'slot_updates': 384, 'integer_oracle_cases': 1000},
               'isolation': isolation, 'local_updates': local_stats, 'whole_updates': whole_stats,
               'storage': storage, 'photos': metrics, 'sources': sources,
               'artifact_hashes': {n: digest(bundle/n) for n in ('base.npy','manifest.json','memory2d.py')}}
    (OUT / 'metrics.json').write_text(json.dumps(results, indent=2, ensure_ascii=False)+'\n')
    make_comparison(photos, recovered, metrics)
    write_report(results)
    print(json.dumps({'hypotheses': results['hypotheses'], 'primes': memory.primes,
                      'base_shape': results['base_shape'], 'photos': metrics,
                      'storage': storage}, indent=2))


def make_comparison(photos, recovered, metrics):
    # Display-only thumbnails; storage/reconstruction use native dimensions.
    cell_w, row_h = 330, 230
    canvas = Image.new('RGB', (3*cell_w, 80+6*row_h), '#111827')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=16)
    draw.text((16, 12), 'SmartCoder | 6 photographs, 3 finite fields, ONE final 2-D base', fill='white', font=font)
    for c, title in enumerate(('Original (native input)', 'Recovered from final base', 'Absolute error x 64')):
        draw.text((16+c*cell_w, 46), title, fill='#93c5fd', font=font)
    for i, (a, b, metric) in enumerate(zip(photos, recovered, metrics)):
        err = np.clip(np.abs(a.astype(np.int16)-b.astype(np.int16))*64, 0, 255).astype(np.uint8)
        for col, array in enumerate((a, b, err)):
            img = Image.fromarray(array)
            img.thumbnail((cell_w-24, row_h-50))
            x = col*cell_w+(cell_w-img.width)//2
            y = 80+i*row_h
            canvas.paste(img, (x, y))
        label = f"{i}: {metric['name']} | {a.shape[1]}x{a.shape[0]} | F{metric['field_prime']} | PSNR {metric['psnr_db']:.2f} dB"
        draw.text((16, 80+i*row_h+row_h-35), label, fill='white', font=font)
    canvas.save(OUT / 'comparison.png')


def write_report(r):
    s = r['storage']
    lines = ['# 二维照片记忆实测结果 — v0.3.0', '',
             '2026-09-06；按 PLAN_2D.md 的预注册阈值运行。研究依据见 RESEARCH_2D.md。', '',
             '## 结论', '',
             'H1–H7 全部通过：六张照片写入同一个二维 base，三个固定素域各返回两张，原生尺寸恢复；存储运算不增加量化之外的损失。', '',
             f"base 为 {r['base_shape']} 的 uint64 矩阵，素数 {r['primes']}，M={r['modulus']}，CRT 权重={r['crt_weights']}。", '',
             '| 照片 | 尺寸 W×H | 域 | 最大通道误差 | PSNR dB | 零 base MSE |',
             '|---|---|---|---|---|---|']
    for p in r['photos']:
        h,w,_ = p['shape_hwc']
        lines.append(f"| {p['name']} | {w}×{h} | F{p['field_prime']} | {p['max_channel_error']} | {p['psnr_db']:.4f} | {p['zero_base_mse']:.2f} |")
    lines += ['', '## 验证记录', '',
              '- H1：全部量化数字零误差，所有图保持尺寸和比例；误差上界 2，理论 PSNR 下界 42.1102 dB。JPEG 输入以本地解码后的 RGB 为真值，不声称恢复拍摄时未压缩原片。硬币灰度图转 RGB，三通道相同。',
              '- H2：三个域、三个固定映射；每个映射输出两张，没有逐照片权重。参数仅 Q、素数、固定槽顺序、尺寸。',
              '- H3：六个槽各测试 8×9 ROI，仅读写 216 个 base cell；其他所有像素与其他五张图逐值保持。完整对照扫描属于验证，不计入写入算法。',
              '- H4：批量构建、正序六次整图写入、逆序六次整图写入完全一致；六个槽分别整图替换均无串扰。整图写入触及 3hw 个 cell。最终保存的 base 保持原六张照片，改动实验用副本。',
              '- H5：新 Python -I 进程，显式添加本机 NumPy/Pillow 安装路径及 bundle；拒绝原图目录访问，主动负对照被阻止，decoder 对原图读取尝试为 0。网络审计守卫启用。此钩子是测试证据，不是操作系统级隔离。',
              '- H6：64 小状态、384 次单槽更新、1000 个 Python 大整数对照通过；加上实际实现的不同尺寸、顺序、ROI 与非法输入测试。',
              '- H7：零 base 无法达到原图 MSE≤4；真正 base 全部达到。此对照只排除本数据上的空状态伪恢复。', '',
              '## 存储与代价（字节）', '', '| 项目 | 字节 |', '|---|---|']
    for key in ('base_payload_bytes','base_npy_bytes','manifest_bytes','decoder_source_bytes',
                'audit_harness_bytes','input_rgb_bytes','direct_quantized_uint8_bytes',
                'direct_quantized_bitpacked_lower_bytes','dense_crt_bitpacked_lower_bytes','download_bytes'):
        lines.append(f'| {key} | {s[key]} |')
    lines += ['', f"uint64 base / 原始 RGB = {s['base_payload_bytes']/s['input_rgb_bytes']:.3f} 倍。当前没有证明压缩优势。理论位打包下界并非已实现文件大小。", '',
              'base 每次完整域解码读取所有 cell，返回两张图；不是按内容关联查找。载入/构造时做一次全 base 合法性检查，之后 ROI 操作不重复全扫描。临时余数约 8×cell 数字节，转换/取模重叠可约 16×cell 数，加输出及校验数组；不是实测峰值内存。局部更新的临时空间随 ROI 增长。没有宣称磁盘页级局部 I/O 或性能领先。', '',
              'dense_crt_bitpacked_lower_bytes 是允许所有 M 种 cell 状态时的稠密表示计数下界，不利用合法照片码字/填充约束；不是本照片集的最低存储量，也不是已实现压缩器。原始下载文件已有 JPEG/PNG 编码；其大小与 RGB 字节数不是同一基准。', '',
              '## 复现', '',
              '从 SmartCoder 目录运行：', '', '```sh', 'python3 -m unittest discover -s . -p test_memory2d.py -v',
              'python3 verify_base_case.py', 'python3 run_photo_demo.py',
              '# 独立复制 bundle 后，在装有 NumPy/Pillow 的环境恢复：',
              'python3 artifacts/photo_demo/bundle/memory2d.py artifacts/photo_demo/bundle /tmp/smartcoder-recovered', '```', '',
              '运行器不会重新下载照片；输入哈希不符立即失败。data/sources.json 是下载清单，metrics.json 保存本次实际 SHA256、原始模式、运行时版本与 bundle 哈希。', '',
              '## 实现调试记录', '',
              '首轮独立进程启动失败：-I 不加载本机用户 site-packages，无法导入 NumPy。修正为显式加入已安装 NumPy/Pillow 的路径；没有放开原图读取或改动 H1–H7 阈值，随后重跑完整实验。', '',
              '## 边界与下一阶段', '',
              '这是受约束的二维编码记忆，不是智能涌现。单个域只读出其两张照片，不具有对完整 base 的单射性；原始 8 位像素因量化也不是单射。固定尺寸，增加记忆或域需要另行研究与容量/溢出设计。当前没有纠错、自动定位变化、联想检索、学习 decoder 或跨照片内容压缩。', '',
              '![原图、重建与放大误差](./artifacts/photo_demo/comparison.png)', '']
    (ROOT / 'RESULTS_2D.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
