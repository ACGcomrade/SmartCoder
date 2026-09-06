"""v0.4: append 12 real photos, test lazy CRT, and measure out-of-core RAM."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFont, ImageOps

from stream_memory import StreamMemory

ROOT = Path(__file__).resolve().parent


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):
            h.update(block)
    return h.hexdigest()


def tile_hashes(store):
    return {p.name:sha(p) for p in (store.directory/'tiles').iterdir()}


def photo(source):
    with Image.open(ROOT/'data'/'photos'/source['file']) as image:
        return np.array(ImageOps.exif_transpose(image).convert('RGB'))


def worker(bundle,mode,output=None):
    # Explicit dependency paths keep -I while supporting this machine's user-installed libs.
    deps = sorted({str(Path(np.__file__).resolve().parent.parent),str(Path(PIL.__file__).resolve().parent.parent)})
    code = ('import sys,json,runpy; sys.path.extend(json.loads(sys.argv.pop(1))); '
            'p=sys.argv.pop(1);sys.path.insert(0,p);runpy.run_path(p+"/bench_stream_memory.py",run_name="__main__")')
    args = [sys.executable,'-I','-B','-c',code,json.dumps(deps),str(bundle),
            str(bundle),mode,str(ROOT/'data'/'photos')]
    if output is not None:
        args.append(str(output))
    result = subprocess.run(args,capture_output=True,text=True,cwd=str(bundle))
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def install_code(bundle):
    for name in ('field_factory.py','stream_memory.py','bench_stream_memory.py'):
        shutil.copyfile(ROOT/name,bundle/name)


def main():
    tests = subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT),'-p','test_*memory*.py','-v'],capture_output=True,text=True,check=True)
    parent = ROOT/'artifacts'/'stream_demo'
    parent.mkdir(parents=True,exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='run_',dir=str(parent)))
    (out/'tests.txt').write_text(tests.stdout+tests.stderr)
    sources = json.loads((ROOT/'data'/'sources.json').read_text())+json.loads((ROOT/'data'/'sources_expanded.json').read_text())
    for s in sources:
        path = ROOT/'data'/'photos'/s['file']
        s.setdefault('url','https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/data/'+s['file'])
        s.setdefault('source_page','https://scikit-image.org/docs/stable/api/skimage.data.html')
        s['actual_sha256'] = sha(path)
        assert s['actual_sha256']==s['expected_sha256']
        with Image.open(path) as image:
            s['source_mode'] = image.mode
            s['shape'] = [image.height,image.width]
        s['file_bytes'] = path.stat().st_size
    assert len(sources)==12
    bundle = out/'bundle'
    store = StreamMemory.create(bundle,[s['shape'] for s in sources[:2]])
    growth = []
    start = time.perf_counter()
    for field in range(6):
        if field:
            before = tile_hashes(store)
            store.reset_stats()
            store.append_pair([s['shape'] for s in sources[2*field:2*field+2]])
            assert before==tile_hashes(store)
            assert store.stats['tile_reads']==store.stats['tile_writes']==0
        growth.append({'photos':2*field+2,'fields':store.factory.count,
                       'new_prime':store.factory.primes[-1],'modulus_bits':store.factory.modulus.bit_length(),
                       'append_old_tile_reads':0,'append_old_tile_writes':0})
        for index in (2*field,2*field+1):
            rgb = photo(sources[index])
            assert list(rgb.shape[:2])==sources[index]['shape']
            store.write_roi(index,rgb)
        del rgb
        print(f'Committed {2*field+2} photos / {field+1} generated fields',flush=True)
    encoding_seconds = time.perf_counter()-start
    install_code(bundle)

    # Independent direct-CRT oracle on 1000 fixed, shared spatial/channel coordinates.
    rng = np.random.default_rng(20260906)
    h,columns = store.shape
    coords = list(zip(rng.integers(0,h,1000),rng.integers(0,columns//3,1000),rng.integers(0,3,1000)))
    digits = [[] for _ in coords]
    for source in sources:
        rgb = photo(source)
        ih,iw,_ = rgb.shape
        for row,(y,x,c) in zip(digits,coords):
            row.append(int(rgb[y,x,c]//4) if y<ih and x<iw else 0)
    del rgb
    # Cache only this tile while checking grouped positions; no full-base oracle buffer.
    grouped = {}
    for i,(y,x,c) in enumerate(coords):
        grouped.setdefault((int(y)//64,int(x)//64),[]).append(i)
    for (ty,tx),indices in grouped.items():
        values,count = store._load_tile(ty,tx)
        values = store._lift_values(values,count)
        for i in indices:
            y,x,c = coords[i]
            assert values[((int(y)%64)*64+int(x)%64)*3+int(c)]==store.factory.encode(digits[i])

    # Each photo slot: cross-boundary ROI, compare all fields locally and every other tile hash.
    updates = []
    for index in range(12):
        before_hash = tile_hashes(store)
        original = [store.read_field_roi(k,56,56,16,16) for k in range(6)]
        patch = np.bitwise_xor(original[index//2][index%2],np.uint8(252))
        store.reset_stats()
        store.write_roi(index,patch,y=56,x=56)
        stats = dict(store.stats)
        assert stats['tile_reads']==stats['tile_writes']==4
        for k in range(6):
            pair = store.read_field_roi(k,56,56,16,16)
            for slot in range(2):
                expected = (patch//4)*4+2 if 2*k+slot==index else original[k][slot]
                assert np.array_equal(pair[slot],expected)
        after_hash = tile_hashes(store)
        changed = {name for name in before_hash if before_hash[name]!=after_hash[name]}
        assert changed <= {'0_0.bin','0_1.bin','1_0.bin','1_1.bin'}
        # Revert quantized contents; final store retains all originals.
        store.write_roi(index,original[index//2][index%2],y=56,x=56)
        updates.append({'photo':index,'stats':stats,'changed_tiles':sorted(changed)})

    recovery = worker(bundle,'recover',out/'recovered')
    print('Independent recovery finished; checking 12 originals',flush=True)
    metrics = []
    for i,s in enumerate(sources):
        rgb = photo(s)
        with Image.open(out/'recovered'/f'photo_{i}.png') as image:
            restored = np.array(image)
        assert rgb.shape==restored.shape and np.array_equal(restored,(rgb//4)*4+2)
        err = restored.astype(np.int16)-rgb.astype(np.int16)
        mse = float(np.mean(err.astype(float)**2))
        psnr = 10*math.log10(255**2/mse)
        assert int(np.abs(err).max())<=2 and psnr>=42.1102
        metrics.append({'name':s['name'],'shape':s['shape'],'field':i//2,'prime':store.factory.primes[i//2],
                        'max_error':int(np.abs(err).max()),'mse':mse,'psnr_db':psnr})
    del rgb,restored,err
    ram = []
    for repeat in range(3):
        for mode in ('open','roi','boundary','stream','eager'):
            row = worker(bundle,mode)
            row['repeat'] = repeat
            ram.append(row)
    roi = [r for r in ram if r['mode']=='roi']
    eager = [r for r in ram if r['mode']=='eager']
    assert len({r['checksum'] for r in roi+eager})==1
    assert all(r['stats']['tile_reads']==1 for r in roi)
    assert all(r['stats']['tile_reads']==4 for r in ram if r['mode']=='boundary')
    assert all(r['stats']['tile_reads']==0 for r in ram if r['mode']=='open')
    roi_delta = statistics.median(r['highwater_increase_bytes'] for r in roi)
    eager_delta = statistics.median(r['highwater_increase_bytes'] for r in eager)
    ram_pass = roi_delta<=8*2**20 and roi_delta<=max(2**20,eager_delta*.25)
    synthetic = synthetic_control(out)
    synth_pass = (len({r['stats']['raw_read_bytes'] for r in synthetic})==1
                  and all(r['stats']['tile_reads']==1 for r in synthetic)
                  and abs(synthetic[0]['highwater_increase_bytes']-synthetic[1]['highwater_increase_bytes'])<=4*2**20)
    result = {'version':'0.4.0','date':'2026-09-06','out':str(out),
              'hypotheses':{f'S{i}':('PASS' if (ram_pass if i==5 else synth_pass if i==6 else True) else 'FAIL') for i in range(1,8)},
              'photos':metrics,'sources':sources,'growth':growth,'local_updates':updates,
              'runtime':{'python':sys.version,'numpy':np.__version__,'pillow':PIL.__version__},
              'encoding_seconds':encoding_seconds,'independent_recovery':recovery,
              'ram':ram,'synthetic':synthetic,'roi_delta_median':roi_delta,'eager_delta_median':eager_delta,
              'shape':store.shape,'fields':store.factory.count,'primes':store.factory.primes,
              'modulus':str(store.factory.modulus),'cell_bytes':store.factory.cell_bytes,
              'disk_tile_bytes':sum(p.stat().st_size for p in (bundle/'tiles').iterdir()),
              'metadata_bytes':(bundle/'manifest.json').stat().st_size,
              'dense_current_schema_bytes':h*columns*store.factory.cell_bytes,
              'rgb_input_bytes':sum(s['shape'][0]*s['shape'][1]*3 for s in sources),
              'direct_oracle_samples':len(coords), 'bundle_tile_hashes':tile_hashes(store)}
    (out/'metrics.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    gallery(out,sources,metrics)
    report(result)
    print(json.dumps({'out':str(out),'hypotheses':result['hypotheses'],
                      'roi_delta_median':roi_delta,'eager_delta_median':eager_delta,
                      'peak_roi_median':statistics.median(r['peak_rss_bytes'] for r in roi),
                      'peak_eager_median':statistics.median(r['peak_rss_bytes'] for r in eager)},indent=2),flush=True)


def synthetic_control(out):
    results = []
    # Same non-photographic deterministic tile repeated spatially; clearly separated from photo count.
    for size in (512,2048):
        bundle = out/f'synthetic_{size}'
        store = StreamMemory.create(bundle,[(size,size)]*2)
        for _ in range(5):
            store.append_pair([(size,size)]*2)
        values = [store.factory.encode([(j*17+k*13)%64 for k in range(12)]) for j in range(64*64*3)]
        store._save_tile(0,0,values)
        template = store.tile_path(0,0).read_bytes()
        for ty,tx in store.tile_keys():
            if (ty,tx)!=(0,0):
                store.tile_path(ty,tx).write_bytes(template)
        install_code(bundle)
        row = worker(bundle,'roi')
        row['canvas_pixels'] = [size,size]
        row['dense_logical_bytes'] = size*size*3*store.factory.cell_bytes
        results.append(row)
    return results


def gallery(out,sources,metrics):
    canvas = Image.new('RGB',(1200,6*240+65),'#111827')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=16)
    draw.text((14,12),'SmartCoder v0.4 | 12 memories / 6 automatically generated fields',font=font,fill='white')
    draw.text((14,37),'Each card: ORIGINAL | RECOVERED. Native sizes retained in files.',font=font,fill='#93c5fd')
    for i,(source,metric) in enumerate(zip(sources,metrics)):
        cx,cy = (i%2)*600,65+(i//2)*240
        for side,path in enumerate((ROOT/'data'/'photos'/source['file'],out/'recovered'/f'photo_{i}.png')):
            with Image.open(path) as image:
                image = image.convert('RGB')
                image.thumbnail((280,190))
                canvas.paste(image,(cx+side*300+(300-image.width)//2,cy))
        draw.text((cx+12,cy+199),f"{i}: {source['name']} | F{metric['prime']} | {metric['psnr_db']:.2f} dB",font=font,fill='white')
    canvas.save(out/'comparison.png')


def report(r):
    rel = Path(r['out']).relative_to(ROOT)
    lines = ['# v0.4 实测：动态域生成与按需 RAM','','2026-09-06；前置研究 RESEARCH_STREAMING.md，预注册 PLAN_STREAMING.md。', '',
             f"结果：{r['hypotheses']}。12张不同图像；{r['fields']}个自动生成域；逻辑base形状{r['shape']}，当前cell字节宽{r['cell_bytes']}。",'',
             '## 结构增长','', '一个 FieldFactory 和一个参数化 decoder；照片逐对入库自动登记下一个素域。每次追加只写metadata，旧tile读取/写入均为0；旧hash保持。实际写新记忆时才局部lift、写回块。','',
             '| 入库照片 | 域数 | 新素数 | M位数 |','|---|---|---|---|']
    for g in r['growth']:
        lines.append(f"|{g['photos']}|{g['fields']}|{g['new_prime']}|{g['modulus_bits']}|")
    lines += ['','这支持容量事件驱动的结构增长，不是根据图像语义学得域，也不是智能涌现。prime实例数与decoder实例数仍各为6，通用代码不把实例数藏掉。','','## 恢复','',
              '| 照片 | H×W | 最大误差 | PSNR dB |','|---|---|---|---|']
    for p in r['photos']:
        lines.append(f"|{p['name']}|{p['shape'][0]}×{p['shape'][1]}|{p['max_error']}|{p['psnr_db']:.4f}|")
    lines += ['','全部量化结果精确，1000个独立直接CRT采样一致。12个槽分别跨4块修改，其他域结果和未命中块hash不变；测试后恢复原记忆，独立进程拒绝源图/网络访问完成全部恢复。','','## RAM：三个独立进程重复的中位数','',
              '| 操作 | 峰值RSS MiB | 相对启动高水位增量 MiB | tile读取数 | 文件读取字节 |','|---|---|---|---|---|']
    for mode in ('open','roi','boundary','stream','eager'):
        rows = [x for x in r['ram'] if x['mode']==mode]
        med = lambda key:statistics.median(x[key] for x in rows)
        lines.append(f"|{mode}|{med('peak_rss_bytes')/2**20:.3f}|{med('highwater_increase_bytes')/2**20:.3f}|{rows[0]['stats']['tile_reads']}|{rows[0]['stats']['file_read_bytes']}|")
    lines += ['', 'open只读metadata；roi为16×16块内双输出，boundary为跨四块双输出；stream逐块消费一个域的两张完整图；eager将全部base展开为同格式紧凑字节后做相同ROI，结果校验和相同。没有用Python对象列表故意放大全载基线。', '',
              f"S5={r['hypotheses']['S5']}，按预注册原阈值计算；高水位增量不是精确瞬时堆占用，也不是磁盘压缩率。RSS含解释器/依赖，不含整个系统文件缓存；未清理OS缓存，不比较冷盘速度。",'',
              '表中增量0表示未超过导入依赖时已达到的进程高水位，绝不表示没有使用RAM。ROI仍解压122880字节并创建大整数与输出数组；峰值RSS的绝对值是本轮更直观的比较。', '',
              '## 画布面积控制实验','', '| 合成画布 | 逻辑字节 | ROI增量MiB | 解压字节 |','|---|---|---|---|']
    for s in r['synthetic']:
        lines.append(f"|{s['canvas_pixels']}|{s['dense_logical_bytes']}|{s['highwater_increase_bytes']/2**20:.3f}|{s['stats']['raw_read_bytes']}|")
    lines += ['', f"S6={r['hypotheses']['S6']}；合成矩阵由重复确定性tile构成，只检验面积扩展，不计作照片，不声称数据超过机器物理RAM。",'',
              '## 持久空间与限制','',f"压缩tile总字节={r['disk_tile_bytes']}，metadata={r['metadata_bytes']}，当前schema逻辑稠密字节={r['dense_current_schema_bytes']}，全部输入RGB={r['rgb_input_bytes']}。tile可能保持旧schema；不能把文件差额全部归功于zlib。",'',
              '每个tile64×64像素，活动12288个cell；边缘tile也固定大小，存在填充。局部访问须解压整块；读取一个域仍要取该块承载全部域的cell。RAM随活动块数与log M增长，并不对记忆数量恒定。全图PNG输出另需图像缓冲，其独立恢复峰值在metrics中记录，不拿核心流式基准掩盖。', '',
              '分块的RAM收益也适用于其他存储结构，不是CRT专属优势。没有声称优于Zarr/数据库/按图懒加载基线；本轮比较对象明确是本实现全量紧凑载入。无并发和跨块事务，CRC32仅防偶然损坏。', '',
              '## 复现','', '```sh','python3 -m unittest discover -s . -p "test_*memory*.py" -v','python3 verify_base_case.py','python3 run_stream_demo.py','```','',
              '每次运行创建独立run目录，不覆盖旧成果。只恢复时，将bundle复制到有NumPy的环境，使用StreamMemory.iter_field；bench_stream_memory.py的recover模式需Pillow，且另有完整图片缓冲。', '',
              f'[机器可读指标]({rel}/metrics.json)', '', f'![12图对照]({rel}/comparison.png)','']
    (ROOT/'RESULTS_STREAMING.md').write_text('\n'.join(lines))


if __name__=='__main__':
    main()
