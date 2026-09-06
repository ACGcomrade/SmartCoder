"""A single logical 2-D CRT base, stored as independently compressed spatial tiles."""
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import zlib

import numpy as np

from field_factory import FieldFactory, family

HEADER = struct.Struct('<4sIBII')  # magic, schema count, codec, raw size, CRC32


def atomic_bytes(path, data):
    fd, name = tempfile.mkstemp(prefix=path.name+'.pending-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class StreamMemory:
    def __init__(self, directory, writable=False):
        self.directory = Path(directory)
        path = self.directory / 'manifest.json'
        blob = path.read_bytes()
        self.meta = json.loads(blob)
        if self.meta.get('format') != 'smartcoder-stream-v1' or self.meta.get('q') != 64:
            raise ValueError('Unsupported format')
        shapes = self.meta['shapes']
        if len(shapes)%2 or not shapes or any(len(s)!=2 or any(type(v)!=int or v<=0 for v in s) for s in shapes):
            raise ValueError('Invalid photo shapes')
        self.tile = self.meta['tile_pixels']
        if type(self.tile) != int or not 1 <= self.tile <= 256:
            raise ValueError('Invalid tile size')
        if self.meta['codec'] not in (0, 1):
            raise ValueError('Invalid codec')
        self.writable = writable
        self.factory = FieldFactory(len(shapes)//2)
        if self.meta['primes'] != list(self.factory.primes):
            raise ValueError('Noncanonical field catalogue')
        self.reset_stats()
        self.stats['metadata_read_bytes'] = len(blob)

    @classmethod
    def create(cls, directory, shapes, tile=64, compressed=True):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if (directory/'manifest.json').exists() or (directory/'tiles').exists():
            raise FileExistsError('Refusing to overwrite an existing store')
        if len(shapes) != 2:
            raise ValueError('Initialize with one pair; append pairs for growth')
        factory = FieldFactory(1)
        meta = {'format':'smartcoder-stream-v1', 'q':64, 'tile_pixels':tile,
                'codec':int(compressed), 'shapes':[list(s) for s in shapes],
                'primes':list(factory.primes)}
        (directory/'tiles').mkdir()
        atomic_bytes(directory/'manifest.json', json.dumps(meta, indent=2).encode())
        return cls(directory, writable=True)

    @property
    def shape(self):
        return max(s[0] for s in self.meta['shapes']), max(s[1] for s in self.meta['shapes'])*3

    def reset_stats(self):
        self.stats = dict(metadata_read_bytes=0, tile_reads=0, tile_writes=0,
                          file_read_bytes=0, file_write_bytes=0, raw_read_bytes=0,
                          max_active_cells=0, lifted_cells=0)

    def append_pair(self, shapes):
        if not self.writable:
            raise PermissionError('Read-only store')
        if len(shapes)!=2 or any(len(s)!=2 or any(type(v)!=int or v<=0 for v in s) for s in shapes):
            raise ValueError('Append two positive photo shapes')
        first = len(self.meta['shapes'])
        self.factory = FieldFactory(self.factory.count+1)
        self.meta['shapes'].extend([list(s) for s in shapes])
        self.meta['primes'] = list(self.factory.primes)
        atomic_bytes(self.directory/'manifest.json', json.dumps(self.meta, indent=2).encode())
        return first, first+1

    def tile_path(self, ty, tx):
        return self.directory/'tiles'/f'{ty}_{tx}.bin'

    def _load_tile(self, ty, tx):
        path = self.tile_path(ty, tx)
        cells = self.tile*self.tile*3
        self.stats['max_active_cells'] = max(self.stats['max_active_cells'], cells)
        if not path.exists():
            return [0]*cells, self.factory.count
        blob = path.read_bytes()
        self.stats['tile_reads'] += 1
        self.stats['file_read_bytes'] += len(blob)
        if len(blob)<HEADER.size:
            raise ValueError('Truncated tile header')
        magic, count, codec, rawsize, crc = HEADER.unpack(blob[:HEADER.size])
        if magic != b'SC04' or not 1<=count<=self.factory.count or codec not in (0,1):
            raise ValueError('Invalid tile schema')
        _, modulus, _ = family(64, count)
        width = ((modulus-1).bit_length()+7)//8
        expected = cells*width
        if rawsize != expected:
            raise ValueError('Invalid tile raw size')
        if codec:
            inflater = zlib.decompressobj()
            raw = inflater.decompress(blob[HEADER.size:], expected+1)
            if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
                raise ValueError('Invalid compressed tile')
        else:
            raw = blob[HEADER.size:]
        if len(raw)!=expected or zlib.crc32(raw)!=crc:
            raise ValueError('Tile checksum/length mismatch')
        self.stats['raw_read_bytes'] += len(raw)
        values = [int.from_bytes(raw[i:i+width], 'little') for i in range(0,len(raw),width)]
        if any(v>=modulus for v in values):
            raise ValueError('Noncanonical tile cell')
        return values, count

    def _lift_values(self, values, count):
        modulus = family(64,count)[1]
        for p in self.factory.primes[count:]:
            inverse = pow(modulus,-1,p)
            values = [v+modulus*((-v*inverse)%p) for v in values]
            modulus *= p
        if count<self.factory.count:
            self.stats['lifted_cells'] += len(values)
        return values

    def _save_tile(self, ty, tx, values):
        if not self.writable:
            raise PermissionError('Read-only store')
        width = self.factory.cell_bytes
        raw = b''.join(v.to_bytes(width,'little') for v in values)
        header = HEADER.pack(b'SC04', self.factory.count, self.meta['codec'], len(raw), zlib.crc32(raw))
        blob = header+(zlib.compress(raw,1) if self.meta['codec'] else raw)
        atomic_bytes(self.tile_path(ty,tx),blob)
        self.stats['tile_writes'] += 1
        self.stats['file_write_bytes'] += len(blob)

    def tile_keys(self):
        h, columns = self.shape
        for ty in range(math.ceil(h/self.tile)):
            for tx in range(math.ceil((columns//3)/self.tile)):
                yield ty,tx

    def read_field_roi(self, field, y, x, h, w):
        """Always returns BOTH decoder outputs for this ROI. No photo-specific map."""
        height, columns = self.shape
        if type(field)!=int or not 0<=field<self.factory.count:
            raise ValueError('Unregistered field')
        if min(y,x)<0 or min(h,w)<=0 or y+h>height or x+w>columns//3:
            raise ValueError('ROI outside logical base')
        output = [np.full((h,w,3),2,dtype=np.uint8) for _ in range(2)]
        t = self.tile
        for ty in range(y//t, (y+h-1)//t+1):
            for tx in range(x//t, (x+w-1)//t+1):
                values,count = self._load_tile(ty,tx)
                y0,x0 = max(y,ty*t),max(x,tx*t)
                y1,x1 = min(y+h,(ty+1)*t),min(x+w,(tx+1)*t)
                for yy in range(y0,y1):
                    start = ((yy-ty*t)*t+x0-tx*t)*3
                    residues = [v%self.factory.primes[field] for v in values[start:start+(x1-x0)*3]] if field<count else [0]*((x1-x0)*3)
                    if any(r>=4096 for r in residues):
                        raise ValueError('Unused digit-pair residue')
                    r = np.asarray(residues,dtype=np.uint16).reshape(x1-x0,3)
                    output[0][yy-y,x0-x:x1-x] = ((r%64)*4+2).astype(np.uint8)
                    output[1][yy-y,x0-x:x1-x] = ((r//64)*4+2).astype(np.uint8)
        return tuple(output)

    def iter_field(self, field):
        if type(field)!=int or not 0<=field<self.factory.count:
            raise ValueError('Unregistered field')
        pair = self.meta['shapes'][2*field:2*field+2]
        h,w = max(s[0] for s in pair), max(s[1] for s in pair)
        for y in range(0,h,self.tile):
            for x in range(0,w,self.tile):
                yield y,x,self.read_field_roi(field,y,x,min(self.tile,h-y),min(self.tile,w-x))

    def write_roi(self, photo, rgb, y=0, x=0):
        if not self.writable:
            raise PermissionError('Read-only store')
        if type(photo)!=int or not 0<=photo<len(self.meta['shapes']):
            raise ValueError('Unknown photo')
        if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:
            raise ValueError('Expected uint8 RGB')
        h,w,_ = rgb.shape
        ih,iw = self.meta['shapes'][photo]
        if min(y,x)<0 or min(h,w)<=0 or y+h>ih or x+w>iw:
            raise ValueError('Invalid photo ROI')
        field,slot = divmod(photo,2)
        p,e,m = self.factory.primes[field],self.factory.weights[field],self.factory.modulus
        t = self.tile
        for ty in range(y//t,(y+h-1)//t+1):
            for tx in range(x//t,(x+w-1)//t+1):
                values,count = self._load_tile(ty,tx)
                values = self._lift_values(values,count)
                y0,x0 = max(y,ty*t),max(x,tx*t)
                y1,x1 = min(y+h,(ty+1)*t),min(x+w,(tx+1)*t)
                digits = (rgb[y0-y:y1-y,x0-x:x1-x]//4).reshape(y1-y0,(x1-x0)*3)
                for yy in range(y0,y1):
                    start = ((yy-ty*t)*t+x0-tx*t)*3
                    for c,new_digit in enumerate(digits[yy-y0]):
                        pos = start+c
                        residue = values[pos]%p
                        if residue>=4096:
                            raise ValueError('Unused digit-pair residue')
                        old_digit = residue//(64**slot)%64
                        delta = ((int(new_digit)-old_digit)*(64**slot))%p
                        values[pos] = (values[pos]+delta*e)%m
                self._save_tile(ty,tx,values)

    def logical_tile_bytes(self, ty, tx):
        values,count = self._load_tile(ty,tx)
        values = self._lift_values(values,count)
        return b''.join(v.to_bytes(self.factory.cell_bytes,'little') for v in values)
