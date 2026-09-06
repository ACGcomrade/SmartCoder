"""One deterministic prime-field family, parameterized by capacity and count."""
from functools import lru_cache
import math


def is_prime(n):
    return isinstance(n, int) and n >= 2 and all(n % d for d in range(2, math.isqrt(n)+1))


@lru_cache(maxsize=32)
def family(q, count):
    if q < 2 or count < 1:
        raise ValueError('Positive field count and radix >=2 required')
    primes = []
    n = q*q
    while len(primes) < count:
        if is_prime(n):
            primes.append(n)
        n += 1
    modulus = math.prod(primes)
    weights = tuple((modulus//p * pow(modulus//p, -1, p)) % modulus for p in primes)
    return tuple(primes), modulus, weights


class FieldFactory:
    def __init__(self, count, q=64):
        self.count, self.q = count, q
        self.primes, self.modulus, self.weights = family(q, count)
        self.cell_bytes = ((self.modulus-1).bit_length()+7)//8

    def project_pair(self, value, field):
        if not 0 <= field < self.count:
            raise ValueError('Unregistered field')
        residue = value % self.primes[field]
        if residue >= self.q**2:
            raise ValueError('Unused digit-pair residue')
        return residue % self.q, residue // self.q

    def encode(self, digits):
        if len(digits) != 2*self.count or any(not 0 <= x < self.q for x in digits):
            raise ValueError('Invalid digit tuple')
        return sum((digits[2*i]+self.q*digits[2*i+1])*e
                   for i,e in enumerate(self.weights)) % self.modulus

    def lift(self, value, old_count):
        """Preserve old components and insert zeros, NOT ordinary same-integer RNS extension."""
        if not 1 <= old_count <= self.count:
            raise ValueError('Invalid old schema')
        old_modulus = family(self.q, old_count)[1]
        if not 0 <= value < old_modulus:
            raise ValueError('Noncanonical old value')
        for p in self.primes[old_count:]:
            value += old_modulus * ((-value * pow(old_modulus, -1, p)) % p)
            old_modulus *= p
        return value
