"""CredentialAdapter — implements CredentialPort against the macOS Keychain.

Uses ``pyobjc-framework-Security`` direct bindings to the Security framework's
``SecItem*`` API (in-process; never shells out to a subprocess, unlike a
cross-platform abstraction such as ``keyring``, whose default backend
selection is not pinned to a verified in-process implementation).

Public contract (per the Interfaces specification): ``get()``, ``store()``,
``delete()``. ``_read_keychain()``, ``_write_keychain()``, and
``_remove_keychain()`` are internal, invoked only from those public
operations. ``_sec_item_*`` are thin wrappers around the Security-framework
calls, kept separate so tests can spy on/inspect the exact query dictionaries
passed to the framework (acceptance criterion: effective-configuration
verification, not adapter-source inspection alone).

``reference`` → Keychain identity mapping: ``reference`` is used verbatim as
the Keychain item's account (``kSecAttrAccount``); the service
(``kSecAttrService``) is fixed per adapter instance, defaulting to
``DEFAULT_SERVICE`` for production use. Tests must construct a
``CredentialAdapter`` with a distinct, test-scoped ``service`` so test runs
never read, write, or delete a production credential entry.
"""

from __future__ import annotations

from core.ports.credentials import CredentialPort
from Security import (
    SecItemAdd,
    SecItemCopyMatching,
    SecItemDelete,
    SecItemUpdate,
    errSecDuplicateItem,
    errSecItemNotFound,
    errSecSuccess,
)

DEFAULT_SERVICE = "com.atria.credentials"


class KeychainAccessError(RuntimeError):
    """Raised when the Keychain reports a failure other than item-not-found."""


class KeychainItemNotFoundError(LookupError):
    """Raised when no Keychain item exists for the requested reference."""


class CredentialAdapter(CredentialPort):
    def __init__(self, service: str = DEFAULT_SERVICE) -> None:
        self._service = service

    def _base_query(self, reference: str) -> dict:
        from Security import kSecAttrAccount, kSecAttrService, kSecClass, kSecClassGenericPassword

        return {
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: self._service,
            kSecAttrAccount: reference,
        }

    def _sec_item_add(self, query: dict) -> int:
        status = SecItemAdd(query, None)
        return status[0] if isinstance(status, tuple) else status

    def _sec_item_copy_matching(self, query: dict) -> tuple[int, object | None]:
        result = SecItemCopyMatching(query, None)
        if isinstance(result, tuple):
            return result
        return result, None

    def _sec_item_update(self, query: dict, attributes_to_update: dict) -> int:
        status = SecItemUpdate(query, attributes_to_update)
        return status[0] if isinstance(status, tuple) else status

    def _sec_item_delete(self, query: dict) -> int:
        status = SecItemDelete(query)
        return status[0] if isinstance(status, tuple) else status

    def _write_keychain(self, reference: str, secret: str) -> None:
        from Security import (
            kSecAttrAccessible,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            kSecValueData,
        )

        # Deferred to Increment 6 (packaging/code signing/notarization): the macOS
        # Data Protection keychain (kSecUseDataProtectionKeychain) requires the
        # calling process to be code-signed with a keychain-access-groups
        # entitlement, which no binary in this prototype has yet — an unsigned
        # process fails every SecItem* call with errSecMissingEntitlement when
        # that flag is set (verified directly). Until Increment 6 ships a signed
        # binary, this adapter targets the legacy file-based Keychain, which is
        # still the real macOS Keychain and still honors the requested
        # accessibility/protection class below. Operator-approved deviation from
        # this increment's originally-approved spec (2026-11-24).
        #
        # The match query used to locate an existing item (for SecItemUpdate)
        # deliberately omits kSecAttrAccessible: a search predicate on that
        # attribute would fail to match an item this adapter itself created
        # under a prior accessibility value, misreporting a legitimate update
        # as a write failure. The attribute is set on add, and re-asserted on
        # update via attributes_to_update instead.
        match_query = self._base_query(reference)
        attributes = {
            kSecValueData: secret.encode("utf-8"),
            kSecAttrAccessible: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        }

        add_query = dict(match_query)
        add_query.update(attributes)
        status = self._sec_item_add(add_query)

        if status == errSecDuplicateItem:
            status = self._sec_item_update(match_query, attributes)

        if status != errSecSuccess:
            raise KeychainAccessError(
                f"Keychain write failed for reference {reference!r} (OSStatus {status})"
            )

    def _read_keychain(self, reference: str) -> str:
        from Security import (
            kSecAttrAccessible,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            kSecMatchLimit,
            kSecMatchLimitOne,
            kSecReturnData,
        )

        query = self._base_query(reference)
        query[kSecAttrAccessible] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        query[kSecReturnData] = True
        query[kSecMatchLimit] = kSecMatchLimitOne

        status, result = self._sec_item_copy_matching(query)

        if status == errSecItemNotFound:
            raise KeychainItemNotFoundError(f"No Keychain entry for reference {reference!r}")
        if status != errSecSuccess:
            raise KeychainAccessError(
                f"Keychain read failed for reference {reference!r} (OSStatus {status})"
            )

        return bytes(result).decode("utf-8")

    def _remove_keychain(self, reference: str) -> None:
        from Security import kSecAttrAccessible, kSecAttrAccessibleWhenUnlockedThisDeviceOnly

        query = self._base_query(reference)
        query[kSecAttrAccessible] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        status = self._sec_item_delete(query)

        if status == errSecItemNotFound:
            raise KeychainItemNotFoundError(f"No Keychain entry for reference {reference!r}")
        if status != errSecSuccess:
            raise KeychainAccessError(
                f"Keychain delete failed for reference {reference!r} (OSStatus {status})"
            )

    def get(self, reference: str) -> str:
        return self._read_keychain(reference)

    def store(self, reference: str, secret: str) -> None:
        self._write_keychain(reference, secret)

    def delete(self, reference: str) -> None:
        self._remove_keychain(reference)
