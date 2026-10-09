"""Logic edits can update a binding digest without weakening native identity checks."""

from copy import deepcopy
import unittest

from tools.rebind_native_catalog import rebind
from ..integrations.rom.native_generation import catalog_digest
from .test_native_ap_catalog import fixture


class CatalogRebindTests(unittest.TestCase):
    def test_logic_changes_update_digest_without_mutating_original(self) -> None:
        catalog, bindings = fixture()
        updated = deepcopy(catalog)
        updated["locations"][0]["requires"] = {"item": "hammer"}
        result = rebind(catalog, updated, bindings)
        self.assertEqual(result["catalog_sha256"], catalog_digest(updated))
        self.assertEqual(bindings["catalog_sha256"], catalog_digest(catalog))
        self.assertEqual(result["locations"], bindings["locations"])

    def test_changed_item_identity_is_rejected(self) -> None:
        catalog, bindings = fixture()
        updated = deepcopy(catalog)
        updated["items"][0]["id"] = "new-hammer"
        with self.assertRaises(ValueError):
            rebind(catalog, updated, bindings)
