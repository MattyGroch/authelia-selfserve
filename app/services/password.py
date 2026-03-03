import argon2
from argon2 import PasswordHasher

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=argon2.Type.ID,
)


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)
