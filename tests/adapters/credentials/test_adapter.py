import subprocess
import sys
from unittest.mock import patch

import pytest

if sys.platform != "darwin":
    pytest.skip(
        "CredentialAdapter requires the macOS Security framework (darwin only); "
        "this is the documented non-macOS CI skip fallback (AGENTS.md).",
        allow_module_level=True,
    )

from adapters.credentials.adapter import (
    DEFAULT_SERVICE,
    CredentialAdapter,
    KeychainAccessError,
    KeychainItemNotFoundError,
)


def test_store_then_get_returns_same_secret(adapter, cleanup):
    cleanup.append("ref-1")
    adapter.store("ref-1", "super-secret")

    assert adapter.get("ref-1") == "super-secret"


def test_store_twice_updates_rather_than_duplicates(adapter, cleanup):
    cleanup.append("ref-2")
    adapter.store("ref-2", "secret-a")
    adapter.store("ref-2", "secret-b")

    assert adapter.get("ref-2") == "secret-b"


def test_delete_then_get_raises(adapter, cleanup):
    cleanup.append("ref-3")
    adapter.store("ref-3", "secret")
    adapter.delete("ref-3")

    with pytest.raises(KeychainItemNotFoundError):
        adapter.get("ref-3")


def test_get_for_never_stored_reference_raises(adapter):
    with pytest.raises(KeychainItemNotFoundError):
        adapter.get("never-stored-reference")


def test_durability_across_adapter_recreation(service, cleanup):
    cleanup.append("ref-restart")

    first = CredentialAdapter(service=service)
    first.store("ref-restart", "persisted-secret")
    del first

    second = CredentialAdapter(service=service)
    assert second.get("ref-restart") == "persisted-secret"


def test_forced_keychain_failure_propagates_on_store(adapter):
    with patch.object(adapter, "_sec_item_add", return_value=-34018):
        with pytest.raises(KeychainAccessError):
            adapter.store("forced-fail", "secret")


def test_forced_keychain_failure_propagates_on_get(adapter):
    with patch.object(adapter, "_sec_item_copy_matching", return_value=(-34018, None)):
        with pytest.raises(KeychainAccessError):
            adapter.get("forced-fail")


def test_forced_keychain_failure_propagates_on_delete(adapter):
    with patch.object(adapter, "_sec_item_delete", return_value=-34018):
        with pytest.raises(KeychainAccessError):
            adapter.delete("forced-fail")


def test_test_namespace_is_distinct_from_production_default(service):
    assert service != DEFAULT_SERVICE
    assert ".test." in service


def test_no_subprocess_spawned_during_store_get_delete(adapter, cleanup):
    cleanup.append("ref-no-subprocess")

    with (
        patch("subprocess.Popen", side_effect=AssertionError("subprocess.Popen invoked")),
        patch("subprocess.run", side_effect=AssertionError("subprocess.run invoked")),
        patch("os.posix_spawn", side_effect=AssertionError("os.posix_spawn invoked")),
        patch("os.posix_spawnp", side_effect=AssertionError("os.posix_spawnp invoked")),
        patch("os.execv", side_effect=AssertionError("os.execv invoked")),
        patch("os.execve", side_effect=AssertionError("os.execve invoked")),
        patch("os.execvp", side_effect=AssertionError("os.execvp invoked")),
        patch("os.execvpe", side_effect=AssertionError("os.execvpe invoked")),
        patch("os.system", side_effect=AssertionError("os.system invoked")),
        patch("os.popen", side_effect=AssertionError("os.popen invoked")),
        # os.spawn*/os.execl*/os.execlp/os.execle are pure-Python wrappers over
        # os.fork()+os.exec*() (CPython's os.py _spawnvef); patching os.fork
        # here closes the entire os.spawn* family in one patch (verified
        # directly: os.spawnv raises through this patch, not through
        # posix_spawn), and os.execv/execve/execvp above already cover
        # os.execl/execle/execlp transitively (also verified directly).
        patch("os.fork", side_effect=AssertionError("os.fork invoked")),
    ):
        adapter.store("ref-no-subprocess", "secret")
        assert adapter.get("ref-no-subprocess") == "secret"
        adapter.delete("ref-no-subprocess")


def test_subprocess_patch_guard_is_effective():
    with patch("subprocess.run", side_effect=AssertionError("subprocess.run invoked")):
        with pytest.raises(AssertionError):
            subprocess.run(["true"])


def test_store_uses_exact_accessibility_class_and_no_data_protection_flag(adapter, cleanup):
    from Security import (
        kSecAttrAccessible,
        kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        kSecUseDataProtectionKeychain,
    )

    cleanup.append("ref-accessibility")
    captured_queries: list[dict] = []
    original_add = adapter._sec_item_add

    def spy_add(query):
        captured_queries.append(dict(query))
        return original_add(query)

    with patch.object(adapter, "_sec_item_add", side_effect=spy_add):
        adapter.store("ref-accessibility", "secret")

    assert captured_queries, "expected _sec_item_add to be invoked"
    query = captured_queries[0]
    assert query[kSecAttrAccessible] == kSecAttrAccessibleWhenUnlockedThisDeviceOnly

    # A string/substring check on these PyObjC-bridged constants is a tautology:
    # str(kSecUseDataProtectionKeychain) is its underlying four-char CFString
    # code (e.g. "nleg"), never the Python constant's name. The only genuine
    # check is object identity/equality against the actual constant.
    assert not any(key == kSecUseDataProtectionKeychain for key in query)


def test_no_secret_value_appears_in_adapter_source():
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    source = (repo_root / "adapters" / "credentials" / "adapter.py").read_text()
    assert "super-secret" not in source
    assert "persisted-secret" not in source
