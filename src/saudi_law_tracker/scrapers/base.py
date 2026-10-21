"""Scraper base class and registry.

Each source gets a subclass of `BaseScraper` decorated with `@register("key")`,
where `key` matches the `scraper:` field of a block in config/sources.yaml.
Implement `discover()` as an async generator of `RegulatoryDocument`s.

`backfill` is a generic hint threaded down from the CLI's `--backfill` flag:
most scrapers can ignore it, but one that paginates a bounded window on
normal runs (see bureau_of_experts.py) can check `self.backfill` to walk its
full result set once instead, e.g. to retroactively enrich older rows.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Callable
from typing import ClassVar
from urllib.parse import urljoin

from ..config import SourceConfig
from ..http import HttpClient
from ..logging import get_logger
from ..models import RegulatoryDocument
from ..storage import DocumentStore

_REGISTRY: dict[str, type[BaseScraper]] = {}


def register(key: str) -> Callable[[type[BaseScraper]], type[BaseScraper]]:
    def _wrap(cls: type[BaseScraper]) -> type[BaseScraper]:
        if key in _REGISTRY:
            raise ValueError(f"duplicate scraper key: {key}")
        cls.key = key
        _REGISTRY[key] = cls
        return cls

    return _wrap


def get_scraper(key: str) -> type[BaseScraper]:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise KeyError(f"no scraper registered for '{key}'. Known: {sorted(_REGISTRY)}") from None


def registered_keys() -> list[str]:
    return sorted(_REGISTRY)


class BaseScraper(abc.ABC):
    key: ClassVar[str] = ""
    tuned: ClassVar[bool] = False
    """True for a scraper written with source-specific selectors that emits
    `verified=True` rows; False (the default, and what `GenericListingScraper`
    leaves it at) for one still on the generic harvester. `saudi-law-tracker
    sources` reads this directly off the class -- keep it in sync with
    whatever a scraper's `discover()` actually sets on `RegulatoryDocument`,
    since nothing enforces the two matching."""

    def __init__(
        self,
        source: SourceConfig,
        http: HttpClient,
        store: DocumentStore,
        *,
        backfill: bool = False,
    ) -> None:
        self.source = source
        self.http = http
        self.store = store
        self.backfill = backfill
        self.log = get_logger(f"scraper.{source.key}")

    def abs_url(self, path: str) -> str:
        return urljoin(self.source.base_url.rstrip("/") + "/", path.lstrip("/"))

    @abc.abstractmethod
    def discover(self) -> AsyncIterator[RegulatoryDocument]:
        """Yield documents found for this source. Implemented as `async def` +
        `yield`, so the abstract signature is a plain method returning the
        iterator."""
        raise NotImplementedError


def load_all_scrapers() -> None:
    """Import every sibling module so `@register` decorators run."""

    import importlib
    import pkgutil

    package = importlib.import_module(__package__)
    for mod in pkgutil.iter_modules(package.__path__):
        if mod.name not in {"base", "_common"}:
            importlib.import_module(f"{__package__}.{mod.name}")
