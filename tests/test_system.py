from __future__ import annotations

import json
import os
import unittest

from fitness_rag.config import COLLECTION_NAME, DB_PATH, METRICS_PATH
from fitness_rag.data import (
    create_or_load_split,
    load_records,
    normalized_rumor,
    split_diagnostics,
)


class FinalSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records()
        cls.train, cls.test = create_or_load_split(cls.records)

    def test_dataset_and_split_are_disjoint(self):
        self.assertEqual(len(self.records), 3000)
        self.assertEqual(len(self.train), 2700)
        self.assertEqual(len(self.test), 300)
        self.assertFalse(set(self.train).intersection(self.test))
        diagnostics = split_diagnostics(self.records, self.train, self.test)
        self.assertEqual(diagnostics["covered_record_count"], 3000)
        self.assertEqual(diagnostics["normalized_rumor_overlap_count"], 0)

    def test_no_normalized_rumor_crosses_the_split(self):
        train_rumors = {
            normalized_rumor(self.records[index]) for index in self.train
        }
        test_rumors = {normalized_rumor(self.records[index]) for index in self.test}
        self.assertFalse(train_rumors.intersection(test_rumors))

    @unittest.skipUnless(DB_PATH.exists(), "Build the local Chroma index first")
    def test_final_collection_count(self):
        import chromadb

        client = chromadb.PersistentClient(path=str(DB_PATH))
        collection = client.get_collection(COLLECTION_NAME)
        self.assertEqual(collection.count(), 2700)
        metadata = collection.get(include=["metadatas"])["metadatas"]
        indexed = {int(item["dataset_index"]) for item in metadata}
        self.assertEqual(indexed, set(self.train))
        self.assertFalse(indexed.intersection(self.test))

    def test_metrics_match_final_collection(self):
        metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(metrics["implementation"]["collection_records"], 2700)
        self.assertEqual(metrics["evaluation_design"]["held_out_test_records"], 300)
        self.assertEqual(metrics["evaluation_design"]["split_version"], 2)
        self.assertEqual(
            metrics["evaluation_design"]["leakage_checks"][
                "normalized_rumor_overlap_count"
            ],
            0,
        )

    @unittest.skipUnless(DB_PATH.exists(), "Build the local Chroma index first")
    def test_analysis_returns_three_ranked_records(self):
        from fitness_rag.service import RagService

        os.environ.pop("DEEPSEEK_API_KEY", None)
        service = RagService()
        result = service.analyze(
            "Deep squats always destroy your knees, so your knees must never pass your toes."
        )
        self.assertEqual(result["generation_mode"], "extractive")
        self.assertEqual(result["verdict"], "Related synthetic rebuttal retrieved")
        self.assertEqual(len(result["evidence"]), 3)
        self.assertEqual([item["rank"] for item in result["evidence"]], [1, 2, 3])
        self.assertGreaterEqual(
            result["evidence"][0]["similarity"],
            result["evidence"][1]["similarity"],
        )


if __name__ == "__main__":
    unittest.main()
