"""
spaCy-based Preprocessor for HeidelTime.

A drop-in alternative to `comprehend_preprocessor` that produces the same
``Sentence`` / ``Token`` objects the engine consumes, but using a local spaCy
pipeline instead of AWS Comprehend. This lets the HeidelTime Lambda do its own
NLP preprocessing (no Comprehend call, no upstream `sentences` payload) while
keeping HeidelTime's expected Penn-Treebank POS scheme:

- HeidelTime's rules gate on **Penn Treebank** POS tags (NN, NNP, VBP, JJ, IN, CD...).
- spaCy's ``token.tag_`` is **already Penn Treebank** for English models -> drop-in,
  no UD->Penn remapping (which Comprehend requires and which loses fine tags).

All offsets are **absolute** into the document text, matching what HeidelTime
expects when it computes ``sentence.begin + match_offset``.

The model is configurable via the ``SPACY_MODEL`` environment variable (default
``en_core_web_md``) and loaded once per container for warm reuse. Large documents
are chunked on paragraph/sentence boundaries (never mid-sentence) so a single
huge input cannot exhaust the parser's memory.

License: GPL-3.0 (same as HeidelTime)
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Iterator, List, Optional, Tuple

# Reuse the engine's dataclasses so output is interchangeable with the
# Comprehend preprocessor (the engine imports Sentence/Token from there).
from comprehend_preprocessor import Sentence, Token

# Default model: en_core_web_md is the accuracy/throughput sweet spot for HeidelTime's
# POS needs (same CPU speed as sm, better tagger, no torch dependency). Override with
# SPACY_MODEL (e.g. en_core_web_sm for speed, en_core_web_trf for max accuracy).
_DEFAULT_MODEL = os.environ.get("SPACY_MODEL", "en_core_web_md")

# Components not needed for POS tagging + sentence segmentation.
_DISABLE = ["lemmatizer", "ner"]

# Target maximum characters per spaCy call. Documents longer than this are split
# into contiguous chunks on paragraph/sentence boundaries before processing.
_CHUNK_CHARS = 100_000
# spaCy's hard ceiling per call. Set above the chunk size (not to a huge value) so a
# pathological chunk fails fast instead of attempting a multi-GB parser allocation.
_MAX_LENGTH = 250_000

_PARA_SPLIT = re.compile(r"\n\s*\n")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


@lru_cache(maxsize=2)
def _load_nlp(model: str = _DEFAULT_MODEL):
    import spacy

    nlp = spacy.load(model, disable=_DISABLE)
    nlp.max_length = _MAX_LENGTH
    return nlp


# --- temporal-trigger prefilter ------------------------------------------------
# A sentence with no trigger token is very unlikely to contain a temporal
# expression; skipping it cuts HeidelTime rule-matching work with negligible recall
# loss. HeidelTime processes each sentence independently, so dropping triggerless
# sentences is safe. (Mirrors source-detector's nlp_spacy._TRIGGER verbatim.)
_TRIGGER = re.compile(
    r"""
    \b(
        jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|
        sep(t(ember)?)?|oct(ober)?|nov(ember)?|dec(ember)?|
        mon(day)?|tue(s(day)?)?|wed(nesday)?|thu(r(s(day)?)?)?|fri(day)?|
        sat(urday)?|sun(day)?|
        today|yesterday|tomorrow|now|tonight|currently|recently|
        year|month|week|day|hour|minute|second|decade|century|quarter|season|
        spring|summer|autumn|fall|winter|morning|afternoon|evening|night|noon|midnight|
        last|next|this|coming|past|previous|following|earlier|later|ago|since|until|
        till|during|before|after|between|from|by|over|within|throughout|
        every|each|daily|weekly|monthly|yearly|annually|quarterly|hourly|
        christmas|easter|thanksgiving|halloween|holiday|weekend|
        century|millennium|era|epoch|moment|period|recent|soon|then|when
    )\b
    | \d            # any digit (dates, times, years, "3 days")
    | \b\d{1,2}(st|nd|rd|th)\b
    | [0-9]{1,2}[:/.\-][0-9]{1,2}
    """,
    re.IGNORECASE | re.VERBOSE,
)


def has_temporal_trigger(text: str) -> bool:
    return _TRIGGER.search(text) is not None


def _find_split(text: str, start: int, end: int) -> int:
    """Return the best split offset in ``(start, end]`` that does not break a sentence.

    Prefers a paragraph boundary, then a sentence boundary, then any whitespace, and
    only as a last resort hard-cuts at ``end``. Guarantees forward progress.
    """
    window = text[start:end]
    para = list(_PARA_SPLIT.finditer(window))
    if para:
        return start + para[-1].end()
    sent = list(_SENT_SPLIT.finditer(window))
    if sent:
        return start + sent[-1].end()
    for i in range(len(window) - 1, 0, -1):
        if window[i].isspace():
            return start + i + 1
    return end


def _iter_chunks(text: str, max_chars: int = _CHUNK_CHARS) -> Iterator[Tuple[int, str]]:
    """Yield ``(base_offset, chunk_text)`` covering ``text`` with contiguous slices.

    Splits only on paragraph/sentence boundaries (never mid-sentence in the common
    case), so token character offsets map linearly back to the document via
    ``base_offset``. Short documents yield a single chunk.
    """
    n = len(text)
    if n <= max_chars:
        yield 0, text
        return
    start = 0
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            end = _find_split(text, start, end)
        yield start, text[start:end]
        start = end


def _doc_to_sentences(doc, base: int, start_token_id: int) -> Tuple[List[Sentence], int]:
    """Convert a spaCy ``Doc`` into HeidelTime ``Sentence``/``Token`` objects.

    ``base`` is added to every offset so chunked documents stay in absolute
    coordinates; ``start_token_id`` keeps token ids continuous across chunks.
    """
    sentences: List[Sentence] = []
    token_id = start_token_id
    for sent in doc.sents:
        tokens: List[Token] = []
        for tok in sent:
            if tok.is_space:
                continue
            tokens.append(Token(
                text=tok.text,
                begin=base + tok.idx,
                end=base + tok.idx + len(tok.text),
                pos=tok.tag_,          # Penn Treebank -- HeidelTime's expected scheme
                token_id=token_id,
            ))
            token_id += 1
        sentences.append(Sentence(
            text=sent.text,
            begin=base + sent.start_char,
            end=base + sent.end_char,
            tokens=tokens,
        ))
    return sentences, token_id


def preprocess(
    text: str,
    *,
    use_pos: bool = True,
    split_on_newlines: bool = False,
    prefilter: bool = True,
    model: Optional[str] = None,
) -> List[Sentence]:
    """Preprocess text into HeidelTime sentences with Penn-Treebank POS via spaCy.

    Args:
        text: Input document text.
        use_pos: Accepted for interface parity. spaCy always tags; HeidelTime decides
            whether to use POS via its own ``use_pos`` flag on the engine.
        split_on_newlines: Accepted for interface parity. spaCy uses parser-based
            sentence segmentation (matching the local source-detector path), so this
            flag is not applied here.
        prefilter: Drop sentences with no temporal trigger token (cuts HeidelTime
            rule-matching work). Safe because HeidelTime processes sentences
            independently.
        model: Override the spaCy model name (defaults to ``SPACY_MODEL`` env var).

    Returns:
        List of ``Sentence`` objects with absolute char offsets.
    """
    nlp = _load_nlp(model or _DEFAULT_MODEL)

    sentences: List[Sentence] = []
    token_id = 1
    for base, chunk in _iter_chunks(text):
        if not chunk.strip():
            continue
        doc = nlp(chunk)
        chunk_sents, token_id = _doc_to_sentences(doc, base, token_id)
        sentences.extend(chunk_sents)

    if prefilter:
        sentences = [s for s in sentences if has_temporal_trigger(s.text)]
    return sentences
