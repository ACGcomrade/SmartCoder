import itertools
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from memory2d import Memory2D, dequantize, parameters, quantize


class BaseCase(unittest.TestCase):
    def test_bundle_and_invalid_alphabet(self):
        photos = [np.full((3, 4, 3), i*37, dtype=np.uint8) for i in range(6)]
        memory = Memory2D.bulk(photos)
        with tempfile.TemporaryDirectory(prefix='smartcoder-test-') as directory:
            memory.save(directory)
            loaded = Memory2D.load(directory)
            self.assertTrue(np.array_equal(loaded.base, memory.base))
            self.assertTrue(all(np.array_equal(a, b) for a, b in
                                zip(loaded.read_all(), memory.read_all())))
            path = Path(directory) / 'manifest.json'
            meta = json.loads(path.read_text())
            meta['q'] = 32
            path.write_text(json.dumps(meta))
            with self.assertRaises(ValueError):
                Memory2D.load(directory)
        # A legal ring element with an unused field residue is not an image codeword.
        bad = memory.base.copy()
        bad[0, 0] = (4096 * memory.weights[0]) % memory.modulus
        invalid = Memory2D(memory.shapes, bad)
        with self.assertRaises(ValueError):
            invalid.read_field(0)
        with self.assertRaises(ValueError):
            invalid.write(0, photos[0], whole=True)

    def test_hand_case_and_exhaustive_updates(self):
        primes, m, weights = parameters(2)
        self.assertEqual((primes, m, weights), ([5, 7, 11], 385, [231, 330, 210]))
        self.assertEqual(sum(r*e for r, e in zip((1, 2, 3), weights)) % m, 366)
        self.assertEqual((366+2*231) % m, 58)
        count = 0
        for bits in itertools.product(range(2), repeat=6):
            residues = [bits[2*i] + 2*bits[2*i+1] for i in range(3)]
            base = sum(r*e for r, e in zip(residues, weights)) % m
            self.assertEqual([base % p for p in primes], residues)
            for index in range(6):
                field, slot = divmod(index, 2)
                delta = ((1-2*bits[index]) * 2**slot) % primes[field]
                changed = (base + delta*weights[field]) % m
                decoded = tuple(v for p in primes for v in (changed % p % 2, changed % p // 2))
                expected = list(bits)
                expected[index] ^= 1
                self.assertEqual(decoded, tuple(expected))
                grid = np.array([[base, 0], [0, 0]])
                grid[0, 0] = changed
                self.assertTrue(np.array_equal(grid[1:], [[0, 0]]))
                self.assertEqual(grid[0, 1], 0)
                count += 1
        self.assertEqual(count, 384)

    def test_real_parameters_integer_oracle(self):
        primes, m, weights = parameters()
        self.assertLess(m * max(primes), 2**63)
        rng = np.random.default_rng(20260906)
        residues = rng.integers(0, 4096, (1000, 3), dtype=np.int64)
        acc = np.zeros(1000, dtype=np.int64)
        for i in range(3):
            acc = (acc + residues[:, i]*weights[i]) % m
        exact = [sum(int(r)*e for r, e in zip(row, weights)) % m for row in residues]
        self.assertTrue(np.array_equal(acc, exact))
        for i, p in enumerate(primes):
            self.assertTrue(np.array_equal(acc % p, residues[:, i]))

    def test_quantizer_all_values(self):
        values = np.repeat(np.arange(256, dtype=np.uint8), 3).reshape(16, 16, 3)
        err = dequantize(quantize(values)).astype(int) - values.astype(int)
        self.assertEqual(int(np.abs(err).max()), 2)
        self.assertEqual(set(err.flatten()), {-1, 0, 1, 2})

    def test_core_locality_order_and_edges(self):
        rng = np.random.default_rng(1)
        photos = [rng.integers(0, 256, (i+2, 9-i, 3), dtype=np.uint8) for i in range(6)]
        bulk = Memory2D.bulk(photos)
        seq = Memory2D([p.shape[:2] for p in photos])
        for i in reversed(range(6)):
            seq.write(i, photos[i], whole=True)
        self.assertTrue(np.array_equal(seq.base, bulk.base))
        original = bulk.read_all()
        for index in range(6):
            mem = Memory2D(bulk.shapes, bulk.base.copy())
            before = mem.base.copy()
            patch = np.full((1, 1, 3), 255, dtype=np.uint8)
            stats = mem.write(index, patch, y=1, x=1)
            mask = np.zeros_like(before, dtype=bool)
            mask[1:2, 3:6] = True
            self.assertTrue(np.array_equal(before[~mask], mem.base[~mask]))
            self.assertEqual(stats['base_cells_read'], 3)
            expected = [a.copy() for a in original]
            expected[index][1, 1] = 63
            for a, b in zip(expected, mem.read_all()):
                self.assertTrue(np.array_equal(a, b))
        with self.assertRaises(ValueError):
            bulk.write(0, photos[0], x=1)
        with self.assertRaises(ValueError):
            bulk.write(6, photos[0])
        with self.assertRaises(ValueError):
            bulk.read_field(3)
        invalid = bulk.base.copy()
        invalid[0, 0] = bulk.modulus
        with self.assertRaises(ValueError):
            Memory2D(bulk.shapes, invalid)
        with self.assertRaises(ValueError):
            quantize(photos[0].astype(float))


if __name__ == '__main__':
    unittest.main(verbosity=2)
