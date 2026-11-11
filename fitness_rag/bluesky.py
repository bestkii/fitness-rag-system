from __future__ import annotations

import base64
import binascii
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SERVICE = "https://bsky.social"
COLLECTION = "app.bsky.feed.post"
MAX_POST_LENGTH = 300
MAX_CARD_BYTES = 1_000_000
CARD_PALETTES = ("red", "gold", "blue")
TID_ALPHABET = "234567abcdefghijklmnopqrstuvwxyz"
PUBLICATION_QUERY = """
    SELECT p.*, c.jpeg, c.alt, c.palette FROM bluesky_publications p
    LEFT JOIN bluesky_cards c USING (draft_id) WHERE p.draft_id = ?
"""


class PublishError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class BlueskyRequestError(PublishError):
    def __init__(self, status: int = 0, code: str = ""):
        if status in (401, 403) or code in {"AuthenticationRequired", "InvalidPassword"}:
            message = "Bluesky could not authenticate the project account. Check its app password."
        elif status == 429:
            message = "Bluesky is rate limiting requests. Try again later."
        else:
            message = "Bluesky did not confirm the request. Try again to check the same post."
        super().__init__(502, message)
        self.code = code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _rpc(
    service: str, method: str, *, token: str = "", body: dict | None = None,
    query: dict | None = None, jpeg: bytes | None = None,
) -> dict:
    url = f"{service}/xrpc/{method}"
    if query:
        url = f"{url}?{urlencode(query)}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if jpeg is not None:
        headers["Content-Type"] = "image/jpeg"
        data = jpeg
    elif body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    try:
        with build_opener(NoRedirect()).open(Request(url, data=data, headers=headers), timeout=10) as response:
            payload = json.load(response)
    except HTTPError as exc:
        with exc:
            try:
                payload = json.load(exc)
                code = payload.get("error", "") if isinstance(payload, dict) else ""
            except (OSError, HTTPException, ValueError):
                code = ""
        raise BlueskyRequestError(exc.code, code) from None
    except (OSError, HTTPException, ValueError):
        raise BlueskyRequestError() from None
    if not isinstance(payload, dict):
        raise BlueskyRequestError()
    return payload


def _bluesky_service(session: dict) -> str:
    document = session.get("didDoc") or {}
    services = document.get("service") if isinstance(document, dict) else None
    for entry in services if isinstance(services, list) else []:
        if isinstance(entry, dict) and entry.get("type") == "AtprotoPersonalDataServer":
            endpoint = entry.get("serviceEndpoint", "")
            if isinstance(endpoint, str) and re.fullmatch(
                r"https://(?:bsky\.social|(?:[a-z0-9-]+\.)+bsky\.network)/?", endpoint
            ):
                return endpoint.rstrip("/")
            raise PublishError(502, "The project account must be hosted by Bluesky.")
    return SERVICE


class BlueskyClient:
    def __init__(self, handle: str, password: str):
        session = _rpc(SERVICE, "com.atproto.server.createSession", body={
            "identifier": handle,
            "password": password,
        })
        self.did = session.get("did")
        self.token = session.get("accessJwt")
        if (
            not isinstance(self.did, str)
            or not re.fullmatch(r"did:plc:[a-z2-7]{24}", self.did)
            or not isinstance(self.token, str)
            or not self.token
        ):
            raise BlueskyRequestError()
        self.service = _bluesky_service(session)

    def get(self, record_key: str) -> dict | None:
        try:
            return _rpc(self.service, "com.atproto.repo.getRecord", token=self.token, query={
                "repo": self.did,
                "collection": COLLECTION,
                "rkey": record_key,
            })
        except BlueskyRequestError as exc:
            if exc.code == "RecordNotFound":
                return None
            raise

    def create(self, record_key: str, record: dict) -> dict:
        return _rpc(self.service, "com.atproto.repo.createRecord", token=self.token, body={
            "repo": self.did,
            "collection": COLLECTION,
            "rkey": record_key,
            "record": record,
            "validate": True,
        })

    def upload_card(self, jpeg: bytes) -> dict:
        response = _rpc(
            self.service, "com.atproto.repo.uploadBlob", token=self.token, jpeg=jpeg
        )
        blob = response.get("blob")
        if (
            not isinstance(blob, dict)
            or blob.get("$type") != "blob"
            or not isinstance(blob.get("ref"), dict)
            or not isinstance(blob["ref"].get("$link"), str)
            or not blob["ref"]["$link"]
            or blob.get("mimeType") != "image/jpeg"
            or blob.get("size") != len(jpeg)
        ):
            raise BlueskyRequestError()
        return blob


def configured_account() -> str | None:
    handle = os.environ.get("BLUESKY_HANDLE", "").strip().lower()
    return handle if handle and os.environ.get("BLUESKY_APP_PASSWORD") else None


def _record_key() -> str:
    value = (time.time_ns() // 1_000 << 10) | secrets.randbits(10)
    return "".join(TID_ALPHABET[(value >> shift) & 31] for shift in range(60, -1, -5))


def _research_link(source: dict) -> str:
    url = source["url"]
    try:
        parts = urlsplit(url)
        valid = parts.scheme == "https" and bool(parts.hostname) and parts.username is None
    except ValueError:
        valid = False
    if not valid:
        raise PublishError(422, "Choose a research source with a valid HTTPS link.")
    return url


def compose_post(draft: dict, text: str, sources: list[int]) -> dict:
    text = text.strip(" \t\r\n")
    if not text or not sources or len(sources) != len(set(sources)):
        raise PublishError(422, "Enter post text and select at least one research source.")
    research = draft["research"]["sources"]
    if any(index < 1 or index > len(research) for index in sources):
        raise PublishError(422, "Choose research sources from this draft.")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PublishError(422, "The post contains invalid Unicode text.") from exc

    text += "\n\nSources:"
    facets = []
    for index in sorted(sources):
        text += " "
        start = len(text.encode("utf-8"))
        text += f"[S{index}]"
        facets.append({
            "index": {"byteStart": start, "byteEnd": len(text.encode("utf-8"))},
            "features": [{
                "$type": "app.bsky.richtext.facet#link",
                "uri": _research_link(research[index - 1]),
            }],
        })
    if len(text) > MAX_POST_LENGTH:
        raise PublishError(422, "The full post must be 300 characters or fewer, including source labels.")
    return {"$type": COLLECTION, "text": text, "langs": ["en"], "facets": facets}


@dataclass(frozen=True)
class PostCard:
    jpeg: bytes
    alt: str
    palette: str

    @classmethod
    def decode(cls, encoded: str, alt: str, palette: str) -> PostCard:
        alt = alt.strip()
        if not alt or len(alt) > 600 or palette not in CARD_PALETTES:
            raise PublishError(422, "The card needs alternative text and a supported palette.")
        if len(encoded) > ((MAX_CARD_BYTES + 2) // 3) * 4:
            raise PublishError(422, "The card must be a JPEG no larger than 1 MB.")
        try:
            jpeg = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise PublishError(422, "The card could not be decoded.") from None
        if (
            len(jpeg) > MAX_CARD_BYTES
            or not jpeg.startswith(b"\xff\xd8\xff")
            or not jpeg.endswith(b"\xff\xd9")
        ):
            raise PublishError(422, "The card must be a JPEG no larger than 1 MB.")
        return cls(jpeg, alt, palette)


def _saved_card(row: dict) -> PostCard | None:
    return PostCard(row["jpeg"], row["alt"], row["palette"]) if row["jpeg"] else None


class PublicationStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("""
            CREATE TABLE IF NOT EXISTS bluesky_publications (
                draft_id TEXT PRIMARY KEY,
                did TEXT NOT NULL,
                account TEXT NOT NULL,
                record_key TEXT NOT NULL,
                record TEXT NOT NULL,
                uri TEXT,
                cid TEXT,
                permalink TEXT,
                UNIQUE (did, record_key)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS bluesky_cards (
                draft_id TEXT PRIMARY KEY,
                jpeg BLOB NOT NULL,
                alt TEXT NOT NULL,
                palette TEXT NOT NULL
            )
        """)
        return connection

    def get(self, draft_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(PUBLICATION_QUERY, (draft_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _next_palette(connection: sqlite3.Connection) -> str:
        count = connection.execute("SELECT COUNT(*) FROM bluesky_cards").fetchone()[0]
        return CARD_PALETTES[count % len(CARD_PALETTES)]

    def next_palette(self) -> str:
        with closing(self._connect()) as connection:
            return self._next_palette(connection)

    def reserve(
        self, draft_id: str, did: str, account: str, record: dict, card: PostCard | None
    ) -> dict:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(PUBLICATION_QUERY, (draft_id,)).fetchone()
            if row is None:
                if card is not None and card.palette != self._next_palette(connection):
                    raise PublishError(409, "The next palette changed. Review the updated preview before publishing.")
                key = _record_key()
                serialized = json.dumps({
                    **record,
                    "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                })
                connection.execute(
                    """INSERT INTO bluesky_publications (draft_id, did, account, record_key, record)
                    VALUES (?, ?, ?, ?, ?)""",
                    (draft_id, did, account, key, serialized),
                )
                if card is not None:
                    connection.execute(
                        "INSERT INTO bluesky_cards (draft_id, jpeg, alt, palette) VALUES (?, ?, ?, ?)",
                        (draft_id, card.jpeg, card.alt, card.palette),
                    )
                row = connection.execute(PUBLICATION_QUERY, (draft_id,)).fetchone()
        return dict(row)

    def save_card_embed(self, draft_id: str, embed: dict) -> dict:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(PUBLICATION_QUERY, (draft_id,)).fetchone()
            record = json.loads(row["record"])
            if "embed" in record and record["embed"] != embed:
                raise PublishError(409, "The uploaded image differs from the saved post.")
            record["embed"] = embed
            connection.execute(
                "UPDATE bluesky_publications SET record = ? WHERE draft_id = ?",
                (json.dumps(record), draft_id),
            )
        return record

    def confirm(self, draft_id: str, uri: str, cid: str, permalink: str) -> dict:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE bluesky_publications SET uri = ?, cid = ?, permalink = ? WHERE draft_id = ?",
                (uri, cid, permalink, draft_id),
            )
        return self.get(draft_id)


def publication_status(row: dict | None) -> dict:
    status = {"configured_account": configured_account(), "state": "ready"}
    if row is not None:
        status.update(
            account=row["account"],
            record=json.loads(row["record"]),
            state="published" if row["uri"] else "pending",
        )
        card = _saved_card(row)
        if card is not None:
            status["card"] = {
                "jpeg": base64.b64encode(card.jpeg).decode("ascii"),
                "alt": card.alt,
                "palette": card.palette,
            }
        if row["uri"]:
            status.update(
                uri=row["uri"],
                cid=row["cid"],
                permalink=row["permalink"],
            )
    return status


def publish_draft(
    store: PublicationStore, draft: dict, account: str, text: str | None,
    sources: list[int], card: PostCard | None = None,
) -> dict:
    if draft.get("language") != "en" or draft.get("status") != "approved":
        raise PublishError(409, "Approve an English draft before publishing.")
    draft_id = draft["id"]
    previous = store.get(draft_id)
    if previous and previous["uri"]:
        return publication_status(previous)
    configured = configured_account()
    if not configured:
        raise PublishError(503, "Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD to publish.")
    if account != configured:
        raise PublishError(409, "The project account changed. Reload and review the post before publishing.")
    if text is None and previous:
        requested = json.loads(previous["record"])
        card = _saved_card(previous)
    else:
        requested = compose_post(draft, text or "", sources)
    client = BlueskyClient(configured, os.environ["BLUESKY_APP_PASSWORD"])
    row = store.reserve(draft_id, client.did, configured, requested, card)
    if row["did"] != client.did:
        raise PublishError(409, "This publishing attempt belongs to a different Bluesky account.")
    if row["uri"]:
        return publication_status(row)
    record = json.loads(row["record"])
    if (
        any(record.get(field) != value for field, value in requested.items())
        or _saved_card(row) != card
    ):
        raise PublishError(409, "A post is pending. Retry the same reviewed preview.")

    key = row["record_key"]
    receipt = client.get(key)
    if receipt is None:
        if card is not None:
            blob = client.upload_card(card.jpeg)
            record = store.save_card_embed(draft_id, {
                "$type": "app.bsky.embed.images",
                "images": [{"image": blob, "alt": card.alt}],
            })
        try:
            receipt = client.create(key, record)
        except BlueskyRequestError:
            receipt = client.get(key)
            if receipt is None:
                raise
    elif card is not None and "embed" not in record:
        record = json.loads(store.get(draft_id)["record"])
    if "value" in receipt and receipt["value"] != record:
        raise PublishError(409, "The Bluesky record differs from the reviewed post.")
    expected_uri = f"at://{client.did}/{COLLECTION}/{key}"
    cid = receipt.get("cid")
    if receipt.get("uri") != expected_uri or not isinstance(cid, str) or not cid:
        raise BlueskyRequestError()
    permalink = f"https://bsky.app/profile/{client.did}/post/{key}"
    return publication_status(store.confirm(draft_id, expected_uri, cid, permalink))
