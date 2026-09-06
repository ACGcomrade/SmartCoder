"""Fresh-process RAM measurement: no input image decoding, equal imports for all modes."""
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys
import time

import numpy as np
from PIL import Image

from stream_memory import StreamMemory


def peak_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform=='darwin' else value*1024)


def main():
    directory,mode,forbidden = Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3]).resolve()
    def guard(event,args):
        if event.startswith('socket.'):
            raise PermissionError('No network during recovery/benchmark')
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path==forbidden or forbidden in path.parents:
                raise PermissionError('No source-photo access')
    sys.addaudithook(guard)
    # Verify the guard before recording the baseline for every mode.
    try:
        (forbidden/'grace_hopper.jpg').read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError('Guard is inactive')
    baseline = peak_bytes()
    start = time.perf_counter()
    store = StreamMemory(directory)
    digest = hashlib.sha256()
    if mode in ('roi','boundary'):
        y,x = (8,8) if mode=='roi' else (56,56)
        pair = store.read_field_roi(0,y,x,16,16)
        for image in pair:
            digest.update(image.tobytes())
    elif mode=='stream':
        for y,x,pair in store.iter_field(0):
            for image in pair:
                digest.update(image.tobytes())
    elif mode=='eager':
        # Same compact current-schema cell bytes, not a bloated Python-object baseline.
        # Holding and hashing the buffer forces all its data pages to be touched.
        packed = bytearray()
        for ty,tx in store.tile_keys():
            packed.extend(store.logical_tile_bytes(ty,tx))
        all_digest = hashlib.sha256(packed).hexdigest()
        width = store.factory.cell_bytes
        pair = [np.empty((16,16,3),dtype=np.uint8) for _ in range(2)]
        for y in range(16):
            for x in range(16):
                for c in range(3):
                    offset = (((y+8)*store.tile+x+8)*3+c)*width  # ROI within first tile
                    v = int.from_bytes(packed[offset:offset+width],'little')
                    a,b = store.factory.project_pair(v,0)
                    pair[0][y,x,c],pair[1][y,x,c] = 4*a+2,4*b+2
        for image in pair:
            digest.update(image.tobytes())
    elif mode=='recover':
        output = Path(sys.argv[4])
        output.mkdir(parents=True,exist_ok=True)
        for field in range(store.factory.count):
            # Full-picture assembly is deliberately separate from streaming RAM claims.
            shapes = store.meta['shapes'][2*field:2*field+2]
            images = [np.empty((h,w,3),dtype=np.uint8) for h,w in shapes]
            for y,x,pair in store.iter_field(field):
                for slot,(h,w) in enumerate(shapes):
                    hh,ww = min(pair[slot].shape[0],h-y),min(pair[slot].shape[1],w-x)
                    if hh>0 and ww>0:
                        images[slot][y:y+hh,x:x+ww] = pair[slot][:hh,:ww]
            for slot,image in enumerate(images):
                Image.fromarray(image).save(output/f'photo_{2*field+slot}.png')
                digest.update(image.tobytes())
    elif mode!='open':
        raise ValueError('Unknown mode')
    peak = peak_bytes()
    print(json.dumps({'mode':mode, 'baseline_peak_bytes':baseline, 'peak_rss_bytes':peak,
                      'highwater_increase_bytes':max(0,peak-baseline),
                      'seconds':time.perf_counter()-start,'checksum':digest.hexdigest(),
                      'stats':store.stats,'source_guard':True,'network_guard':True,
                      'packed_buffer_bytes':len(packed) if mode=='eager' else 0}))


if __name__=='__main__':
    main()
