"""
AWS Lambda Handler for HeidelTime Temporal Expression Extraction

This module provides an HTTP API endpoint for temporal expression extraction
using HeidelTime. Uses AWS Comprehend for NLP preprocessing.

License: GPL-3.0 (same as HeidelTime)
"""

import json
import os
from typing import Any, Dict, List, Optional

from comprehend_preprocessor import Sentence, Token

# Initialize the engine lazily to avoid cold start overhead on unused imports
_ENGINE_CACHE: Dict[str, Any] = {}


def get_engine(
    language: str = "english",
    doc_type: str = "news",
    dct: Optional[str] = None,
    resolve_with_dct: bool = True,
    find_dates: bool = True,
    find_times: bool = True,
    find_durations: bool = True,
    find_sets: bool = True,
    find_temponyms: bool = False,
    use_pos: bool = True,
    split_on_newlines: bool = False,
):
    """Get or create a HeidelTimeEngine instance with the given configuration."""
    from heideltime_engine import HeidelTimeEngine

    # Create a cache key from the configuration
    cache_key = f"{language}:{doc_type}:{find_dates}:{find_times}:{find_durations}:{find_sets}:{find_temponyms}:{use_pos}:{split_on_newlines}"

    if cache_key not in _ENGINE_CACHE:
        # Determine the resources directory
        resources_dir = os.environ.get("HEIDELTIME_RESOURCES", "/var/task/resources")
        language_dir = os.path.join(resources_dir, language)

        _ENGINE_CACHE[cache_key] = HeidelTimeEngine(
            language_dir=language_dir,
            doc_type=doc_type,
            dct=dct,
            resolve_with_dct=resolve_with_dct,
            find_dates=find_dates,
            find_times=find_times,
            find_durations=find_durations,
            find_sets=find_sets,
            find_temponyms=find_temponyms,
            use_pos=use_pos,
            split_on_newlines=split_on_newlines,
        )

    # Update DCT on cached engine if provided
    engine = _ENGINE_CACHE[cache_key]
    engine.dct = dct
    engine.resolve_with_dct = resolve_with_dct
    return engine


def timex_to_dict(timex) -> Dict[str, Any]:
    """Convert a Timex object to a JSON-serializable dictionary."""
    return {
        "type": timex.timex_type,
        "text": timex.text,
        "value": timex.value,
        "begin": timex.begin,
        "end": timex.end,
        "quant": timex.quant if timex.quant else None,
        "freq": timex.freq if timex.freq else None,
        "mod": timex.mod if timex.mod else None,
        "timex_id": timex.timex_id,
        "rule": timex.rule,
    }


def parse_sentences(sentences_data: List[Dict]) -> List[Sentence]:
    """Parse sentence data from JSON into Sentence objects."""
    sentences = []
    for sent_data in sentences_data:
        tokens = [
            Token(
                text=tok["text"],
                begin=tok["begin"],
                end=tok["end"],
                pos=tok.get("pos", ""),
                token_id=tok.get("token_id", i + 1),
            )
            for i, tok in enumerate(sent_data.get("tokens", []))
        ]
        sentences.append(Sentence(
            text=sent_data["text"],
            begin=sent_data["begin"],
            end=sent_data["end"],
            tokens=tokens,
        ))
    return sentences


def extract_temporal_expressions(
    text: str,
    language: str = "english",
    doc_type: str = "news",
    dct: Optional[str] = None,
    resolve_with_dct: bool = True,
    find_dates: bool = True,
    find_times: bool = True,
    find_durations: bool = True,
    find_sets: bool = True,
    find_temponyms: bool = False,
    use_pos: bool = True,
    split_on_newlines: bool = False,
    sentences: Optional[List[Sentence]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract temporal expressions from text.

    Args:
        text: Input text to analyze (ignored if sentences provided)
        language: Language resources to use (default: "english")
        doc_type: Document type - "news", "narrative", "colloquial", "scientific"
        dct: Document creation time in YYYY-MM-DD format
        resolve_with_dct: Whether to resolve relative expressions using DCT
        find_dates: Extract DATE expressions
        find_times: Extract TIME expressions
        find_durations: Extract DURATION expressions
        find_sets: Extract SET expressions
        find_temponyms: Extract TEMPONYM expressions
        use_pos: Use POS tagging for disambiguation (via AWS Comprehend)
        split_on_newlines: Treat newlines as sentence boundaries
        sentences: Optional pre-processed sentences. If provided, skips
                  Comprehend call and uses these directly.

    Returns:
        List of temporal expression dictionaries
    """
    engine = get_engine(
        language=language,
        doc_type=doc_type,
        dct=dct,
        resolve_with_dct=resolve_with_dct,
        find_dates=find_dates,
        find_times=find_times,
        find_durations=find_durations,
        find_sets=find_sets,
        find_temponyms=find_temponyms,
        use_pos=use_pos,
        split_on_newlines=split_on_newlines,
    )

    timexes = engine.extract(text, sentences=sentences)

    return [timex_to_dict(t) for t in timexes]


def create_response(status_code: int, body: Any) -> Dict[str, Any]:
    """Create a Lambda response with proper headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
        },
        "body": json.dumps(body),
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for HeidelTime extraction.

    Expects a JSON body with:
    {
        "text": "The text to analyze",
        "language": "english",           // optional, default: "english"
        "doc_type": "news",              // optional, default: "news"
        "dct": "2024-01-15",             // optional, document creation time
        "resolve_with_dct": true,        // optional, default: true
        "find_dates": true,              // optional, default: true
        "find_times": true,              // optional, default: true
        "find_durations": true,          // optional, default: true
        "find_sets": true,               // optional, default: true
        "find_temponyms": false,         // optional, default: false
        "use_pos": true,                 // optional, default: true
        "split_on_newlines": false,      // optional, default: false
        "sentences": [                   // optional, pre-processed NLP data
            {
                "text": "sentence text",
                "begin": 0,
                "end": 14,
                "tokens": [
                    {"text": "sentence", "begin": 0, "end": 8, "pos": "NN", "token_id": 1},
                    {"text": "text", "begin": 9, "end": 13, "pos": "NN", "token_id": 2}
                ]
            }
        ]
    }

    If "sentences" is provided, the "text" field is ignored and no Comprehend
    call is made. This allows sharing NLP preprocessing across services.

    Returns:
    {
        "timexes": [
            {
                "type": "DATE",
                "text": "January 15, 2024",
                "value": "2024-01-15",
                "begin": 19,
                "end": 35,
                "timex_id": "t1",
                "rule": "date_r1"
            }
        ]
    }
    """
    # Handle CORS preflight
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if http_method == "OPTIONS":
        return create_response(200, {})

    try:
        # Parse request body
        body = event.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body)

        # Check for pre-processed sentences
        sentences_data = body.get("sentences")
        sentences = None
        if sentences_data:
            sentences = parse_sentences(sentences_data)
        
        text = body.get("text", "")
        if not text and not sentences:
            return create_response(400, {"error": "Missing required field: text (or sentences)"})

        # Extract parameters with defaults
        params = {
            "text": text,
            "language": body.get("language", "english"),
            "doc_type": body.get("doc_type", "news"),
            "dct": body.get("dct"),
            "resolve_with_dct": body.get("resolve_with_dct", True),
            "find_dates": body.get("find_dates", True),
            "find_times": body.get("find_times", True),
            "find_durations": body.get("find_durations", True),
            "find_sets": body.get("find_sets", True),
            "find_temponyms": body.get("find_temponyms", False),
            "use_pos": body.get("use_pos", True),
            "split_on_newlines": body.get("split_on_newlines", False),
            "sentences": sentences,
        }

        # Extract temporal expressions
        timexes = extract_temporal_expressions(**params)

        return create_response(200, {"timexes": timexes})

    except json.JSONDecodeError as e:
        return create_response(400, {"error": f"Invalid JSON: {str(e)}"})
    except Exception as e:
        # Log the full error for debugging
        import traceback
        traceback.print_exc()
        return create_response(500, {"error": f"Internal error: {str(e)}"})


# For local testing
if __name__ == "__main__":
    # Test event
    test_event = {
        "body": json.dumps({
            "text": "The meeting is scheduled for January 15, 2024 at 3pm. We discussed events from last week.",
            "dct": "2024-01-10",
            "doc_type": "news",
        })
    }

    result = handler(test_event, None)
    print(json.dumps(json.loads(result["body"]), indent=2))
