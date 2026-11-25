"""Streamlit front end for an offline ovalbumin evidence index."""
import requests
import streamlit as st

from search import EvidenceSearch, assay_link, paper_link

st.set_page_config(page_title="Ovalbumin Evidence Search", page_icon="🔎", layout="wide")


@st.cache_resource
def load_index():
    return EvidenceSearch()


search = load_index()
st.title("Ovalbumin evidence search")
st.caption(f"Gallus gallus · UniProt P01012 · {len(search.assays):,} curated IEDB assay records")
question = st.text_input(
    "Search by evidence ID, peptide or assay description",
    placeholder="Example: What evidence exists for epitope 181380?",
    max_chars=280,
)
examples = st.pills("Examples", ["IEDB 17678705", "Negative western blot", "LKISQAVHAAHAEIN"])
question = question or examples
with st.sidebar:
    st.header("Summary")
    local = st.toggle("Use a local Ollama model")
    model = st.text_input("Installed model", value="qwen2.5:1.5b", disabled=not local)
    st.caption("The optional model selects assay IDs from the retrieved records.")
if question:
    hits = search.search(question)
    narrative = hits
    if local and not hits.empty:
        try:
            narrative = search.select_with_model(question, hits, model)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            st.info("Local model unavailable. Showing the retrieved evidence and its citations.")
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("Assay summary")
        st.markdown(search.answer(narrative))
    with right:
        st.subheader("Sources")
        for row in hits.itertuples():
            st.markdown(
                f"- [Assay {row.bcell_id}]({assay_link(row.bcell_id)}) · "
                f"[PMID {row.pubmed_id}]({paper_link(row.pubmed_id)}) · {row.qualitative_measure}"
            )
else:
    st.write("Choose an example or type a question to review reported binding outcomes.")
