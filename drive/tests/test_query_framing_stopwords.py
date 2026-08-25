"""A natural-language request must not rank on how it was phrased.

Subject overlap is rarity-weighted, so an uncommon framing word carries a *high*
weight: "regarding" made "a distillation of the literature regarding knowledge
transfer" score as a match for "i need dataset regarding forest fire and
economic changes". The same raw words also reached the external providers, so
OpenAlex returned that paper as a forest-fire dataset.
"""

from scripts.research_data_mcp.procurement_search import (
    PROCUREMENT_QUERY_STOPWORDS,
    query_topic_tokens,
)
from scripts.research_data_mcp.semantic_index import STOPWORDS, _tokenize

FRAMING = (
    "need",
    "want",
    "looking",
    "regarding",
    "about",
    "concerning",
    "related",
    "please",
    "show",
    "give",
    "seeking",
)

SUBJECT_BEARING = ("fire", "forest", "economic", "change", "changes", "new")
# "time" and "series" are deliberately dropped on the provider path only: there
# they describe the shape of a request, not its subject.
SEMANTIC_ONLY_SUBJECT = ("time", "series")


def test_request_framing_never_becomes_a_subject_token():
    query = "i need dataset regarding forest fire and economic changes"
    assert _tokenize(query) == ["forest", "fire", "economic", "changes"]
    assert sorted(query_topic_tokens(query)) == [
        "changes",
        "economic",
        "fire",
        "forest",
    ]


def test_framing_words_are_filtered_on_both_paths():
    """Parity, not duplication: a word dropped locally must also be dropped
    before it reaches a provider, or the two layers disagree about the query."""
    for word in FRAMING:
        assert word in STOPWORDS, f"{word} still scores in subject overlap"
        assert word in PROCUREMENT_QUERY_STOPWORDS, f"{word} still sent to providers"


def test_subject_words_are_not_over_filtered():
    for word in SUBJECT_BEARING:
        assert word not in STOPWORDS, f"{word} carries subject meaning"
        assert word not in PROCUREMENT_QUERY_STOPWORDS, f"{word} carries subject meaning"


def test_shape_words_stay_available_to_local_scoring():
    for word in SEMANTIC_ONLY_SUBJECT:
        assert word not in STOPWORDS, f"{word} still describes a local dataset"


def test_phrasing_only_match_shares_no_tokens():
    query = "i need dataset regarding forest fire and economic changes"
    noise = (
        "Putting knowledge to use: A distillation of the literature regarding "
        "knowledge transfer and change"
    )
    assert not set(_tokenize(query)) & set(_tokenize(noise))
