"""
similarity.py – Duplicate / related-ticket detection.

TF-IDF + cosine similarity over ticket titles and descriptions. Pure Python,
no LLM or API key needed, deterministic, and fast enough for thousands of
tickets. Titles are weighted double because they carry most of the signal.
"""
import math
import re
from collections import Counter
from typing import Iterable, List, Optional, Tuple

# Above this score a newly created ticket is flagged as a possible duplicate.
DUPLICATE_THRESHOLD = 0.35

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "of", "on", "in", "to", "for",
    "with", "without", "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "it",
    "its", "this", "that", "these", "those", "we", "our", "you", "your", "they", "their", "i",
    "me", "my", "he", "she", "them", "not", "no", "can", "cannot", "can't", "should", "would",
    "could", "will", "when", "after", "before", "while", "so", "do", "does", "did", "has", "have",
    "had", "get", "gets", "got", "into", "out", "up", "down", "all", "any", "some", "more", "very",
    "also", "just", "than", "there", "here", "about", "please", "need", "needs", "want", "make",
}

_SUFFIXES = ("ing", "edly", "ed", "es", "s")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text: Optional[str]) -> List[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [_stem(w) for w in words if len(w) > 1 and w not in _STOPWORDS]


def ticket_tokens(title: str, description: Optional[str]) -> List[str]:
    return tokenize(title) * 2 + tokenize(description)


def rank(
    query: List[str],
    corpus: Iterable[Tuple[str, List[str]]],
    limit: int = 5,
    min_score: float = 0.2,
) -> List[Tuple[str, float]]:
    """Return [(key, score)] for corpus entries most similar to the query tokens."""
    corpus = [(k, toks) for k, toks in corpus if toks]
    if not query or not corpus:
        return []

    df: Counter = Counter()
    for _, toks in corpus:
        df.update(set(toks))
    df.update(set(query))
    n_docs = len(corpus) + 1
    idf = {w: math.log((n_docs + 1) / (c + 1)) + 1 for w, c in df.items()}

    def vector(tokens: List[str]):
        tf = Counter(tokens)
        vec = {w: (1 + math.log(c)) * idf[w] for w, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return vec, norm

    q_vec, q_norm = vector(query)
    scored = []
    for key, toks in corpus:
        d_vec, d_norm = vector(toks)
        dot = sum(weight * d_vec.get(w, 0.0) for w, weight in q_vec.items())
        score = dot / (q_norm * d_norm)
        if score >= min_score:
            scored.append((key, round(score, 3)))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored[:limit]
