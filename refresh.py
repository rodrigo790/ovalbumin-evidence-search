"""Create a new, dated snapshot of published ovalbumin binding assays."""
import argparse
import datetime
import json
from pathlib import Path

import pandas as pd
import requests

IEDB = "https://query-api.iedb.org/bcell_search"
PUBMED = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PMIDS = ("34818647", "17236828", "14600204")
FIELDS = (
    "bcell_id", "structure_id", "linear_sequence", "structure_type", "pubmed_id",
    "qualitative_measure", "assay_names", "host_organism_name",
    "antibody_isotype", "parent_source_antigen_iri",
)


def refresh(output: Path):
    output.mkdir(exist_ok=True, parents=True)
    with requests.Session() as session:
        rows = []
        for offset in range(0, 2000, 500):
            response = session.get(IEDB, params={
                "select": ",".join(FIELDS), "parent_source_antigen_iri": "eq.UNIPROT:P01012",
                "pubmed_id": f"in.({','.join(PMIDS)})", "structure_type": "eq.Linear peptide",
                "order": "bcell_id.asc", "limit": "500", "offset": offset,
            }, timeout=35)
            response.raise_for_status()
            page = response.json()
            rows.extend(page)
            if len(page) < 500:
                break
        else:
            raise ValueError("Snapshot exceeded the expected record limit")
        response = session.get(PUBMED, params={
            "query": " OR ".join(f"(EXT_ID:{p} AND SRC:MED)" for p in PMIDS),
            "format": "json",
        }, timeout=35)
        response.raise_for_status()

    papers = {
        article["pmid"]: {
            "title": article["title"], "authors": article["authorString"], "year": article["pubYear"]
        }
        for article in response.json()["resultList"]["result"] if article.get("pmid") in PMIDS
    }
    if set(papers) != set(PMIDS) or not rows:
        raise ValueError("The snapshot is incomplete")
    assays = pd.DataFrame(rows)
    if (not assays.bcell_id.is_unique or
            set(assays.parent_source_antigen_iri) != {"UNIPROT:P01012"}):
        raise ValueError("Unexpected assay rows")
    assays.to_csv(output / "assays.csv", index=False)
    (output / "bibliography.json").write_text(json.dumps(papers, indent=2) + "\n", encoding="utf-8")
    (output / "retrieval.json").write_text(json.dumps({
        "retrieved_utc": datetime.datetime.now(datetime.UTC).date().isoformat(),
        "iedb": IEDB, "pubmed_metadata_via": PUBMED, "pmids": PMIDS,
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="New output folder for the snapshot")
    refresh(parser.parse_args().output)
