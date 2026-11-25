"""Search fixed ovalbumin records and render source-grounded assay summaries."""
import json
import re

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from common import DATA


def assay_link(identifier):
    return f"https://www.iedb.org/details_v3.php?id={int(identifier)}&type=assay"


def paper_link(identifier):
    return f"https://pubmed.ncbi.nlm.nih.gov/{int(identifier)}/"


class EvidenceSearch:
    def __init__(self, directory=DATA):
        self.assays = pd.read_csv(directory / "assays.csv").fillna("")
        self.papers = json.loads((directory / "bibliography.json").read_text(encoding="utf-8"))
        terminology = json.loads((directory / "search_terms.json").read_text(encoding="utf-8"))
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), strip_accents="unicode")
        text = [
            " ".join((str(row.structure_id), str(row.bcell_id), row.linear_sequence,
                      row.qualitative_measure, row.assay_names.replace("|", " "),
                      row.host_organism_name, f"Ig{row.antibody_isotype}".replace("IgIg", "Ig"),
                      self.papers[str(row.pubmed_id)]["title"], terminology[str(row.pubmed_id)]))
            for row in self.assays.itertuples()
        ]
        self.matrix = self.vectorizer.fit_transform(text)

    def search(self, question, limit=8):
        text = question.strip()
        if not text or limit < 1:
            return self.assays.iloc[:0].copy()
        explicit = re.search(r"\b(?:epitop[eo]|iedb)\s*[:#-]?\s*(\d+)\b", text, re.I)
        sequence = re.search(r"\b[ACDEFGHIKLMNPQRSTVWY]{8,}\b", text)
        pool = self.assays
        if explicit:
            number = int(explicit[1])
            pool = pool[pool.structure_id.eq(number) | pool.bcell_id.eq(number)]
        elif sequence:
            pool = pool[pool.linear_sequence.eq(sequence[0])]
        if pool.empty:
            return pool.copy()
        text = re.sub(r"\bhumano[s]?\b", "human", text, flags=re.I)
        text = re.sub(r"\bnegativ[oa]s?\b", "negative", text, flags=re.I)
        text = re.sub(r"\bpositiv[oa]s?\b", "positive", text, flags=re.I)
        text = re.sub(r"\banticuerpo[s]?\b", "antibody", text, flags=re.I)
        scores = (self.matrix[pool.index] @ self.vectorizer.transform([text]).T).toarray().ravel()
        ranked = pool.assign(score=scores)
        if not (explicit or sequence):
            ranked = ranked[ranked.score.ge(0.07)]
        ranked = ranked.sort_values(["score", "bcell_id"], ascending=[False, True])
        if not (explicit or sequence):
            # Prefer a mix of sources when many rows repeat the same study vocabulary.
            round_number = ranked.groupby("pubmed_id").cumcount() // 3
            ranked = ranked.assign(round_number=round_number).sort_values("round_number", kind="stable")
        return ranked.head(limit)

    def select_with_model(self, question, hits, model, post=None):
        """Use a local model to focus the answer on listed assay IDs."""
        if hits.empty:
            return hits
        if post is None:
            from requests import post
        allowed = {int(value) for value in hits.bcell_id}
        choices = hits[["bcell_id", "assay_names", "qualitative_measure", "linear_sequence"]]
        instruction = (
            "Choose up to four record IDs relevant to the question from the supplied table. "
            "Return a JSON object with the sole key ids and an array of integers. "
            "Do not include any other data. If all records are comparable, include different outcomes."
        )
        response = post("http://127.0.0.1:11434/api/chat", json={
            "model": model, "stream": False, "format": "json", "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": question + "\n" + choices.to_json(orient="records")},
            ],
        }, timeout=45)
        response.raise_for_status()
        ids = json.loads(response.json()["message"]["content"])["ids"]
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 4
                or any(type(value) is not int or value not in allowed for value in ids)):
            raise ValueError("The local model returned an invalid assay selection")
        return hits[hits.bcell_id.isin(ids)]

    @staticmethod
    def answer(hits):
        if hits.empty:
            return "No matching assay was found in this ovalbumin snapshot."
        summaries = []
        for row in hits.head(4).itertuples():
            method = row.assay_names.replace("|", " / ")
            summaries.append(
                f"{row.qualitative_measure} for **{row.linear_sequence}** in "
                f"{row.host_organism_name}, {method}. "
                f"[IEDB assay {row.bcell_id}]({assay_link(row.bcell_id)}) · "
                f"[PMID {row.pubmed_id}]({paper_link(row.pubmed_id)})"
            )
        return "\n\n".join(summaries)
