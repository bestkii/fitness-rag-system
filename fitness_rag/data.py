from __future__ import annotations

import json
import hashlib
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from sklearn.model_selection import train_test_split

from .config import DATASET_PATH, RANDOM_SEED, SPLIT_PATH, SPLIT_VERSION, TEST_SIZE


def load_records(path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            item = json.loads(line)
            if "_meta" in item:
                continue
            required = {"topics", "expert", "rumor", "truth"}
            missing = required.difference(item)
            if missing:
                raise ValueError(f"Line {line_number} is missing {sorted(missing)}")
            item["_source_line"] = line_number
            records.append(item)
    return records


def topic_pair(record: dict[str, Any]) -> str:
    return "|".join(sorted(record["topics"]))


def normalized_rumor(record: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", record["rumor"]).strip().casefold()


def records_fingerprint(records: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        stable_record = {key: value for key, value in record.items() if key != "_source_line"}
        digest.update(
            json.dumps(
                stable_record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def split_diagnostics(
    records: list[dict[str, Any]],
    train_indices: list[int],
    test_indices: list[int],
) -> dict[str, Any]:
    train = set(train_indices)
    test = set(test_indices)
    train_rumors = {normalized_rumor(records[index]) for index in train}
    test_rumors = {normalized_rumor(records[index]) for index in test}
    return {
        "train_count": len(train_indices),
        "test_count": len(test_indices),
        "index_overlap_count": len(train.intersection(test)),
        "covered_record_count": len(train.union(test)),
        "normalized_rumor_overlap_count": len(train_rumors.intersection(test_rumors)),
    }


def validate_split(
    records: list[dict[str, Any]],
    train_indices: list[int],
    test_indices: list[int],
) -> dict[str, Any]:
    diagnostics = split_diagnostics(records, train_indices, test_indices)
    expected_train = len(records) - TEST_SIZE
    if diagnostics["train_count"] != expected_train:
        raise ValueError(f"Expected {expected_train} training records.")
    if diagnostics["test_count"] != TEST_SIZE:
        raise ValueError(f"Expected {TEST_SIZE} held-out records.")
    if diagnostics["index_overlap_count"]:
        raise ValueError("Train and test indices overlap.")
    if diagnostics["covered_record_count"] != len(records):
        raise ValueError("Train and test indices do not cover the dataset exactly once.")
    if diagnostics["normalized_rumor_overlap_count"]:
        raise ValueError("Normalized rumor text crosses the train/test boundary.")
    return diagnostics


def _repair_normalized_rumor_overlap(
    records: list[dict[str, Any]],
    train_indices: list[int],
    test_indices: list[int],
) -> tuple[list[int], list[int]]:
    """Keep exact normalized-rumor groups on one side without changing strata sizes."""
    train = set(train_indices)
    test = set(test_indices)
    groups: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        groups.setdefault(normalized_rumor(record), []).append(index)

    rng = random.Random(RANDOM_SEED)
    for group_key in sorted(groups):
        group = groups[group_key]
        train_members = train.intersection(group)
        test_members = test.intersection(group)
        if not train_members or not test_members:
            continue
        labels = {topic_pair(records[index]) for index in group}
        if len(labels) != 1:
            raise ValueError("A duplicate rumor group spans multiple topic-pair labels.")
        label = labels.pop()

        # Put the duplicate group in training so evaluation does not repeat a query.
        moved_to_train = sorted(test_members)
        test.difference_update(moved_to_train)
        train.update(moved_to_train)

        candidates = [
            index
            for index in train
            if topic_pair(records[index]) == label
            and len(groups[normalized_rumor(records[index])]) == 1
        ]
        rng.shuffle(candidates)
        replacements = candidates[: len(moved_to_train)]
        if len(replacements) != len(moved_to_train):
            raise ValueError("Could not repair the split while preserving stratum size.")
        train.difference_update(replacements)
        test.update(replacements)

    return sorted(train), sorted(test)


def create_or_load_split(
    records: list[dict[str, Any]],
    split_path: Path = SPLIT_PATH,
) -> tuple[list[int], list[int]]:
    fingerprint = records_fingerprint(records)
    if split_path.exists():
        split = json.loads(split_path.read_text(encoding="utf-8"))
        if (
            split.get("split_version") == SPLIT_VERSION
            and split.get("record_count") == len(records)
            and split.get("records_sha256") == fingerprint
        ):
            train_indices = split["train_indices"]
            test_indices = split["test_indices"]
            validate_split(records, train_indices, test_indices)
            return train_indices, test_indices

    indices = list(range(len(records)))
    labels = [topic_pair(record) for record in records]
    train_indices, test_indices = train_test_split(
        indices,
        test_size=TEST_SIZE,
        random_state=RANDOM_SEED,
        stratify=labels,
    )
    train_indices = sorted(train_indices)
    test_indices = sorted(test_indices)
    train_indices, test_indices = _repair_normalized_rumor_overlap(
        records, train_indices, test_indices
    )
    diagnostics = validate_split(records, train_indices, test_indices)
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(
        json.dumps(
            {
                "split_version": SPLIT_VERSION,
                "record_count": len(records),
                "records_sha256": fingerprint,
                "random_seed": RANDOM_SEED,
                "strategy": (
                    "stratified by unordered topic pair; normalized-rumor groups "
                    "kept on one side"
                ),
                "train_count": len(train_indices),
                "test_count": len(test_indices),
                "train_indices": train_indices,
                "test_indices": test_indices,
                "topic_pair_counts": Counter(labels),
                "leakage_checks": diagnostics,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return train_indices, test_indices


def document_text(record: dict[str, Any]) -> str:
    return (
        f"Claim pattern: {record['rumor']}\n"
        f"Scientific evidence: {record['truth']}"
    )
