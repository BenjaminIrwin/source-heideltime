"""
HeidelTime - Temporal Expression Extraction Engine

A Python port of the HeidelTime temporal tagger with TimeML value normalization.
This package is licensed under GPL-3.0 (same as the original HeidelTime).

This package provides:
- HeidelTimeEngine: Main extraction engine
- HeidelTimeLoader: Resource file loader
- Timex: Dataclass for temporal expression annotations
- Sentence, Token: NLP dataclasses for pre-processed input

Usage (with automatic Comprehend preprocessing):
    from heideltime import HeidelTimeEngine
    
    engine = HeidelTimeEngine(
        language_dir="resources/english",
        doc_type="news",
        dct="2024-01-15",
    )
    
    timexes = engine.extract("The meeting is on January 15, 2024.")
    for timex in timexes:
        print(f"{timex.text} -> {timex.value}")

Usage (with pre-processed NLP data):
    from heideltime import HeidelTimeEngine, Sentence, Token
    
    # Pre-process upstream (e.g., shared Comprehend call)
    sentences = [
        Sentence(
            text="The meeting is on January 15, 2024.",
            begin=0,
            end=36,
            tokens=[
                Token(text="The", begin=0, end=3, pos="DT", token_id=1),
                Token(text="meeting", begin=4, end=11, pos="NN", token_id=2),
                # ... more tokens
            ]
        )
    ]
    
    # Pass pre-processed data (no Comprehend call)
    timexes = engine.extract("", sentences=sentences)
"""

from heideltime_engine import HeidelTimeEngine, Timex
from heideltime_loader import HeidelTimeLoader, NormalizationManager, RePatternManager
from comprehend_preprocessor import Sentence, Token, preprocess

__all__ = [
    "HeidelTimeEngine",
    "HeidelTimeLoader",
    "Timex",
    "Sentence",
    "Token",
    "preprocess",
    "NormalizationManager",
    "RePatternManager",
]

__version__ = "0.1.0"
__license__ = "GPL-3.0"
