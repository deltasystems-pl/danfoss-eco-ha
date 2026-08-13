"""XXTEA codec for the Danfoss Eco eTRV wire format.

The device encrypts every characteristic in its custom settings service
(except the standard battery characteristic) with XXTEA, applied over the
payload with every 4-byte chunk byte-reversed before and after the cipher.

Pure-python implementation of the public-domain XXTEA (Corrected Block TEA)
algorithm by Needham & Wheeler; word order matches the little-endian
convention used by the reference C implementation (and the `xxtea` PyPI
package with ``padding=False``), which is what the eTRV firmware speaks.
Protocol layout knowledge derives from the MIT-licensed libetrv and
etrv2mqtt projects.
"""

from __future__ import annotations

import struct

_DELTA = 0x9E3779B9
_MASK = 0xFFFFFFFF


class EtrvCryptoError(Exception):
    """Raised when a payload cannot be encoded/decoded."""


def _to_words(data: bytes) -> list[int]:
    return list(struct.unpack(f"<{len(data) // 4}I", data))


def _from_words(words: list[int]) -> bytes:
    return struct.pack(f"<{len(words)}I", *words)


def _mx(y: int, z: int, total: int, key: list[int], p: int, e: int) -> int:
    return (
        (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4)))
        ^ ((total ^ y) + (key[(p & 3) ^ e] ^ z))
    ) & _MASK


def _btea_encrypt(v: list[int], key: list[int]) -> list[int]:
    n = len(v)
    if n < 2:
        return v
    rounds = 6 + 52 // n
    total = 0
    z = v[n - 1]
    for _ in range(rounds):
        total = (total + _DELTA) & _MASK
        e = (total >> 2) & 3
        for p in range(n - 1):
            y = v[p + 1]
            v[p] = (v[p] + _mx(y, z, total, key, p, e)) & _MASK
            z = v[p]
        y = v[0]
        v[n - 1] = (v[n - 1] + _mx(y, z, total, key, n - 1, e)) & _MASK
        z = v[n - 1]
    return v


def _btea_decrypt(v: list[int], key: list[int]) -> list[int]:
    n = len(v)
    if n < 2:
        return v
    rounds = 6 + 52 // n
    total = (rounds * _DELTA) & _MASK
    y = v[0]
    while total:
        e = (total >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            v[p] = (v[p] - _mx(y, z, total, key, p, e)) & _MASK
            y = v[p]
        z = v[n - 1]
        v[0] = (v[0] - _mx(y, z, total, key, 0, e)) & _MASK
        y = v[0]
        total = (total - _DELTA) & _MASK
    return v


def _reverse_chunks(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), 4):
        out += data[i : i + 4][::-1]
    return bytes(out)


def _key_words(key: bytes) -> list[int]:
    if len(key) != 16:
        raise EtrvCryptoError(f"Secret key must be 16 bytes, got {len(key)}")
    return list(struct.unpack("<4I", key))


def etrv_decode(data: bytes, key: bytes) -> bytes:
    """Decrypt a payload read from the device."""
    if len(data) == 1:
        raise EtrvCryptoError(
            f"Device returned error code {data[0]:#04x} - wrong PIN or not paired"
        )
    if len(data) < 8 or len(data) % 4:
        raise EtrvCryptoError(f"Un-decodable payload length {len(data)}")
    words = _to_words(_reverse_chunks(data))
    return _reverse_chunks(_from_words(_btea_decrypt(words, _key_words(key))))


def etrv_encode(data: bytes, key: bytes) -> bytes:
    """Encrypt a payload for writing to the device."""
    if len(data) % 4:
        raise EtrvCryptoError(f"Un-encodable payload length {len(data)}")
    words = _to_words(_reverse_chunks(data))
    return _reverse_chunks(_from_words(_btea_encrypt(words, _key_words(key))))
