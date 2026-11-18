"""Argon2id hashes."""

from argon2 import PasswordHasher

from app.security.passwords import PasswordService

PASSWORD = "Synthetic-" + "p" * 12


async def test_hash_is_argon2id_and_verifies() -> None:
    service = PasswordService()
    hashed = await service.hash(PASSWORD)
    assert hashed.startswith("$argon2id$")
    assert PASSWORD not in hashed
    assert await service.verify(hashed, PASSWORD)
    assert not await service.verify(hashed, PASSWORD + "x")
    assert not service.needs_rehash(hashed)


async def test_a_malformed_hash_never_matches() -> None:
    service = PasswordService()
    assert not await service.verify("not-a-hash", PASSWORD)
    assert service.needs_rehash("not-a-hash")


async def test_weaker_hashes_are_upgraded() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    service = PasswordService()
    assert await service.verify(weak, PASSWORD)
    assert service.needs_rehash(weak)


async def test_spending_verify_time_reuses_one_hash() -> None:
    service = PasswordService()
    await service.spend_verify_time(PASSWORD)
    first = service._timing_hash
    await service.spend_verify_time(PASSWORD)
    assert first is not None
    assert service._timing_hash == first
