from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fitness_rag.bluesky import (
    COLLECTION,
    BlueskyClient,
    BlueskyRequestError,
    PublicationStore,
    PublishError,
    compose_post,
    publication_status,
    publish_draft,
)


ACCOUNT = "studio.bsky.social"
DID = "did:plc:abcdefghijklmnopqrstuvwx"
DRAFT = {
    "id": "e6af7959-f2ae-4b7f-8cef-de10508e3fb1",
    "language": "en",
    "status": "approved",
    "research": {"sources": [
        {"title": "First study", "url": "https://pubmed.ncbi.nlm.nih.gov/34542869/"},
        {"title": "Second study", "url": "https://example.org/study"},
    ]},
}
POST_TEXT = "How many reps did you have left? Estimates vary."


class BlueskyPostTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = PublicationStore(Path(directory.name) / "bluesky.sqlite3")
        env = patch.dict(os.environ, {"BLUESKY_HANDLE": ACCOUNT, "BLUESKY_APP_PASSWORD": "test-password"})
        env.start()
        self.addCleanup(env.stop)
        patcher = patch("fitness_rag.bluesky.BlueskyClient")
        self.client_class = patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.client_class.return_value
        self.client.did = DID
        self.client.get.return_value = None
        self.client.create.side_effect = self.create_receipt

    @staticmethod
    def create_receipt(key, record):
        return {"uri": f"at://{DID}/{COLLECTION}/{key}", "cid": "example-cid"}

    def test_unapproved_and_chinese_drafts_cannot_publish(self):
        for overrides in ({"status": "draft"}, {"language": "zh"}):
            with self.subTest(overrides=overrides), self.assertRaises(PublishError) as failure:
                publish_draft(self.store, {**DRAFT, **overrides}, ACCOUNT, POST_TEXT, [1])
            self.assertEqual(failure.exception.status, 409)
        self.client_class.assert_not_called()

    def test_missing_credentials_do_not_prepare_or_send_a_post(self):
        with patch.dict(os.environ, {"BLUESKY_APP_PASSWORD": ""}):
            self.assertIsNone(publication_status(None)["configured_account"])
            with self.assertRaises(PublishError) as failure:
                publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1])
        self.assertEqual(failure.exception.status, 503)
        self.assertIsNone(self.store.get(DRAFT["id"]))
        self.client_class.assert_not_called()

    def test_post_checks_the_full_character_count_and_source_selection(self):
        suffix = "\n\nSources: [S1]"
        text = "a" * (300 - len(suffix))
        self.assertEqual(len(compose_post(DRAFT, text, [1])["text"]), 300)
        for body, sources in ((text + "x", [1]), (POST_TEXT, []), (POST_TEXT, [3]), (POST_TEXT, [1, 1])):
            with self.subTest(sources=sources), self.assertRaises(PublishError) as failure:
                compose_post(DRAFT, body, sources)
            self.assertEqual(failure.exception.status, 422)

    def test_facets_use_utf8_offsets_and_link_only_to_selected_sources(self):
        record = compose_post(DRAFT, "Estimates vary — café 🏋.", [2, 1])
        encoded = record["text"].encode("utf-8")
        self.assertEqual(record["langs"], ["en"])
        for index, facet in enumerate(record["facets"], 1):
            offset = facet["index"]
            self.assertEqual(encoded[offset["byteStart"]:offset["byteEnd"]].decode(), f"[S{index}]")
            self.assertEqual(facet["features"][0]["uri"], DRAFT["research"]["sources"][index - 1]["url"])

    def test_successful_post_persists_receipt_and_repeat_does_not_write(self):
        result = publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1])
        self.assertEqual(result["state"], "published")
        key, record = self.client.create.call_args.args
        self.assertRegex(key, r"^[2-7ab][2-7a-z]{12}$")
        self.assertTrue(record["createdAt"].endswith("Z"))
        self.assertEqual(result["permalink"], f"https://bsky.app/profile/{DID}/post/{key}")
        self.assertEqual(publication_status(self.store.get(DRAFT["id"])), result)
        self.assertEqual(publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1]), result)
        self.client.create.assert_called_once()

    def test_timeout_after_write_is_reconciled_without_a_second_write(self):
        def create_then_timeout(key, record):
            stored = self.store.get(DRAFT["id"])
            self.assertEqual(stored["record_key"], key)
            self.assertEqual(publication_status(stored)["record"], record)
            self.client.get.return_value = {**self.create_receipt(key, record), "value": record}
            raise BlueskyRequestError()

        self.client.create.side_effect = create_then_timeout
        result = publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1])
        self.assertEqual(result["state"], "published")
        self.assertEqual(self.client.get.call_count, 2)
        self.client.create.assert_called_once()

    def test_retry_rejects_account_or_preview_changes_and_reuses_original_key(self):
        self.client.create.side_effect = BlueskyRequestError()
        with self.assertRaises(BlueskyRequestError):
            publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1])
        key = self.store.get(DRAFT["id"])["record_key"]
        self.assertEqual(publication_status(self.store.get(DRAFT["id"]))["state"], "pending")
        self.client.did = "did:plc:zyxwvutsrqponmlkjihgfedc"
        with self.assertRaisesRegex(PublishError, "different Bluesky account"):
            publish_draft(self.store, DRAFT, ACCOUNT, None, [])
        self.client.did = DID
        with self.assertRaisesRegex(PublishError, "same reviewed preview"):
            publish_draft(self.store, DRAFT, ACCOUNT, "Changed post", [1])
        self.client.create.assert_called_once()
        self.client.create.side_effect = self.create_receipt
        result = publish_draft(self.store, DRAFT, ACCOUNT, None, [])
        self.assertEqual(result["state"], "published")
        self.assertEqual(self.client.create.call_args.args[0], key)

    def test_changed_account_after_preview_is_rejected_before_login(self):
        with self.assertRaisesRegex(PublishError, "project account changed"):
            publish_draft(self.store, DRAFT, "other.bsky.social", POST_TEXT, [1])
        self.client_class.assert_not_called()

    def test_existing_record_with_different_content_is_never_adopted(self):
        def get_collision(key):
            return {**self.create_receipt(key, {}), "value": {"text": "Other post"}}

        self.client.get.side_effect = get_collision
        with self.assertRaisesRegex(PublishError, "differs"):
            publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1])
        self.client.create.assert_not_called()


class BlueskyTransportTests(unittest.TestCase):
    def test_hosted_account_writes_to_the_pds_with_the_saved_key(self):
        session = {
            "did": DID,
            "accessJwt": "test-session-token",
            "didDoc": {"service": [{
                "type": "AtprotoPersonalDataServer",
                "serviceEndpoint": "https://example.us-east.host.bsky.network",
            }]},
        }
        with patch("fitness_rag.bluesky._rpc", Mock(side_effect=[session, BlueskyRequestError(400, "RecordNotFound"), {}])) as rpc:
            client = BlueskyClient(ACCOUNT, "test-password")
            self.assertIsNone(client.get("3jzfcijpj2z2a"))
            client.create("3jzfcijpj2z2a", {"text": POST_TEXT})
        self.assertEqual(rpc.call_args.args, (
            "https://example.us-east.host.bsky.network", "com.atproto.repo.createRecord",
        ))
        self.assertEqual(rpc.call_args.kwargs["body"]["rkey"], "3jzfcijpj2z2a")
        self.assertEqual(rpc.call_args.kwargs["body"]["repo"], DID)
