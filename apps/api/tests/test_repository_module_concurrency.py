import hashlib
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from types import ModuleType

import pytest

from huginn_muninn_api.core.evidence_api import EvidenceApi
from huginn_muninn_api.core.guardduty_ingest_api import GuardDutyIngestApi
from huginn_muninn_api.core.repository_module_lock import repository_module_transaction
from huginn_muninn_api.core.wazuh_ingest_api import WazuhIngestApi


@pytest.fixture
def repository(tmp_path):
    root = Path(__file__).resolve().parents[3]
    shutil.copytree(root / "core", tmp_path / "core", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(root / "reports", tmp_path / "reports")
    return tmp_path


def module_state():
    return {k: v for k, v in sys.modules.copy().items() if k == "core" or k.startswith("core.")}


def fingerprints(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_original_160_call_reproduction(repository):
    apis = [EvidenceApi(repository) for _ in range(8)]

    def call(i):
        api = apis[i]
        calls = [
            api.summary,
            lambda: api.finding("weakness:15953a2c-3b98-4640-9401-1306f95162e3"),
            lambda: api.mitre("T1078"),
            lambda: api.weakness("15953a2c-3b98-4640-9401-1306f95162e3"),
            lambda: api.recommendation("design.post_auth_telemetry_layer"),
            lambda: api.confidence("high"),
        ]
        return calls[i % 6]()

    expected = [call(i) for i in range(8)]
    before, modules = fingerprints(repository), module_state()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in range(20):
            barrier = Barrier(8, timeout=5)

            def parallel(i, barrier=barrier):
                barrier.wait()
                return call(i)

            futures = [pool.submit(parallel, i) for i in range(8)]
            assert [f.result(timeout=10) for f in futures] == expected
    assert module_state() == modules
    assert fingerprints(repository) == before


def test_mixed_loaders_and_root_isolation(repository, tmp_path):
    second = tmp_path / "second"
    shutil.copytree(repository / "core", second / "core")
    (second / "reports").mkdir()
    (second / "reports/evidence-index.json").write_text('{"schema_version":"1.0","evidence":[]}')
    loaders = [
        EvidenceApi(repository)._load_repository_evidence_query,
        WazuhIngestApi(repository)._repository_modules,
        GuardDutyIngestApi(repository)._repository_modules,
        EvidenceApi(second)._load_repository_evidence_query,
        WazuhIngestApi(second)._repository_modules,
        GuardDutyIngestApi(second)._repository_modules,
    ]
    before, modules = fingerprints(repository), module_state()
    with ThreadPoolExecutor(max_workers=6) as pool:
        for _ in range(5):
            barrier = Barrier(6, timeout=5)

            def load(i, barrier=barrier):
                barrier.wait()
                return loaders[i]()

            futures = [pool.submit(load, i) for i in range(6)]
            results = [f.result(timeout=10) for f in futures]
            for i, result in enumerate(results):
                cls = result if i % 3 == 0 else result["KnowledgeGraph"]
                expected_root = repository if i < 3 else second
                method = cls.__init__
                assert Path(method.__code__.co_filename).is_relative_to(expected_root / "core")
    assert EvidenceApi(repository).summary()["match_count"] == 6
    assert EvidenceApi(second).summary()["match_count"] == 0
    assert module_state() == modules
    assert fingerprints(repository) == before


def test_pause_and_exception_restore_modules(repository, monkeypatch):
    api = EvidenceApi(repository)
    entered, release, attempted, second_entered = Event(), Event(), Event(), Event()
    original = api._load_module
    failure = RuntimeError("controlled initialization failure")
    modules = module_state()

    def paused(name, path):
        sys.modules["core.diagnostic_transitive"] = ModuleType("core.diagnostic_transitive")
        entered.set()
        assert release.wait(5)
        raise failure

    monkeypatch.setattr(api, "_load_module", paused)

    def competing():
        attempted.set()
        with repository_module_transaction():
            second_entered.set()
            assert "core.diagnostic_transitive" not in sys.modules

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(api.summary)
        try:
            assert entered.wait(5)
            other = pool.submit(competing)
            assert attempted.wait(5)
            assert not second_entered.wait(0.1)
        finally:
            release.set()
        with pytest.raises(RuntimeError) as exc:
            first.result(timeout=5)
        assert exc.value is failure
        other.result(timeout=5)
    assert module_state() == modules
    monkeypatch.setattr(api, "_load_module", original)
    assert api.summary()["match_count"] == 6


def test_nested_transaction_and_none_entry_restored(monkeypatch):
    monkeypatch.setitem(sys.modules, "core.diagnostic_none", None)
    before = module_state()
    with repository_module_transaction():
        outer = ModuleType("core")
        sys.modules["core"] = outer
        with repository_module_transaction():
            sys.modules["core"] = ModuleType("core")
        assert sys.modules["core"] is outer
    assert module_state() == before
