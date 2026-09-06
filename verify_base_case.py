"""Exact finite checks for README P1-P5; no learning or intelligence claim.

Run with Python 3.8+ without -O. Only the standard library is required.
Snapshots belong to the verification harness, never to the read/write rules.
"""

from dataclasses import dataclass
from itertools import product
import json


M = 6


def prime(p):
    return p >= 2 and all(p % k for k in range(2, int(p**0.5) + 1))


class ProbedList:
    def __init__(self, values):
        self._values = list(values)
        self.reads = []
        self.writes = []

    def get(self, j):
        self.reads.append(j)
        return self._values[j]

    def set(self, j, value):
        if not isinstance(value, int) or not 0 <= value < M:
            raise ValueError("cell must be a canonical representative in [0, 6)")
        self.writes.append(j)
        self._values[j] = value

    def snapshot(self):
        """Verification-only full observation; not a memory access primitive."""
        return tuple(self._values)


@dataclass(frozen=True)
class Affine:
    p: int
    alpha: int
    beta: int

    def __post_init__(self):
        if not prime(self.p) or self.p < M:
            raise ValueError("prime field must contain at least M representatives")
        if not 0 < self.alpha < self.p or not 0 <= self.beta < self.p:
            raise ValueError("nonzero canonical multiplier and canonical offset required")

    def forward(self, b):
        if not isinstance(b, int) or not 0 <= b < M:
            raise ValueError("invalid base cell")
        return (self.alpha * b + self.beta) % self.p

    def inverse(self, y):
        if not isinstance(y, int) or not 0 <= y < self.p:
            raise ValueError("invalid field representative")
        b = (pow(self.alpha, -1, self.p) * (y - self.beta)) % self.p
        if b >= M:
            raise ValueError("field value is outside this decoder's image")
        return b

    def read(self, base, j):
        return self.forward(base.get(j))

    def write(self, base, j, y):
        base.set(j, self.inverse(y))


PRIMES = (2, 3)
IDEMPOTENTS = {p: ((M // p) * pow(M // p, -1, p)) % M for p in PRIMES}


def project(base, j, p):
    if p not in PRIMES:
        raise ValueError("unconfigured CRT prime")
    return base.get(j) % p


def write_residue(base, j, p, v):
    if p not in PRIMES or not isinstance(v, int) or not 0 <= v < p:
        raise ValueError("invalid CRT residue")
    b = base.get(j)
    delta = (v - b % p) % p
    base.set(j, (b + delta * IDEMPOTENTS[p]) % M)


def pack(residues):
    if len(residues) != len(PRIMES):
        raise ValueError("one residue per configured prime required")
    if any(not 0 <= v < p for p, v in zip(PRIMES, residues)):
        raise ValueError("invalid CRT residue")
    return sum(v * IDEMPOTENTS[p] for p, v in zip(PRIMES, residues)) % M


def verify():
    if not __debug__:
        raise RuntimeError("Run without -O: mathematical checks use assertions")
    stats = {}
    for p in (2, 3, 7, 11):
        assert prime(p)
        for a in range(p):
            assert (a + 0) % p == a and (a * 1) % p == a
            assert (a + (-a) % p) % p == 0
            if a:
                assert a * pow(a, -1, p) % p == 1
            for b in range(p):
                assert 0 <= (a + b) % p < p and 0 <= a * b % p < p
                assert (a + b) % p == (b + a) % p
                assert a * b % p == b * a % p
                for c in range(p):
                    assert ((a + b) % p + c) % p == (a + (b + c) % p) % p
                    assert ((a * b) % p * c) % p == (a * (b * c) % p) % p
                    assert a * ((b + c) % p) % p == (a * b + a * c) % p
    assert 2 * 3 % 6 == 0  # Nonzero zero divisors: Z/6Z is not a field.
    stats["prime_fields_checked"] = [2, 3, 7, 11]

    decoders = (Affine(7, 1, 1), Affine(11, 2, 1))
    bases = tuple(product(range(M), repeat=2))
    outputs = set()
    a_count = 0
    changed_counts = {0: 0, 1: 0}
    bit_flips = set()
    for b in bases:
        for d in decoders:
            memory = ProbedList(b)
            values = tuple(d.read(memory, j) for j in range(2))
            assert memory.reads == [0, 1] and not memory.writes
            assert tuple(d.inverse(y) for y in values) == b
            tagged = (d, values)
            assert tagged not in outputs
            outputs.add(tagged)
            for j in range(2):
                for target in range(M):
                    memory = ProbedList(b)
                    y = d.forward(target)
                    d.write(memory, j, y)
                    assert memory.writes == [j] and memory.reads == []
                    assert d.read(memory, j) == y and memory.reads == [j]
                    after = memory.snapshot()
                    assert after[j] == target and after[1 - j] == b[1 - j]
                    changed = sum(x != z for x, z in zip(b, after))
                    assert changed == int(target != b[j])
                    changed_counts[changed] += 1
                    bit_flips.add(bin(b[j] ^ after[j]).count("1"))
                    a_count += 1
    stats["strict_typed_pairs"] = len(outputs)
    stats["affine_local_write_cases"] = a_count
    stats["affine_changed_cell_histogram"] = changed_counts
    stats["affine_bit_flips_in_3bit_cell"] = sorted(bit_flips)
    rejected = 0
    for d in decoders:
        legal = {d.forward(b) for b in range(M)}
        for y in range(d.p):
            if y in legal:
                assert d.forward(d.inverse(y)) == y
            else:
                try:
                    d.inverse(y)
                except ValueError:
                    rejected += 1
                else:
                    raise AssertionError("accepted a value outside decoder image")
    stats["out_of_image_values_rejected"] = rejected

    # Stronger alternative: disjoint numeric images, no decoder tag in output.
    untagged = set()
    alternatives = (Affine(7, 1, 0), Affine(13, 1, 6))
    for b in bases:
        for d in alternatives:
            values = tuple(d.forward(x) for x in b)
            assert values not in untagged
            untagged.add(values)
            recovered_decoder = alternatives[int(values[0] >= M)]
            assert recovered_decoder == d
            assert tuple(recovered_decoder.inverse(y) for y in values) == b
    assert len(untagged) == 72
    stats["strict_untagged_disjoint_image_pairs"] = len(untagged)

    for b in range(M):
        assert pack(tuple(b % p for p in PRIMES)) == b
    for residues in product(range(2), range(3)):
        assert tuple(pack(residues) % p for p in PRIMES) == residues
    assert IDEMPOTENTS == {2: 3, 3: 4}
    c_count = 0
    for b in bases:
        for j in range(2):
            for p in PRIMES:
                for v in range(p):
                    memory = ProbedList(b)
                    write_residue(memory, j, p, v)
                    assert memory.reads == [j] and memory.writes == [j]
                    after = memory.snapshot()
                    assert after[j] % p == v
                    assert after[1 - j] == b[1 - j]
                    for q in PRIMES:
                        if q != p:
                            assert after[j] % q == b[j] % q
                    c_count += 1
    stats["crt_cell_roundtrips"] = M
    stats["crt_local_write_cases"] = c_count

    retained = 0
    for value, other in product(range(M), repeat=2):
        memory = ProbedList((0, 0))
        decoders[0].write(memory, 0, decoders[0].forward(value))
        decoders[1].write(memory, 1, decoders[1].forward(other))
        serialized = json.dumps(memory.snapshot())
        del memory
        restored = ProbedList(json.loads(serialized))
        assert decoders[0].inverse(decoders[0].read(restored, 0)) == value
        assert restored.reads == [0]
        retained += 1
    stats["retention_histories_with_serialization"] = retained
    old, new = Affine(11, 2, 1), Affine(11, 2, 2)
    for b in bases:
        assert tuple(old.forward(x) for x in b) != tuple(new.forward(x) for x in b)
        assert tuple(new.inverse(new.forward(x)) for x in b) == b
    stats["dynamic_decoder_cases"] = len(bases)

    # Negative controls: these must collide; no weakened injectivity claim.
    assert 1 % 2 == 3 % 2
    assert decoders[0].read(ProbedList((5, 0)), 0) == decoders[0].read(ProbedList((5, 1)), 0)
    assert decoders[0].forward(0) == decoders[1].forward(0)
    assert Affine(11, 2, 1).forward(1) == Affine(11, 2, 3).forward(0)
    stats["negative_controls_confirmed"] = [
        "single CRT projection is not injective",
        "partial query cannot identify the full free list",
        "untagged D7/D11 values can collide (unlike the H7/H13 alternative)",
        "field tag alone does not identify changed decoder parameters",
    ]

    # A known erased first symbol in a three-symbol parity block.
    code = ProbedList((None, 2, 1, 1, 4, 5))
    a = (code.get(2) - code.get(1)) % M
    code.set(0, a)
    assert code.snapshot() == (5, 2, 1, 1, 4, 5)
    assert code.reads == [2, 1] and code.writes == [0]
    stats["erasure_repair_trace"] = {"reads": code.reads, "writes": code.writes, "result": a}
    code = ProbedList((5, 2, 1, 1, 4, 5))
    neighbor = code.get(1)
    code.set(0, 3)
    code.set(2, (3 + neighbor) % M)
    assert code.snapshot() == (3, 2, 5, 1, 4, 5)
    stats["parity_update_trace"] = {"reads": code.reads, "writes": code.writes}
    assert len([(a, b) for a, b in product(range(M), repeat=2) if (a + b) % M == 1]) == M
    stats["two_erasure_ambiguity_count"] = M
    stats["examples"] = {
        "base": [5, 2],
        "D7": [decoders[0].forward(x) for x in (5, 2)],
        "D11": [decoders[1].forward(x) for x in (5, 2)],
        "affine_updated_base": [3, 2],
        "crt_updated_base": [2, 2],
    }
    assert len(outputs) == 72 and a_count == 864 and c_count == 360
    assert rejected == 6 and retained == 36
    return stats


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
