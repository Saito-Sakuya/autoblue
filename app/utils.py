import hashlib
import re
from typing import Iterable


def normalize_text(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def simhash64(tokens: Iterable[str]) -> int:
    v = [0] * 64
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8", errors="ignore")).hexdigest(), 16)
        for i in range(64):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1
    out = 0
    for i, val in enumerate(v):
        if val > 0:
            out |= (1 << i)
    return out


def simhash_text(text: str) -> int:
    tokens = re.findall(r"[\w\u4e00-\u9fa5]+", normalize_text(text))
    return simhash64(tokens)


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")
