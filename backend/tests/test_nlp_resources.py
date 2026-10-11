"""Concurrency and reuse guarantees for process-local NLP resources."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from app.nlp import resources


def test_concurrent_loaders_build_one_resource(monkeypatch) -> None:
    """Requests arriving together must not load duplicate model instances."""
    resources.reset()
    calls = 0
    gate = threading.Barrier(8)
    built = resources.Resources(
        nlp=object(), segmenter=None, stopwords=frozenset(), model="test-model"
    )

    def build(_model: str) -> resources.Resources:
        nonlocal calls
        calls += 1
        return built

    monkeypatch.setattr(resources, "_build", build)

    def load() -> resources.Resources:
        gate.wait()
        return resources.load("test-model")

    with ThreadPoolExecutor(max_workers=8) as pool:
        loaded = list(pool.map(lambda _: load(), range(8)))

    assert calls == 1
    assert all(item is built for item in loaded)
    resources.reset()
