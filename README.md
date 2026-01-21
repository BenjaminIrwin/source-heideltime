# PythonHeidelTime

A Python implementation of the HeidelTime temporal expression tagger.

## License

**This package is licensed under GNU General Public License v3 (GPL-3.0)**, the same license as the original HeidelTime project.

This means:
- You can use this software freely
- You can modify and distribute it
- If you distribute modified versions, you must also release them under GPL-3.0
- You must make the source code available

See: https://www.gnu.org/licenses/gpl-3.0.html

## Installation

```bash
pip install boto3
```

Note: This package uses AWS Comprehend for NLP preprocessing. Ensure you have AWS credentials configured.

### AWS Lambda Deployment

This package includes infrastructure for deploying as an AWS Lambda service using **AWS Comprehend** for NLP preprocessing.

See [DEPLOY.md](DEPLOY.md) for full instructions.

```bash
# Quick deploy
./scripts/deploy.sh --init
```

## Usage

### Python Library

```python
from heideltime import HeidelTimeEngine

engine = HeidelTimeEngine(
    language_dir="resources/english",
    doc_type="news",
    dct="2024-01-15",
)

timexes = engine.extract("The meeting is scheduled for January 15, 2024 at 3pm.")

for timex in timexes:
    print(f"{timex.text} -> {timex.value} ({timex.timex_type})")
```

### With Pre-processed NLP Data

If you've already tokenized/POS-tagged text upstream (e.g., shared Comprehend call), you can pass it directly:

```python
from heideltime import HeidelTimeEngine, Sentence, Token

# Pre-processed data from your NLP pipeline
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
```

### HTTP API (Lambda or Local)

This package can be deployed as a REST API service. The HTTP API allows proprietary client code to use HeidelTime without GPL license requirements (the GPL copyleft does not extend over network APIs).

```bash
# POST to the Lambda endpoint or local server
curl -X POST <endpoint_url> \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "The meeting is on January 15, 2024.",
    "doc_type": "news",
    "dct": "2024-01-15"
  }'
```

Response:
```json
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
```

## Document Types

- `news` - News articles (default, uses document creation time for relative expressions)
- `narrative` - Historical/narrative text (uses context for relative expressions)
- `colloquial` - Informal/conversational text
- `scientific` - Scientific/academic text

## Attribution

Based on HeidelTime by Jannik Strötgen and Michael Gertz.
- Original project: https://github.com/HeidelTime/heideltime
- Paper: Strötgen & Gertz (2010). HeidelTime: High Quality Rule-based Extraction and Normalization of Temporal Expressions.
