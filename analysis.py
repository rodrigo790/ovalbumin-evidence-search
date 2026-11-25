"""Run the tracked retrieval evaluation against a frozen corpus."""
import json

import pandas as pd

from common import DATA, RESULTS, save_summary
from search import EvidenceSearch


def main():
    engine = EvidenceSearch()
    queries = json.loads((DATA / "evaluation.json").read_text(encoding="utf-8"))
    rows = []
    for query in queries:
        hits = engine.search(query["question"], limit=8)
        if query.get("assay"):
            passed = int(query["assay"]) in set(hits.bcell_id)
        elif query.get("pmid"):
            passed = int(query["pmid"]) in set(hits.pubmed_id)
        else:
            passed = hits.empty
        answer = engine.answer(hits)
        reported = [row for row in hits.head(4).itertuples()]
        grounded = all(f"IEDB assay {row.bcell_id}" in answer and f"PMID {row.pubmed_id}" in answer
                       for row in reported)
        rows.append({**query, "hits": len(hits), "retrieval_pass": passed, "citations_pass": grounded})
    RESULTS.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(RESULTS / "evaluation.csv", index=False)
    save_summary({"assay_records": len(engine.assays), "studies": len(engine.papers),
                  "evaluation_queries": len(rows), "retrieval_passes": sum(r["retrieval_pass"] for r in rows),
                  "citation_passes": sum(r["citations_pass"] for r in rows)})


if __name__ == "__main__":
    main()
