"""The SSRF guard: which URLs the server may call (dev-work-plan C9-B).

Every outbound HTTP request made on an admin's behalf (the webhook, Slack and
Teams channels of phase C9-I, the outbound heartbeat of phase C10) asks
check_target first:

1. The URL is http or https, has a host and carries no user name or password.
2. The host is resolved: every IPv4 and IPv6 address of it.
3. Every address must be public. Loopback, private (RFC 1918, fc00::/7),
   link-local (169.254.0.0/16 and fe80::/10, where cloud metadata services
   answer), shared (100.64.0.0/10), multicast, reserved (site-local
   fec0::/10 too) and unspecified addresses are refused, and so is an IPv6
   address that carries one of them (IPv4-mapped, SIIT, IPv4-compatible,
   6to4, NAT64).

Two settings relax the rule: ALLOW_PRIVATE_TARGETS=true allows every other
address, and a host that is exactly one of OUTBOUND_ALLOWED_HOSTS (no
wildcard, no subdomain) is allowed whatever it resolves to. Neither allows a
link-local or a cloud metadata address (phase C9-I decided the security
review note of C9-B: link-local has no legitimate webhook receiver, and it
is where metadata services answer, so it joined METADATA_ADDRESSES in the
never set).

The caller connects to one of Target.addresses, not to the name again, so the
DNS answer cannot change between the check and the connection (DNS
rebinding), and follows no redirect. A refusal is TargetRefused, whose text is
one readable sentence that names the host and the address, never the path or
the query of the URL (they may hold a webhook secret).

The SMTP relay of an e-mail channel is not checked here: an MSP often sends
through an internal relay, and only an admin can set it (docs/security.md).
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

SCHEMES: Final = frozenset({"http", "https"})
DEFAULT_PORTS: Final = {"http": 80, "https": 443}
MAX_URL_LENGTH: Final = 2000
# Seconds one DNS lookup may take.
RESOLVE_TIMEOUT: Final = 5.0
# Metadata services of the big clouds: refused even where ALLOW_PRIVATE_TARGETS
# or OUTBOUND_ALLOWED_HOSTS allow private addresses. 168.63.129.16 is the
# Azure WireServer (a public address); fd00:ec2::/32 holds the AWS IPv6
# metadata endpoint and the EKS Pod Identity agent.
_METADATA = (
    "169.254.169.254",
    "169.254.170.2",
    "fd00:ec2::254",
    "100.100.100.200",
    "168.63.129.16",
)
METADATA_ADDRESSES: Final = frozenset(map(ipaddress.ip_address, _METADATA))
METADATA_NETWORKS: Final = (ipaddress.IPv6Network("fd00:ec2::/32"),)
# IPv6 prefixes whose last 32 bits are an IPv4 address: NAT64 and SIIT.
CARRIER_PREFIXES: Final = (
    ipaddress.IPv6Network("64:ff9b::/96"),
    ipaddress.IPv6Network("::ffff:0:0:0/96"),
)
ADVICE: Final = (
    "Outbound requests go to public addresses only. An admin can allow this "
    "host with OUTBOUND_ALLOWED_HOSTS, or private targets with "
    "ALLOW_PRIVATE_TARGETS."
)
NEVER: Final = (
    "Link-local and metadata addresses are never called, whatever "
    "OUTBOUND_ALLOWED_HOSTS and ALLOW_PRIVATE_TARGETS say."
)

type IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
type Resolver = Callable[[str, int], Awaitable[Sequence[str]]]


class TargetRefused(ValueError):
    """The URL may not be called; the text says why in one sentence."""


@dataclass(frozen=True, slots=True)
class Target:
    """A URL that passed the guard, with the addresses to connect to.

    allowed_by is public, allowed_host (OUTBOUND_ALLOWED_HOSTS) or
    allow_private (ALLOW_PRIVATE_TARGETS).
    """

    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...]
    allowed_by: str


async def system_resolver(host: str, port: int) -> list[str]:
    """Every address of host, through the system resolver."""
    loop = asyncio.get_running_loop()
    found = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in found]


def embedded_ipv4(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 address carries (mapped, SIIT, 6to4, NAT64 or
    the deprecated IPv4-compatible ::a.b.c.d)."""
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address.sixtofour is not None:
        return address.sixtofour
    low = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    if any(address in prefix for prefix in CARRIER_PREFIXES):
        return low
    if int(address) >> 32 == 0 and int(address) > 1:
        return low
    return None


def is_metadata(address: IpAddress) -> bool:
    """A cloud metadata address, also inside an IPv6 address. A zone id is
    ignored: IPv6Address equality includes it, so fd00:ec2::254%1 would
    otherwise not match."""
    if isinstance(address, ipaddress.IPv6Address):
        address = ipaddress.IPv6Address(int(address))
        inner = embedded_ipv4(address)
        if inner is not None and inner in METADATA_ADDRESSES:
            return True
        if any(address in network for network in METADATA_NETWORKS):
            return True
    return address in METADATA_ADDRESSES


def is_never(address: IpAddress) -> bool:
    """An address no setting ever allows: a cloud metadata or a link-local
    address (fe80::/10, 169.254.0.0/16, and either inside an IPv6 address).
    Link-local is where the metadata services answer, and no webhook receiver
    lives there, so phase C9-I refused it under ALLOW_PRIVATE_TARGETS and
    OUTBOUND_ALLOWED_HOSTS too."""
    if address.is_link_local:
        return True
    if isinstance(address, ipaddress.IPv6Address):
        inner = embedded_ipv4(address)
        if inner is not None and inner.is_link_local:
            return True
    return is_metadata(address)


def refusal(address: IpAddress) -> str | None:
    """Why the address may not be called (a phrase), or None when it is
    public."""
    if isinstance(address, ipaddress.IPv6Address):
        inner = embedded_ipv4(address)
        if inner is not None:
            reason = refusal(inner)
            if reason is not None:
                return f"{reason} inside an IPv6 address"
    if is_metadata(address):
        return "a cloud metadata address"
    if address.is_unspecified:
        return "the unspecified address"
    if address.is_loopback:
        return "a loopback address"
    if address.is_link_local:
        return "a link-local address"
    if address.is_multicast:
        return "a multicast address"
    if address.is_private:
        return "a private address"
    if address.is_reserved:
        return "a reserved address"
    if isinstance(address, ipaddress.IPv6Address) and address.is_site_local:
        return "a site-local address"
    if not address.is_global:
        return "an address that is not public"
    return None


def refused_text(
    host: str, literal: IpAddress | None, address: IpAddress, reason: str, advice: str
) -> str:
    """The sentence of a refusal: the host, the address and why."""
    if literal is not None:
        return f"{address} is {reason}. {advice}"
    return f"{host} resolves to {address}, {reason}. {advice}"


def parse_address(value: str) -> IpAddress | None:
    """The address in value without a zone id, or None when it is a name."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.scope_id:
        return ipaddress.IPv6Address(int(address))
    return address


async def check_target(
    url: str,
    *,
    allow_private: bool,
    allowed_hosts: Collection[str],
    resolver: Resolver = system_resolver,
) -> Target:
    """The checked target of url; TargetRefused when it may not be called."""
    if len(url) > MAX_URL_LENGTH:
        raise TargetRefused(f"The URL is longer than {MAX_URL_LENGTH} characters.")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise TargetRefused("The URL cannot be read.") from None
    scheme = parts.scheme.lower()
    if scheme not in SCHEMES:
        raise TargetRefused("Only http:// and https:// URLs can be called.")
    if parts.username is not None or parts.password is not None:
        raise TargetRefused("A URL may not carry a user name or password.")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise TargetRefused("The URL has no host.")
    if "%" in host:
        # An IPv6 zone ([fd00:ec2::254%1]) names an interface, never a
        # webhook receiver, and would slip past the exact address checks.
        raise TargetRefused("A URL may not name an IPv6 zone.")
    port = port or DEFAULT_PORTS[scheme]
    literal = parse_address(host)
    if literal is not None:
        addresses: list[IpAddress] = [literal]
    else:
        addresses = await resolve(host, port, resolver)
    refused = [
        (address, reason)
        for address in addresses
        if (reason := refusal(address)) is not None
    ]
    # A link-local or metadata address is never allowed, whatever the
    # settings say.
    never = [item for item in refused if is_never(item[0])]
    if never:
        address, reason = never[0]
        raise TargetRefused(refused_text(host, literal, address, reason, NEVER))
    if not refused:
        allowed_by = "public"
    elif host in allowed_hosts:
        allowed_by = "allowed_host"
    elif allow_private:
        allowed_by = "allow_private"
    else:
        address, reason = refused[0]
        raise TargetRefused(refused_text(host, literal, address, reason, ADVICE))
    return Target(
        scheme=scheme,
        host=host,
        port=port,
        addresses=tuple(str(address) for address in addresses),
        allowed_by=allowed_by,
    )


async def resolve(host: str, port: int, resolver: Resolver) -> list[IpAddress]:
    """Every address of host, without repeats; TargetRefused when it has none."""
    unresolved = TargetRefused(f"The host {host} cannot be resolved.")
    try:
        async with asyncio.timeout(RESOLVE_TIMEOUT):
            found = await resolver(host, port)
    except (OSError, UnicodeError, TimeoutError):
        raise unresolved from None
    addresses: list[IpAddress] = []
    for value in found:
        # A zone id (fe80::1%eth0) is dropped; the address is link-local anyway.
        address = parse_address(value.split("%", 1)[0])
        if address is not None and address not in addresses:
            addresses.append(address)
    if not addresses:
        raise unresolved
    return addresses
