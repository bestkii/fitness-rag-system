from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fitness_rag.bluesky import (
    COLLECTION,
    MAX_CARD_BYTES,
    BlueskyClient,
    BlueskyRequestError,
    PublicationStore,
    PostCard,
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
JPEG_BYTES = b"\xff\xd8\xfffixture\xff\xd9"
RED_CARD = PostCard(JPEG_BYTES, "Myth: 2 reps left is exact. Clarification: It is an estimate.", "red")
CARD_BLOB = {
    "$type": "blob",
    "ref": {"$link": "fixture-blob"},
    "mimeType": "image/jpeg",
    "size": len(JPEG_BYTES),
}


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
        self.client.upload_card.return_value = CARD_BLOB

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

    def test_preview_image_is_uploaded_and_included_with_its_alt_text(self):
        result = publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1], RED_CARD)
        self.client.upload_card.assert_called_once_with(JPEG_BYTES)
        _, record = self.client.create.call_args.args
        self.assertEqual(record["embed"], {
            "$type": "app.bsky.embed.images",
            "images": [{"image": CARD_BLOB, "alt": RED_CARD.alt}],
        })
        self.assertEqual(result["record"], record)
        self.assertEqual(result["card"]["jpeg"], base64.b64encode(JPEG_BYTES).decode())
        self.assertEqual(result["card"]["palette"], "red")
        self.assertEqual(self.store.next_palette(), "gold")

    def test_rotation_uses_card_reservations_and_skips_older_text_posts(self):
        publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1])
        self.assertEqual(self.store.next_palette(), "red")
        for index, palette in enumerate(("red", "gold", "blue", "red")):
            self.assertEqual(self.store.next_palette(), palette)
            draft = {**DRAFT, "id": f"draft-{index}"}
            card = PostCard(JPEG_BYTES, RED_CARD.alt, palette)
            result = publish_draft(self.store, draft, ACCOUNT, POST_TEXT, [1], card)
            self.assertEqual(result["card"]["palette"], palette)
        self.assertEqual(self.store.next_palette(), "gold")

    def test_stale_palette_requires_a_new_preview_without_an_upload(self):
        card = PostCard(JPEG_BYTES, RED_CARD.alt, "gold")
        with self.assertRaisesRegex(PublishError, "palette changed"):
            publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1], card)
        self.assertIsNone(self.store.get(DRAFT["id"]))
        self.client.upload_card.assert_not_called()

    def test_retry_after_failed_upload_uses_the_same_card_and_key(self):
        self.client.upload_card.side_effect = BlueskyRequestError()
        with self.assertRaises(BlueskyRequestError):
            publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1], RED_CARD)
        row = self.store.get(DRAFT["id"])
        self.assertEqual(publication_status(row)["card"]["alt"], RED_CARD.alt)
        self.client.create.assert_not_called()
        self.client.upload_card.side_effect = None
        publish_draft(self.store, DRAFT, ACCOUNT, None, [])
        self.assertEqual(self.client.create.call_args.args[0], row["record_key"])
        self.assertEqual(self.client.upload_card.call_count, 2)
        self.assertEqual(self.client.upload_card.call_args.args, (JPEG_BYTES,))

    def test_retry_after_uncertain_post_does_not_upload_a_second_image(self):
        self.client.create.side_effect = BlueskyRequestError()
        with self.assertRaises(BlueskyRequestError):
            publish_draft(self.store, DRAFT, ACCOUNT, POST_TEXT, [1], RED_CARD)
        key, record = self.client.create.call_args.args
        self.client.get.return_value = {**self.create_receipt(key, record), "value": record}
        result = publish_draft(self.store, DRAFT, ACCOUNT, None, [])
        self.assertEqual(result["state"], "published")
        self.client.upload_card.assert_called_once()
        self.client.create.assert_called_once()

    def test_card_requires_valid_base64_jpeg_alt_text_and_palette(self):
        encoded = base64.b64encode(JPEG_BYTES).decode()
        self.assertEqual(PostCard.decode(encoded, RED_CARD.alt, "red"), RED_CARD)
        oversized = base64.b64encode(b"\xff\xd8\xff" + b"x" * MAX_CARD_BYTES + b"\xff\xd9").decode()
        for data, alt, palette in (
            ("invalid!", RED_CARD.alt, "red"),
            ("ZGF0YQ==", RED_CARD.alt, "red"),
            (oversized, RED_CARD.alt, "red"),
            (encoded, " ", "red"),
            (encoded, RED_CARD.alt, "green"),
        ):
            with self.subTest(palette=palette, length=len(data)), self.assertRaises(PublishError):
                PostCard.decode(data, alt, palette)


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

    def test_image_transport_uses_raw_jpeg_and_validates_the_blob(self):
        session = {"did": DID, "accessJwt": "test-session-token"}
        responses = [session, {"blob": CARD_BLOB}, {"blob": {**CARD_BLOB, "size": 1}}]
        with patch("fitness_rag.bluesky._rpc", Mock(side_effect=responses)) as rpc:
            client = BlueskyClient(ACCOUNT, "test-password")
            self.assertEqual(client.upload_card(JPEG_BYTES), CARD_BLOB)
            self.assertEqual(rpc.call_args.args[1], "com.atproto.repo.uploadBlob")
            self.assertEqual(rpc.call_args.kwargs["jpeg"], JPEG_BYTES)
            with self.assertRaises(BlueskyRequestError):
                client.upload_card(JPEG_BYTES)
