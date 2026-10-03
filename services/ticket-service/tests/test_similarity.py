from src import similarity


def test_tokenize_drops_stopwords_and_stems():
    assert similarity.tokenize("The users are crashing on the login pages") == ["user", "crash", "login", "page"]
    assert similarity.tokenize(None) == []


def test_singular_and_plural_forms_match():
    for plural, singular in [("pages", "page"), ("issues", "issue"), ("crashes", "crash"),
                             ("boxes", "box"), ("users", "user"), ("classes", "class")]:
        assert similarity.tokenize(plural) == similarity.tokenize(singular), plural


def test_titles_weigh_more_than_descriptions():
    tokens = similarity.ticket_tokens("Login crash", "safari")
    assert tokens.count("login") == 2 and tokens.count("safari") == 1


def test_rank_orders_by_similarity_and_applies_threshold():
    corpus = [
        ("APM-1", similarity.ticket_tokens("Login page crashes on Safari", None)),
        ("APM-2", similarity.ticket_tokens("Add dark mode to settings", None)),
        ("APM-3", similarity.ticket_tokens("Safari login crash on submit", None)),
    ]
    query = similarity.ticket_tokens("Safari login crash", None)
    ranked = similarity.rank(query, corpus, limit=5, min_score=0.2)
    assert [k for k, _ in ranked][:2] in (["APM-3", "APM-1"], ["APM-1", "APM-3"])
    assert "APM-2" not in [k for k, _ in ranked]
    assert all(0 < score <= 1 for _, score in ranked)


def test_rank_handles_empty_inputs():
    assert similarity.rank([], [("APM-1", ["x"])]) == []
    assert similarity.rank(["x"], []) == []
