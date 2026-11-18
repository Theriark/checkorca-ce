"""Repository base class and the @guarded decorator.

A public method of a repository must be decorated with @guarded(verb): the
decorator checks that the first argument is a Principal and asks the policy
about Action(resource, verb) before the method body runs. A subclass with an
undecorated public method fails at import time, so no repository call can skip
the policy.
"""

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, Concatenate

from sqlalchemy.ext.asyncio import AsyncSession

from app.access import AccessPolicy, Action, Principal

GUARD_ATTRIBUTE = "__access_verb__"

type RepoMethod[S, **P, R] = Callable[Concatenate[S, Principal, P], Awaitable[R]]


def guarded[S: Repository, **P, R](
    verb: str,
) -> Callable[[RepoMethod[S, P, R]], RepoMethod[S, P, R]]:
    """Run the access policy for (resource, verb) before the method."""

    def decorate(method: RepoMethod[S, P, R]) -> RepoMethod[S, P, R]:
        @functools.wraps(method)
        async def run(
            self: S, principal: Principal, /, *args: P.args, **kwargs: P.kwargs
        ) -> R:
            if not isinstance(principal, Principal):
                raise TypeError("a repository call needs a Principal first")
            self.policy.check(principal, Action(self.resource, verb))
            return await method(self, principal, *args, **kwargs)

        setattr(run, GUARD_ATTRIBUTE, verb)
        return run

    return decorate


class Repository:
    """Base of every repository: a database session and the access policy."""

    resource: ClassVar[str]

    def __init__(self, db: AsyncSession, policy: AccessPolicy) -> None:
        self.db = db
        self.policy = policy

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for name, member in vars(cls).items():
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            if not hasattr(member, GUARD_ATTRIBUTE):
                raise TypeError(
                    f"{cls.__name__}.{name} is public and must use @guarded"
                )


def guarded_methods(cls: type[Repository]) -> dict[str, str]:
    """Public method name to verb, for the access tests."""
    return {
        name: getattr(member, GUARD_ATTRIBUTE)
        for name, member in vars(cls).items()
        if not name.startswith("_") and inspect.isfunction(member)
    }
