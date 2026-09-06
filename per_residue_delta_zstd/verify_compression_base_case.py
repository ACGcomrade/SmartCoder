"""Minimal base case for per-residue-plane delta+lzma compression.

Hand-calculable example. Run with: python3 verify_compression_base_case.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from field_factory import FieldFactory, family


def run():
    # ---- parameters (simple enough to hand-calculate) ----
    Q = 4       # 2-bit quantization for legibility (not 64)
    K = 2       # 2 fields → 4 photos
    CELLS = 3   # single row of 3 cells (like 1×1 pixel with 3 channels)

    # Manually chosen pixel values in [0, Q)
    # Photo 0 (field 0, slot 0):
    d0 = [1, 1, 2]
    # Photo 1 (field 0, slot 1):
    d1 = [2, 3, 3]
    # Photo 2 (field 1, slot 0):
    d2 = [3, 3, 2]
    # Photo 3 (field 1, slot 1):
    d3 = [0, 1, 1]

    # ---- compute smallest primes ≥ Q² = 16 ----
    factory = FieldFactory(K, q=Q)
    p0, p1 = factory.primes
    w0, w1 = factory.weights
    M = factory.modulus
    print(f"Q={Q}, K={K}, p0={p0}, p1={p1}, M={M}")
    print(f"cell_bytes (current format): {factory.cell_bytes} (valid info: {2*K*int(math.log2(Q))} bits)")

    # ---- encode via CRT (big integer format, current scheme) ----
    big_ints = []
    for c in range(CELLS):
        r0 = d0[c] + Q * d1[c]      # packed residue for field 0
        r1 = d2[c] + Q * d3[c]      # packed residue for field 1
        assert 0 <= r0 < p0 and 0 <= r1 < p1, "residue must be < prime"
        b = (r0 * w0 + r1 * w1) % M
        big_ints.append(b)
        # verify projection
        assert b % p0 == r0, "CRT inverse check p0"
        assert b % p1 == r1, "CRT inverse check p1"
    print(f"\nBig integers: {big_ints}")

    # ---- current format: fixed-width bytes, zlib level=1 ----
    import zlib
    w = factory.cell_bytes
    raw_bigint = b''.join(b.to_bytes(w, 'little') for b in big_ints)
    compressed_bigint = zlib.compress(raw_bigint, level=1)
    print(f"\nCurrent format (big-int zlib):")
    print(f"  raw bytes:        {len(raw_bigint)}")
    print(f"  zlib-1 bytes:     {len(compressed_bigint)}")

    # ---- new format: 2K uint8 planes, row-delta, lzma ----
    import lzma, struct
    planes = [
        bytes(d0),   # field 0, slot 0
        bytes(d1),   # field 0, slot 1
        bytes(d2),   # field 1, slot 0
        bytes(d3),   # field 1, slot 1
    ]
    # Row delta (single row of 3 cells; delta relative to 0 is the value itself)
    # For multi-row tiles the delta would be: plane[j] - plane[j-1]
    # Verify: prefix sum modulo Q restores original
    for name, plane in zip(["d0","d1","d2","d3"], planes):
        deltas = [plane[0]] + [(plane[j] - plane[j-1]) % Q for j in range(1, len(plane))]
        recovered = []
        acc = 0
        for d in deltas:
            acc = (acc + d) % Q
            recovered.append(acc)
        assert list(recovered) == list(plane), f"Delta roundtrip failed for {name}"
    raw_planes = b''.join(planes)
    # Apply proper uint8 delta (mod 256 for general case, values are [0,Q) so mod Q also works)
    all_deltas = bytearray()
    for plane in planes:
        all_deltas.append(plane[0])
        for j in range(1, len(plane)):
            all_deltas.append((plane[j] - plane[j-1]) % 256)
    compressed_planes = lzma.compress(bytes(all_deltas), format=lzma.FORMAT_XZ, preset=6)
    print(f"\nNew format (per-plane delta+lzma):")
    print(f"  raw bytes:        {len(raw_planes)} (2K={2*K} planes × {CELLS} cells × 1 byte)")
    print(f"  delta bytes:      {len(bytes(all_deltas))} (same size, but values near 0)")
    print(f"  lzma-6 bytes:     {len(compressed_planes)}")

    # ---- verify reconstruction from planes ----
    # Decompress
    recovered_deltas = bytearray(lzma.decompress(compressed_planes))
    recovered_planes = []
    ptr = 0
    for _ in range(2 * K):
        plane = bytearray(CELLS)
        acc = 0
        for j in range(CELLS):
            acc = (acc + recovered_deltas[ptr]) % 256
            plane[j] = acc
            ptr += 1
        recovered_planes.append(bytes(plane))
    assert len(recovered_planes) == 4
    rd0, rd1, rd2, rd3 = recovered_planes
    print(f"\nRecovered planes: d0={list(rd0)}, d1={list(rd1)}, d2={list(rd2)}, d3={list(rd3)}")
    assert list(rd0) == d0, "d0 mismatch"
    assert list(rd1) == d1, "d1 mismatch"
    assert list(rd2) == d2, "d2 mismatch"
    assert list(rd3) == d3, "d3 mismatch"
    print("All planes recovered exactly. ✓")

    # ---- verify CRT reconstruction from planes ----
    for c in range(CELLS):
        r0_rec = rd0[c] + Q * rd1[c]
        r1_rec = rd2[c] + Q * rd3[c]
        b_rec = (r0_rec * w0 + r1_rec * w1) % M
        assert b_rec == big_ints[c], f"CRT mismatch at cell {c}"
    print("CRT reconstruction from planes matches original. ✓")

    # ---- hand-calculable verification ----
    print("\n--- Hand-check cell 0 ---")
    r0 = d0[0] + Q * d1[0]
    r1 = d2[0] + Q * d3[0]
    print(f"  r0 = {d0[0]} + {Q}*{d1[0]} = {r0}  (must be in [0, {p0}))")
    print(f"  r1 = {d2[0]} + {Q}*{d3[0]} = {r1}  (must be in [0, {p1}))")
    b = (r0 * w0 + r1 * w1) % M
    print(f"  b  = {r0}*{w0} + {r1}*{w1} ≡ {b} (mod {M})")
    print(f"  b mod p0 = {b % p0} (expected {r0})")
    print(f"  b mod p1 = {b % p1} (expected {r1})")
    print(f"  recover d0={b%p0%Q}, d1={b%p0//Q}, d2={b%p1%Q}, d3={b%p1//Q}")

    # ---- compression ratio summary ----
    ratio = len(raw_bigint) / len(compressed_planes) if compressed_planes else float('inf')
    print(f"\n=== Base case compression ratio (big-int-raw / planes-lzma): {ratio:.2f}×")
    print("    (Note: for real T=64 tiles with natural images the ratio is higher)")


if __name__ == '__main__':
    run()
