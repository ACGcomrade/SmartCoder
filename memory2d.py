"""Finite-field multiplexed 2-D memory. No source-photo access in decoding."""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


def primes_from(start, count):
    result = []
    n = max(2, start)
    while len(result) < count:
        if all(n % d for d in range(2, math.isqrt(n) + 1)):
            result.append(n)
        n += 1
    return result


def parameters(q=64):
    if q not in (2, 64):
        raise ValueError('This verified implementation supports Q=2 or Q=64')
    primes = primes_from(q * q, 3)
    modulus = math.prod(primes)
    if modulus * max(primes) >= 2**63:
        raise OverflowError('Signed int64 arithmetic bound exceeded')
    weights = [(modulus // p * pow(modulus // p, -1, p)) % modulus
               for p in primes]
    return primes, modulus, weights


def quantize(rgb):
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Expected uint8 H x W x RGB')
    return rgb // np.uint8(4)


def dequantize(digits):
    return (digits.astype(np.int64) * 4 + 2).astype(np.uint8)


class Memory2D:
    def __init__(self, shapes, base=None):
        if len(shapes) != 6 or any(len(s) != 2 or min(s) <= 0 for s in shapes):
            raise ValueError('Exactly six positive (height, width) shapes required')
        self.shapes = [tuple(map(int, s)) for s in shapes]
        self.height = max(s[0] for s in self.shapes)
        self.width = max(s[1] for s in self.shapes)
        self.primes, self.modulus, self.weights = parameters()
        expected = (self.height, self.width * 3)
        self.base = np.zeros(expected, dtype=np.uint64) if base is None else base
        if self.base.shape != expected or self.base.dtype != np.uint64:
            raise ValueError('base must be a two-dimensional uint64 matrix')
        # Validate once on construction/loading, not on every local operation.
        if np.any(self.base >= self.modulus):
            raise ValueError('Noncanonical base value')

    @staticmethod
    def _index(index):
        if not isinstance(index, int) or not 0 <= index < 6:
            raise ValueError('Photo index must be in 0..5')

    def read_field(self, field):
        """One fixed decoder returns BOTH stored images; no photo parameter."""
        if not isinstance(field, int) or not 0 <= field < 3:
            raise ValueError('Field index must be in 0..2')
        residual = self.base.astype(np.int64) % self.primes[field]
        if np.any(residual >= 4096):
            raise ValueError('Residue outside the two-digit code alphabet')
        images = []
        for slot in range(2):
            h, w = self.shapes[2 * field + slot]
            digits = (residual[:h, :w*3] // (64**slot)) % 64
            images.append(digits.reshape(h, w, 3).astype(np.uint8))
        return tuple(images)

    def read_all(self):
        return [img for field in range(3) for img in self.read_field(field)]

    def write(self, index, rgb, y=0, x=0, whole=False):
        """Known ROI: only read/write its cells. Counts are logical, not disk I/O."""
        self._index(index)
        digits = quantize(rgb)
        h, w, _ = digits.shape
        ih, iw = self.shapes[index]
        if min(h, w) <= 0 or min(y, x) < 0 or y+h > ih or x+w > iw:
            raise ValueError('ROI outside the fixed photo shape')
        if whole and (y != 0 or x != 0 or (h, w) != (ih, iw)):
            raise ValueError('Whole-image replacement must match original shape')
        field, slot = divmod(index, 2)
        region = self.base[y:y+h, 3*x:3*(x+w)]
        old = region.astype(np.int64)
        residual = old % self.primes[field]
        if np.any(residual >= 4096):
            raise ValueError('Invalid residue in update region')
        old_digit = (residual // (64**slot)) % 64
        delta = ((digits.reshape(h, 3*w).astype(np.int64) - old_digit)
                 * (64**slot)) % self.primes[field]
        new = (old + delta * self.weights[field]) % self.modulus
        changed = int(np.count_nonzero(new != old))
        region[:] = new.astype(np.uint64)
        return {'mode': 'whole_image' if whole else 'known_roi',
                'base_cells_read': h*w*3, 'base_cells_written': h*w*3,
                'base_cells_changed': changed, 'roi_yxhw': [y, x, h, w]}

    @classmethod
    def bulk(cls, photos):
        memory = cls([p.shape[:2] for p in photos])
        acc = np.zeros_like(memory.base, dtype=np.int64)
        for field in range(3):
            residual = np.zeros_like(acc)
            for slot in range(2):
                digits = quantize(photos[2*field+slot])
                h, w, _ = digits.shape
                residual[:h, :3*w] += digits.reshape(h, 3*w).astype(np.int64) * (64**slot)
            # Modulo after each term: bounded integer intermediates.
            acc = (acc + residual * memory.weights[field]) % memory.modulus
        memory.base[:] = acc.astype(np.uint64)
        return memory

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / 'base.npy', self.base, allow_pickle=False)
        metadata = {'schema': 'smartcoder-2d-v1', 'q': 64,
                    'shapes_hw': self.shapes, 'field_count': 3,
                    'primes': self.primes, 'layout': 'B[y,3*x+c]',
                    'assignment': [[0, 1], [2, 3], [4, 5]]}
        (directory / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')

    @classmethod
    def load(cls, directory):
        directory = Path(directory)
        metadata = json.loads((directory / 'manifest.json').read_text())
        if (metadata.get('schema') != 'smartcoder-2d-v1'
                or metadata.get('q') != 64
                or metadata.get('primes') != parameters()[0]
                or metadata.get('field_count') != 3
                or metadata.get('assignment') != [[0, 1], [2, 3], [4, 5]]
                or metadata.get('layout') != 'B[y,3*x+c]'):
            raise ValueError('Unsupported decoder configuration')
        return cls(metadata['shapes_hw'], np.load(directory / 'base.npy',
                                                allow_pickle=False, mmap_mode='r'))


def recover(bundle, output):
    memory = Memory2D.load(bundle)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for field in range(3):
        for slot, digits in enumerate(memory.read_field(field)):
            Image.fromarray(dequantize(digits)).save(output / f'photo_{2*field+slot}.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    recover(args.bundle, args.output)
