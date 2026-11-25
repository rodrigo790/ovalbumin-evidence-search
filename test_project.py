import json
from types import SimpleNamespace
import unittest

from search import EvidenceSearch
from common import DATA


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = EvidenceSearch()

    def test_expected_search_examples_and_grounding(self):
        cases = json.loads((DATA / "evaluation.json").read_text())
        for case in cases:
            with self.subTest(case=case):
                hits = self.engine.search(case["question"])
                if "assay" in case:
                    self.assertIn(case["assay"], set(hits.bcell_id))
                elif "pmid" in case:
                    self.assertIn(case["pmid"], set(hits.pubmed_id))
                else:
                    self.assertTrue(hits.empty)
                summary = self.engine.answer(hits)
                for hit in hits.head(4).itertuples():
                    self.assertIn(f"id={hit.bcell_id}&type=assay", summary)
                    self.assertIn(f"pubmed.ncbi.nlm.nih.gov/{hit.pubmed_id}", summary)

    def test_model_cannot_add_new_ids(self):
        hits = self.engine.search("IEDB 17678705")

        def response(ids):
            return lambda *args, **kwargs: SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"message": {"content": json.dumps({"ids": ids})}},
            )

        approved = self.engine.select_with_model(
            "Summarize", hits, "test-model", post=response([17678705])
        )
        self.assertEqual(list(approved.bcell_id), [17678705])
        with self.assertRaises(ValueError):
            self.engine.select_with_model("Summarize", hits, "test-model", post=response([999]))
