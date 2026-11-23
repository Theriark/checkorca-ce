"""The SSRF guard (app/security/ssrf.py): http and https only; private,
loopback and metadata addresses refused after DNS resolution, unless
ALLOW_PRIVATE_TARGETS or an exact OUTBOUND_ALLOWED_HOSTS entry allows them.
Link-local and metadata addresses are never allowed (phase C9-I decided the
C9-B security review note). DNS answers come from a fake resolver; no request
leaves the test."""

import ipaddress
from collections.abc import Mapping, Sequence

import pytest

from app.security.ssrf import (
    Target,
    TargetRefused,
    check_target,
    refusal,
    system_resolver,
)
from app.settings import load_settings

# Synthetic names (example.com, example.net) and documentation addresses.
DNS: Mapping[str, Sequence[str]] = {
    "hooks.example.com": ("93.184.215.14",),
    "internal.example.com": ("10.0.0.7",),
    "mixed.example.com": ("93.184.215.14", "192.168.1.20"),
    "v6.example.com": ("2606:4700::6810:84e5",),
    "mapped.example.com": ("::ffff:127.0.0.1",),
    "mock-platform": ("172.18.0.5",),
    "metadata.example.com": ("169.254.169.254",),
}


class FakeResolver:
    """Answers from DNS; an unknown name does not resolve."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, int]] = []

    async def __call__(self, host: str, port: int) -> Sequence[str]:
        self.asked.append((host, port))
        if host not in DNS:
            raise OSError("name does not resolve")
        return DNS[host]


async def check(
    url: str, *, allow_private: bool = False, allowed: frozenset[str] = frozenset()
) -> Target:
    return await check_target(
        url,
        allow_private=allow_private,
        allowed_hosts=allowed,
        resolver=FakeResolver(),
    )


@pytest.mark.parametrize(
    ("url", "words"),
    [
        ("http://10.0.0.5/", "10.0.0.5 is a private address"),
        ("http://127.0.0.1:8080/hook", "127.0.0.1 is a loopback address"),
        (
            "http://169.254.169.254/latest/meta-data/",
            "169.254.169.254 is a cloud metadata address",
        ),
        ("http://[::1]/", "::1 is a loopback address"),
        ("https://[fd00::]/", "fd00:: is a private address"),
        ("http://[fe80::1]/", "fe80::1 is a link-local address"),
        ("http://100.64.0.1/", "100.64.0.1 is an address that is not public"),
        ("http://0.0.0.0/", "0.0.0.0 is the unspecified address"),
        ("http://224.0.0.1/", "224.0.0.1 is a multicast address"),
        (
            "https://internal.example.com/hook",
            "internal.example.com resolves to 10.0.0.7, a private address",
        ),
        (
            "https://mixed.example.com/hook",
            "mixed.example.com resolves to 192.168.1.20, a private address",
        ),
        (
            "https://mapped.example.com/",
            "a loopback address inside an IPv6 address",
        ),
        # IPv4-compatible and SIIT forms carry an IPv4 address too.
        ("http://[::7f00:1]/", "::7f00:1 is a loopback address inside an IPv6"),
        ("http://[::a9fe:a9fe]/", "a cloud metadata address inside an IPv6"),
        ("http://[::ffff:0:7f00:1]/", "a loopback address inside an IPv6"),
        ("http://[fec0::1]/", "fec0::1 is a site-local address"),
        ("http://[4000::1]/", "4000::1 is a reserved address"),
        ("ftp://hooks.example.com/file", "Only http:// and https:// URLs"),
        ("file:///etc/passwd", "Only http:// and https:// URLs"),
        ("gopher://hooks.example.com/", "Only http:// and https:// URLs"),
        ("javascript:alert(1)", "Only http:// and https:// URLs"),
        ("https://user:pass@hooks.example.com/", "user name or password"),
        ("https:///no-host", "has no host"),
        ("https://hooks.example.com:99999/", "cannot be read"),
        ("https://nowhere.example.net/", "nowhere.example.net cannot be resolved"),
    ],
)
async def test_the_guard_refuses_with_a_readable_reason(url: str, words: str) -> None:
    with pytest.raises(TargetRefused) as refused:
        await check(url)
    text = str(refused.value)
    assert words in text
    # One readable sentence that never repeats the path or the query.
    assert "meta-data" not in text and "/hook" not in text
    if "address" in words and "cannot" not in words:
        assert "OUTBOUND_ALLOWED_HOSTS" in text and "ALLOW_PRIVATE_TARGETS" in text


async def test_public_targets_pass_with_the_addresses_to_connect_to() -> None:
    target = await check("https://hooks.example.com/services/T0/B0/x")
    assert target == Target(
        scheme="https",
        host="hooks.example.com",
        port=443,
        addresses=("93.184.215.14",),
        allowed_by="public",
    )
    plain = await check("http://HOOKS.example.com.:8080/")
    assert (plain.host, plain.port, plain.scheme) == ("hooks.example.com", 8080, "http")
    v6 = await check("https://v6.example.com/")
    assert v6.addresses == ("2606:4700::6810:84e5",)


async def test_the_allowed_hosts_match_exactly() -> None:
    allowed = frozenset({"mock-platform", "internal.example.com"})
    target = await check("http://mock-platform:8025/hook", allowed=allowed)
    assert target.allowed_by == "allowed_host"
    assert target.addresses == ("172.18.0.5",)
    # No subdomain, no suffix, no prefix: exact names only.
    for url in (
        "http://evil.mock-platform/",
        "http://mock-platform.example.com/",
        "http://10.0.0.5/",
    ):
        with pytest.raises(TargetRefused):
            await check(url, allowed=allowed)


async def test_allow_private_targets_allows_every_address() -> None:
    target = await check("http://10.0.0.5/", allow_private=True)
    assert target.allowed_by == "allow_private"
    resolved = await check("https://internal.example.com/", allow_private=True)
    assert resolved.addresses == ("10.0.0.7",)
    public = await check("https://hooks.example.com/", allow_private=True)
    assert public.allowed_by == "public"
    # The scheme rule stays.
    with pytest.raises(TargetRefused):
        await check("ftp://10.0.0.5/", allow_private=True)


async def test_link_local_and_metadata_are_never_allowed() -> None:
    """Neither setting opens a cloud metadata service, or anything else on
    link-local, to a webhook URL (phase C9-I)."""
    allowed = frozenset({"169.254.169.254", "metadata.example.com", "169.254.0.1"})
    for url in (
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/",
        "http://[::ffff:169.254.169.254]/",
        "http://169.254.0.1/hook",
        "http://[fe80::1]/",
        # Link-local inside an IPv6 address (mapped, NAT64) too.
        "http://[::ffff:169.254.0.1]/",
        "http://[64:ff9b::a9fe:1]/",
    ):
        with pytest.raises(TargetRefused, match="never called") as refused:
            await check(url, allow_private=True, allowed=allowed)
        assert "meta-data" not in str(refused.value)
    with pytest.raises(TargetRefused, match="resolves to 169.254.169.254"):
        await check("http://metadata.example.com/", allow_private=True, allowed=allowed)


async def test_the_azure_and_aws_v6_metadata_services_are_never_allowed() -> None:
    """The Azure WireServer is a public address and fd00:ec2::/32 a private
    range; both stay refused under either setting."""
    allowed = frozenset({"168.63.129.16"})
    for url in (
        "http://168.63.129.16/machine",
        "http://[::ffff:168.63.129.16]/",
        "http://[fd00:ec2::254]/",
        "http://[fd00:ec2::23]/",
    ):
        with pytest.raises(TargetRefused, match="never called"):
            await check(url, allow_private=True, allowed=allowed)


async def test_an_ipv6_zone_is_refused() -> None:
    """IPv6Address equality includes the zone, so fd00:ec2::254%1 would not
    match the metadata set; a URL naming a zone is refused outright."""
    for url in ("http://[fd00:ec2::254%1]/", "http://[fd00:ec2::254%251]/"):
        with pytest.raises(TargetRefused, match="may not name an IPv6 zone"):
            await check(url, allow_private=True, allowed=frozenset())
    zoned = ipaddress.ip_address("fd00:ec2::254%1")
    assert refusal(zoned) == "a cloud metadata address"


async def test_a_slow_or_empty_resolver_is_a_refusal() -> None:
    async def empty(host: str, port: int) -> Sequence[str]:
        return ["not-an-address"]

    with pytest.raises(TargetRefused, match="cannot be resolved"):
        await check_target(
            "https://hooks.example.com/",
            allow_private=False,
            allowed_hosts=(),
            resolver=empty,
        )


async def test_the_system_resolver_is_the_default() -> None:
    """localhost resolves through the system resolver (the hosts file) to a
    loopback address, which the guard refuses."""
    assert await system_resolver("localhost", 80)
    with pytest.raises(TargetRefused, match="loopback"):
        await check_target("http://localhost/", allow_private=False, allowed_hosts=())


def test_public_addresses_have_no_refusal() -> None:
    for value in ("93.184.215.14", "2606:4700::6810:84e5", "8.8.8.8"):
        assert refusal(ipaddress.ip_address(value)) is None
    assert refusal(ipaddress.ip_address("100.100.100.200")) == (
        "a cloud metadata address"
    )
    assert refusal(ipaddress.ip_address("64:ff9b::a00:5")) == (
        "a private address inside an IPv6 address"
    )


def test_the_settings_read_the_allowed_hosts() -> None:
    settings = load_settings(
        outbound_allowed_hosts=" Mock-Platform , hooks.example.com.,, ",
        allow_private_targets=True,
    )
    assert settings.allowed_hosts == frozenset({"mock-platform", "hooks.example.com"})
    assert settings.allow_private_targets is True
    assert load_settings().allowed_hosts == frozenset()
    assert load_settings().allow_private_targets is False
