import hashlib
import itertools
from pathlib import Path
import tempfile
import unittest
import zlib

import numpy as np

from field_factory import FieldFactory, is_prime
from stream_memory import StreamMemory


def hashes(store):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.directory/'tiles').iterdir()}


class StreamTests(unittest.TestCase):
    def test_factory_and_small_lift(self):
        for n in (1,3,6,16,100):
            f = FieldFactory(n)
            self.assertEqual(f.primes,FieldFactory(100).primes[:n])
            self.assertTrue(all(is_prime(p) for p in f.primes))
        f2,f3 = FieldFactory(2,2),FieldFactory(3,2)
        self.assertEqual(f2.encode((1,0,0,1)),16)
        self.assertEqual(f3.lift(16,2),121)
        self.assertEqual((121+3*f3.weights[2])%f3.modulus,366)
        for bits in itertools.product(range(2),repeat=6):
            old = f2.encode(bits[:4])
            lifted = f3.lift(old,2)
            self.assertEqual(f3.project_pair(lifted,2),(0,0))
            updated = (lifted+(bits[4]+2*bits[5])*f3.weights[2])%f3.modulus
            self.assertEqual(updated,f3.encode(bits))

    def test_lazy_growth_locality_and_direct_oracle(self):
        with tempfile.TemporaryDirectory(prefix='smartcoder-stream-test-') as tmp:
            rng = np.random.default_rng(44)
            photos = [rng.integers(0,256,(8+i,9+i,3),dtype=np.uint8) for i in range(12)]
            store = StreamMemory.create(tmp,[a.shape[:2] for a in photos[:2]],tile=4)
            for k in range(6):
                if k:
                    before = hashes(store)
                    store.reset_stats()
                    store.append_pair([a.shape[:2] for a in photos[2*k:2*k+2]])
                    self.assertEqual(hashes(store),before)
                    self.assertEqual(store.stats['tile_reads'],0)
                for j in (2*k,2*k+1):
                    store.write_roi(j,photos[j])
                for j in range(2*k+2):
                    h,w,_ = photos[j].shape
                    actual = store.read_field_roi(j//2,0,0,h,w)[j%2]
                    self.assertTrue(np.array_equal(actual,(photos[j]//4)*4+2))
            # Check every scalar against an independent direct CRT expression.
            for ty,tx in store.tile_keys():
                values,count = store._load_tile(ty,tx)
                values = store._lift_values(values,count)
                for yy in range(store.tile):
                    for xx in range(store.tile):
                        y,x = ty*store.tile+yy,tx*store.tile+xx
                        for c in range(3):
                            digits = [int(a[y,x,c]//4) if y<a.shape[0] and x<a.shape[1] else 0 for a in photos]
                            self.assertEqual(values[(yy*store.tile+xx)*3+c],store.factory.encode(digits))
            before = hashes(store)
            store.reset_stats()
            patch = np.full((2,2,3),254,dtype=np.uint8)
            store.write_roi(0,patch,y=3,x=3)
            self.assertEqual(store.stats['tile_reads'],4)
            self.assertEqual(store.stats['tile_writes'],4)
            changed = {k for k,v in hashes(store).items() if v!=before[k]}
            self.assertEqual(changed,{'0_0.bin','0_1.bin','1_0.bin','1_1.bin'})
            opened = StreamMemory(tmp)
            self.assertEqual(opened.stats['tile_reads'],0)
            with self.assertRaises(PermissionError):
                opened.append_pair([(2,2),(2,2)])

    def test_codec_and_corruption(self):
        with tempfile.TemporaryDirectory(prefix='smartcoder-codec-test-') as tmp:
            photo = np.arange(8*8*3,dtype=np.uint8).reshape(8,8,3)
            stores = [StreamMemory.create(Path(tmp)/str(c),[(8,8)]*2,tile=4,compressed=bool(c)) for c in (0,1)]
            for store in stores:
                store.write_roi(0,photo)
                self.assertTrue(np.array_equal(store.read_field_roi(0,0,0,8,8)[0],(photo//4)*4+2))
            for store in stores:
                path = store.tile_path(1,1)
                original = path.read_bytes()
                path.write_bytes(original[:-2])
                opened = StreamMemory(store.directory)
                opened.read_field_roi(0,0,0,1,1)  # unrelated tile still accessible
                with self.assertRaises((ValueError,zlib.error)):
                    opened.read_field_roi(0,4,4,1,1)
                corrupted = bytearray(original)
                corrupted[16] ^= 1  # CRC field, without changing encoded image data
                path.write_bytes(corrupted)
                with self.assertRaises(ValueError):
                    opened.read_field_roi(0,4,4,1,1)


if __name__=='__main__':
    unittest.main(verbosity=2)
