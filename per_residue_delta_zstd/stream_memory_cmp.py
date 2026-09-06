"""Per-residue-plane delta+lzma CRT memory.

Tile format (codec=2, magic=b'SC05'):
  Header: magic(4) schema_count(4B LE) codec(1B) raw_size(4B LE) crc32(4B LE) = 17 bytes
  Body:   lzma-compressed payload of 2*K planes × T*T*3 uint8 values, each plane
          row-delta-filtered (Sub: delta[i,j] = (plane[i,j] - plane[i,j-1]) % 256,
          first column delta = plane[i,0] itself).

Storage equivalence: plane[2k][cell] = field-k residue mod Q,
                     plane[2k+1][cell] = field-k residue // Q.
Schema extension: new fields get zero-planes (no CRT lift arithmetic needed).
"""
import json
import lzma
import math
import os
from pathlib import Path
import struct
import tempfile

import numpy as np

from field_factory import FieldFactory, family

HEADER = struct.Struct('<4sIBII')   # magic, schema_count, codec, raw_size, crc32
MAGIC  = b'SC05'
CODEC  = 2


def _crc32(data):
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def atomic_bytes(path, data):
    fd, name = tempfile.mkstemp(prefix=path.name + '.pending-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _delta_encode(plane: np.ndarray) -> np.ndarray:
    """Apply Sub (horizontal) delta filter, result stored as uint8."""
    out = np.empty_like(plane)
    out[:, 0] = plane[:, 0]
    out[:, 1:] = (plane[:, 1:].astype(np.int16) - plane[:, :-1].astype(np.int16)) % 256
    return out.astype(np.uint8)


def _delta_decode(encoded: np.ndarray) -> np.ndarray:
    """Invert Sub delta filter."""
    out = encoded.copy().astype(np.int32)
    for j in range(1, encoded.shape[1]):
        out[:, j] = (out[:, j] + out[:, j - 1]) % 256
    return out.astype(np.uint8)


class StreamMemoryCmp:
    def __init__(self, directory, writable=False):
        self.directory = Path(directory)
        path = self.directory / 'manifest.json'
        blob = path.read_bytes()
        self.meta = json.loads(blob)
        if self.meta.get('format') != 'smartcoder-stream-cmp-v1' or self.meta.get('q') != 64:
            raise ValueError('Unsupported format')
        shapes = self.meta['shapes']
        if len(shapes) % 2 or not shapes or any(len(s) != 2 or any(type(v) != int or v <= 0 for v in s) for s in shapes):
            raise ValueError('Invalid photo shapes')
        self.tile = self.meta['tile_pixels']
        if type(self.tile) != int or not 1 <= self.tile <= 256:
            raise ValueError('Invalid tile size')
        self.writable = writable
        self.factory = FieldFactory(len(shapes) // 2)
        if self.meta['primes'] != list(self.factory.primes):
            raise ValueError('Noncanonical field catalogue')
        self.reset_stats()
        self.stats['metadata_read_bytes'] = len(blob)

    @classmethod
    def create(cls, directory, shapes, tile=64):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if (directory / 'manifest.json').exists() or (directory / 'tiles').exists():
            raise FileExistsError('Refusing to overwrite an existing store')
        if len(shapes) != 2:
            raise ValueError('Initialize with one pair; append pairs for growth')
        factory = FieldFactory(1)
        meta = {
            'format': 'smartcoder-stream-cmp-v1', 'q': 64, 'tile_pixels': tile,
            'codec': CODEC, 'shapes': [list(s) for s in shapes],
            'primes': list(factory.primes),
        }
        (directory / 'tiles').mkdir()
        atomic_bytes(directory / 'manifest.json', json.dumps(meta, indent=2).encode())
        return cls(directory, writable=True)

    @property
    def shape(self):
        return (max(s[0] for s in self.meta['shapes']),
                max(s[1] for s in self.meta['shapes']) * 3)

    def reset_stats(self):
        self.stats = dict(metadata_read_bytes=0, tile_reads=0, tile_writes=0,
                          file_read_bytes=0, file_write_bytes=0, raw_read_bytes=0,
                          max_active_cells=0)

    def append_pair(self, shapes):
        if not self.writable:
            raise PermissionError('Read-only store')
        if len(shapes) != 2 or any(len(s) != 2 or any(type(v) != int or v <= 0 for v in s) for s in shapes):
            raise ValueError('Append two positive photo shapes')
        self.factory = FieldFactory(self.factory.count + 1)
        self.meta['shapes'].extend([list(s) for s in shapes])
        self.meta['primes'] = list(self.factory.primes)
        atomic_bytes(self.directory / 'manifest.json', json.dumps(self.meta, indent=2).encode())

    def tile_path(self, ty, tx):
        return self.directory / 'tiles' / f'{ty}_{tx}.bin'

    # ---- tile I/O (per-plane format) ------------------------------------

    def _load_planes(self, ty, tx):
        """Return planes[2K][T*T*3] as uint8 array, schema_count of the file."""
        path = self.tile_path(ty, tx)
        t = self.tile
        cells = t * t * 3
        K = self.factory.count
        self.stats['max_active_cells'] = max(self.stats['max_active_cells'], cells)
        if not path.exists():
            return np.zeros((2 * K, t * t * 3), dtype=np.uint8), K

        blob = path.read_bytes()
        self.stats['tile_reads'] += 1
        self.stats['file_read_bytes'] += len(blob)
        if len(blob) < HEADER.size:
            raise ValueError('Truncated tile')
        magic, count, codec, rawsize, crc = HEADER.unpack(blob[:HEADER.size])
        if magic != MAGIC or codec != CODEC or not 1 <= count <= K:
            raise ValueError('Invalid tile header')
        expected = 2 * count * cells
        if rawsize != expected:
            raise ValueError('Invalid tile raw size')
        raw = lzma.decompress(blob[HEADER.size:])
        if len(raw) != expected:
            raise ValueError('Decompressed size mismatch')
        if _crc32(raw) != crc:
            raise ValueError('CRC32 mismatch')
        self.stats['raw_read_bytes'] += len(raw)

        # Decode delta: reshape to (2*count, t*t, 3), then delta along columns
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(2 * count, t * t, 3)
        # Treat each plane as a t×t×3 row of cells; delta was encoded per "pixel row" of T cells
        # We stored planes flattened as T*T*3 sequential, delta along axis-1 (column of cells*3)
        planes_file = np.empty((2 * count, t * t * 3), dtype=np.uint8)
        for p in range(2 * count):
            flat = arr[p]   # shape (t*t, 3)
            # encoded as 2D (t rows of t*3 uint8): undo delta
            encoded_2d = flat.reshape(t, t * 3)
            decoded_2d = _delta_decode(encoded_2d)
            planes_file[p] = decoded_2d.reshape(t * t * 3)

        # Pad new fields with zeros if schema has grown
        if count < K:
            padded = np.zeros((2 * K, t * t * 3), dtype=np.uint8)
            padded[:2 * count] = planes_file
            return padded, count
        return planes_file, count

    def _save_planes(self, ty, tx, planes):
        """planes: uint8 array shape (2*K, T*T*3)."""
        if not self.writable:
            raise PermissionError('Read-only store')
        t = self.tile
        K = self.factory.count
        cells = t * t * 3
        assert planes.shape == (2 * K, cells)

        arr = np.empty((2 * K, t * t, 3), dtype=np.uint8)
        for p in range(2 * K):
            plane_2d = planes[p].reshape(t, t * 3)
            arr[p] = _delta_encode(plane_2d).reshape(t * t, 3)

        raw = arr.astype(np.uint8).tobytes()
        crc = _crc32(raw)
        compressed = lzma.compress(raw, format=lzma.FORMAT_XZ, preset=1)
        header = HEADER.pack(MAGIC, K, CODEC, len(raw), crc)
        blob = header + compressed
        atomic_bytes(self.tile_path(ty, tx), blob)
        self.stats['tile_writes'] += 1
        self.stats['file_write_bytes'] += len(blob)

    # ---- public read/write API ------------------------------------------

    def tile_keys(self):
        h, columns = self.shape
        for ty in range(math.ceil(h / self.tile)):
            for tx in range(math.ceil((columns // 3) / self.tile)):
                yield ty, tx

    def read_field_roi(self, field, y, x, h, w):
        """Return (img0, img1) uint8 RGB arrays for this ROI."""
        height, columns = self.shape
        if type(field) != int or not 0 <= field < self.factory.count:
            raise ValueError('Unregistered field')
        if min(y, x) < 0 or min(h, w) <= 0 or y + h > height or x + w > columns // 3:
            raise ValueError('ROI outside logical base')
        t = self.tile
        output = [np.full((h, w, 3), 2, dtype=np.uint8) for _ in range(2)]
        for ty in range(y // t, (y + h - 1) // t + 1):
            for tx in range(x // t, (x + w - 1) // t + 1):
                planes, _ = self._load_planes(ty, tx)
                plane_lo = planes[2 * field]    # slot 0
                plane_hi = planes[2 * field + 1]  # slot 1
                y0, x0 = max(y, ty * t), max(x, tx * t)
                y1, x1 = min(y + h, (ty + 1) * t), min(x + w, (tx + 1) * t)
                for yy in range(y0, y1):
                    start = ((yy - ty * t) * t + x0 - tx * t) * 3
                    lo = plane_lo[start:start + (x1 - x0) * 3].reshape(x1 - x0, 3)
                    hi = plane_hi[start:start + (x1 - x0) * 3].reshape(x1 - x0, 3)
                    output[0][yy - y, x0 - x:x1 - x] = lo.astype(np.uint8) * 4 + 2
                    output[1][yy - y, x0 - x:x1 - x] = hi.astype(np.uint8) * 4 + 2
        return tuple(output)

    def iter_field(self, field):
        if type(field) != int or not 0 <= field < self.factory.count:
            raise ValueError('Unregistered field')
        pair = self.meta['shapes'][2 * field:2 * field + 2]
        h, w = max(s[0] for s in pair), max(s[1] for s in pair)
        for y in range(0, h, self.tile):
            for x in range(0, w, self.tile):
                yield y, x, self.read_field_roi(field, y, x, min(self.tile, h - y), min(self.tile, w - x))

    def write_roi(self, photo, rgb, y=0, x=0):
        if not self.writable:
            raise PermissionError('Read-only store')
        if type(photo) != int or not 0 <= photo < len(self.meta['shapes']):
            raise ValueError('Unknown photo')
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError('Expected uint8 RGB')
        h, w, _ = rgb.shape
        ih, iw = self.meta['shapes'][photo]
        if min(y, x) < 0 or min(h, w) <= 0 or y + h > ih or x + w > iw:
            raise ValueError('Invalid photo ROI')
        field, slot = divmod(photo, 2)
        t = self.tile
        Q = self.factory.q
        digits = (rgb // 4).astype(np.uint8)  # 6-bit quantize

        for ty in range(y // t, (y + h - 1) // t + 1):
            for tx in range(x // t, (x + w - 1) // t + 1):
                planes, _ = self._load_planes(ty, tx)
                y0, x0 = max(y, ty * t), max(x, tx * t)
                y1, x1 = min(y + h, (ty + 1) * t), min(x + w, (tx + 1) * t)
                for yy in range(y0, y1):
                    start = ((yy - ty * t) * t + x0 - tx * t) * 3
                    patch = digits[yy - y, x0 - x:x1 - x].reshape((x1 - x0) * 3)
                    planes[2 * field + slot, start:start + (x1 - x0) * 3] = patch
                self._save_planes(ty, tx, planes)

    def tile_bytes_on_disk(self):
        """Total compressed bytes for all tile files."""
        return sum(p.stat().st_size for p in (self.directory / 'tiles').iterdir() if p.suffix == '.bin')
