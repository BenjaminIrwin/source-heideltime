"""
AWS Comprehend-based Preprocessor for HeidelTime

This module provides tokenization, sentence segmentation, and POS tagging
using AWS Comprehend.

License: GPL-3.0
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

import boto3


@dataclass
class Token:
    """A token with text, character offsets, POS tag, and ID."""
    text: str
    begin: int
    end: int
    pos: str
    token_id: int


@dataclass
class Sentence:
    """A sentence with text, character offsets, and tokens."""
    text: str
    begin: int
    end: int
    tokens: List[Token]


# AWS Comprehend Universal Dependencies → Penn Treebank tag mapping
# HeidelTime rules use Penn Treebank tags (NN, VBP, JJ, etc.)
# Comprehend uses coarser Universal Dependencies tags
UD_TO_PENN = {
    # Nouns
    "NOUN": "NN",      # Common noun → singular noun (conservative)
    "PROPN": "NNP",    # Proper noun
    # Verbs
    "VERB": "VB",      # Verb → base form (will match VB* patterns loosely)
    "AUX": "MD",       # Auxiliary/modal → modal (covers "may", "can", etc.)
    # Adjectives/Adverbs
    "ADJ": "JJ",       # Adjective
    "ADV": "RB",       # Adverb
    # Determiners/Pronouns
    "DET": "DT",       # Determiner
    "PRON": "PRP",     # Pronoun
    # Prepositions/Conjunctions
    "ADP": "IN",       # Adposition (preposition)
    "SCONJ": "IN",     # Subordinating conjunction
    "CONJ": "CC",      # Coordinating conjunction
    "CCONJ": "CC",     # Coordinating conjunction (alternate tag)
    # Other
    "NUM": "CD",       # Number → cardinal number
    "PART": "RP",      # Particle
    "INTJ": "UH",      # Interjection
    "PUNCT": ".",      # Punctuation
    "SYM": "SYM",      # Symbol
    "X": "XX",         # Other/unknown
    "O": "XX",         # Outside/other
}


def _map_pos_tag(ud_tag: str) -> str:
    """Map Universal Dependencies tag to Penn Treebank tag."""
    return UD_TO_PENN.get(ud_tag, ud_tag)


def _split_sentences(text: str) -> List[tuple[str, int, int]]:
    """
    Simple rule-based sentence splitting.
    
    Returns list of (sentence_text, start_offset, end_offset).
    """
    # Pattern for sentence boundaries: . ! ? followed by space and capital or end
    # Simple rule-based sentence splitting
    sentence_pattern = re.compile(
        r'(?<=[.!?])\s+(?=[A-Z"])|(?<=[.!?])$',
        re.MULTILINE
    )
    
    sentences = []
    last_end = 0
    
    for match in sentence_pattern.finditer(text):
        sent_text = text[last_end:match.start() + 1].strip()
        if sent_text:
            # Find actual start (skip leading whitespace)
            actual_start = last_end
            while actual_start < len(text) and text[actual_start].isspace():
                actual_start += 1
            sentences.append((sent_text, actual_start, match.start() + 1))
        last_end = match.end()
    
    # Don't forget the last sentence
    remaining = text[last_end:].strip()
    if remaining:
        actual_start = last_end
        while actual_start < len(text) and text[actual_start].isspace():
            actual_start += 1
        sentences.append((remaining, actual_start, len(text)))
    
    # If no sentences found, treat whole text as one sentence
    if not sentences and text.strip():
        sentences.append((text.strip(), 0, len(text)))
    
    return sentences


class ComprehendPreprocessor:
    """
    Preprocessor using AWS Comprehend for POS tagging.
    
    Falls back to simple tokenization if Comprehend is unavailable or
    if use_pos=False.
    """
    
    def __init__(self, region_name: Optional[str] = None):
        """
        Initialize the Comprehend client.
        
        Args:
            region_name: AWS region. If None, uses default from environment.
        """
        self._client = None
        self._region = region_name
    
    @property
    def client(self):
        """Lazy initialization of Comprehend client."""
        if self._client is None:
            self._client = boto3.client(
                'comprehend',
                region_name=self._region
            )
        return self._client
    
    def preprocess(
        self,
        text: str,
        *,
        use_pos: bool = True,
        split_on_newlines: bool = False,
    ) -> List[Sentence]:
        """
        Preprocess text into sentences with tokens and POS tags.
        
        Args:
            text: Input text
            use_pos: Whether to get POS tags from Comprehend
            split_on_newlines: Treat newlines as sentence boundaries
            
        Returns:
            List of Sentence objects with tokens
        """
        sentences: List[Sentence] = []
        token_id = 1
        
        if split_on_newlines:
            # Process line by line
            offset = 0
            for raw_line in text.splitlines(keepends=True):
                line_text = raw_line.rstrip("\r\n")
                if line_text:
                    tokens, token_id = self._tokenize_with_pos(
                        line_text, offset, token_id, use_pos
                    )
                    sentences.append(Sentence(
                        text=line_text,
                        begin=offset,
                        end=offset + len(line_text),
                        tokens=tokens,
                    ))
                offset += len(raw_line)
        else:
            # Split into sentences, then tokenize each
            for sent_text, sent_start, sent_end in _split_sentences(text):
                tokens, token_id = self._tokenize_with_pos(
                    sent_text, sent_start, token_id, use_pos
                )
                sentences.append(Sentence(
                    text=sent_text,
                    begin=sent_start,
                    end=sent_end,
                    tokens=tokens,
                ))
        
        return sentences
    
    def _tokenize_with_pos(
        self,
        text: str,
        offset: int,
        start_token_id: int,
        use_pos: bool,
    ) -> tuple[List[Token], int]:
        """
        Tokenize text and optionally get POS tags.
        
        Returns (tokens, next_token_id).
        """
        if not text.strip():
            return [], start_token_id
        
        if use_pos:
            return self._comprehend_tokenize(text, offset, start_token_id)
        else:
            return self._simple_tokenize(text, offset, start_token_id)
    
    def _comprehend_tokenize(
        self,
        text: str,
        offset: int,
        start_token_id: int,
    ) -> tuple[List[Token], int]:
        """
        Tokenize using AWS Comprehend detect_syntax.
        
        Comprehend returns word tokens with POS tags and character offsets.
        """
        try:
            # Comprehend has a 5000 byte limit per request
            if len(text.encode('utf-8')) > 5000:
                return self._chunked_comprehend_tokenize(text, offset, start_token_id)
            
            response = self.client.detect_syntax(
                Text=text,
                LanguageCode='en'
            )
            
            tokens: List[Token] = []
            token_id = start_token_id
            
            for syntax_token in response['SyntaxTokens']:
                # Get Penn Treebank tag from Universal Dependencies tag
                ud_tag = syntax_token['PartOfSpeech']['Tag']
                penn_tag = _map_pos_tag(ud_tag)
                
                begin = syntax_token['BeginOffset'] + offset
                end = syntax_token['EndOffset'] + offset
                
                tokens.append(Token(
                    text=syntax_token['Text'],
                    begin=begin,
                    end=end,
                    pos=penn_tag,
                    token_id=token_id,
                ))
                token_id += 1
            
            return tokens, token_id
            
        except Exception as e:
            # Fall back to simple tokenization on error
            print(f"Comprehend error, falling back to simple tokenization: {e}")
            return self._simple_tokenize(text, offset, start_token_id)
    
    def _chunked_comprehend_tokenize(
        self,
        text: str,
        offset: int,
        start_token_id: int,
    ) -> tuple[List[Token], int]:
        """Handle texts longer than Comprehend's 5000 byte limit."""
        all_tokens: List[Token] = []
        token_id = start_token_id
        
        # Split on whitespace, keeping track of positions
        chunk = ""
        chunk_start = 0
        pos = 0
        
        for i, char in enumerate(text):
            if char.isspace() and len((chunk + char).encode('utf-8')) > 4500:
                # Process current chunk
                if chunk.strip():
                    tokens, token_id = self._comprehend_tokenize(
                        chunk, offset + chunk_start, token_id
                    )
                    all_tokens.extend(tokens)
                chunk = ""
                chunk_start = i + 1
            else:
                chunk += char
        
        # Process remaining chunk
        if chunk.strip():
            tokens, token_id = self._comprehend_tokenize(
                chunk, offset + chunk_start, token_id
            )
            all_tokens.extend(tokens)
        
        return all_tokens, token_id
    
    def _simple_tokenize(
        self,
        text: str,
        offset: int,
        start_token_id: int,
    ) -> tuple[List[Token], int]:
        """
        Simple whitespace/punctuation tokenization without POS tags.
        
        Used when use_pos=False or as fallback.
        """
        # Pattern to match words and punctuation separately
        token_pattern = re.compile(r'\S+')
        
        tokens: List[Token] = []
        token_id = start_token_id
        
        for match in token_pattern.finditer(text):
            tokens.append(Token(
                text=match.group(),
                begin=match.start() + offset,
                end=match.end() + offset,
                pos="",  # No POS tag
                token_id=token_id,
            ))
            token_id += 1
        
        return tokens, token_id


# Module-level singleton for reuse across invocations
_preprocessor: Optional[ComprehendPreprocessor] = None


def get_preprocessor(region_name: Optional[str] = None) -> ComprehendPreprocessor:
    """Get or create the Comprehend preprocessor singleton."""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = ComprehendPreprocessor(region_name=region_name)
    return _preprocessor


def preprocess(
    text: str,
    *,
    use_pos: bool = True,
    split_on_newlines: bool = False,
    region_name: Optional[str] = None,
) -> List[Sentence]:
    """
    Preprocess text using AWS Comprehend.
    
    Preprocess text using AWS Comprehend for tokenization and POS tagging.
    
    Args:
        text: Input text
        use_pos: Whether to get POS tags
        split_on_newlines: Treat newlines as sentence boundaries
        region_name: AWS region for Comprehend
        
    Returns:
        List of Sentence objects
    """
    preprocessor = get_preprocessor(region_name)
    return preprocessor.preprocess(
        text,
        use_pos=use_pos,
        split_on_newlines=split_on_newlines,
    )
