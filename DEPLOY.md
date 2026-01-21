# HeidelTime Python - AWS Lambda Deployment Guide

This guide explains how to deploy HeidelTime as an AWS Lambda function with an HTTP API endpoint.

## Architecture

The deployment uses:
- **AWS Lambda** with container images
- **AWS Comprehend** for NLP preprocessing (tokenization, POS tagging)
- **Amazon ECR** for container image storage
- **Lambda Function URL** for HTTP access (or optional API Gateway)
- **Terraform** for infrastructure as code

AWS Comprehend provides fast cold starts (<1 second) with a small container (~50MB).

## Prerequisites

1. **AWS CLI** configured with credentials
   ```bash
   aws configure
   ```

2. **Docker** installed and running

3. **Terraform** >= 1.0
   ```bash
   brew install terraform  # macOS
   ```

4. AWS IAM permissions for:
   - Lambda (create, update, invoke)
   - ECR (create repository, push images)
   - IAM (create roles)
   - CloudWatch Logs
   - **Comprehend** (DetectSyntax)

## Quick Start

### 1. Deploy Everything

```bash
# From the project root
./scripts/deploy.sh --init
```

This will:
- Create an ECR repository
- Build and push the Docker image
- Deploy the Lambda function with Terraform
- Configure Comprehend permissions
- Output the Function URL

### 2. Test the Endpoint

```bash
curl -X POST <function_url> \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "The meeting is scheduled for January 15, 2024 at 3pm.",
    "dct": "2024-01-10",
    "doc_type": "news"
  }'
```

Expected response:
```json
{
  "timexes": [
    {
      "type": "DATE",
      "text": "January 15, 2024",
      "value": "2024-01-15",
      "begin": 32,
      "end": 48,
      "timex_id": "t1",
      "rule": "date_r..."
    },
    {
      "type": "TIME",
      "text": "3pm",
      "value": "2024-01-15T15:00",
      "begin": 52,
      "end": 55,
      "timex_id": "t2",
      "rule": "time_r..."
    }
  ]
}
```

## Configuration

### Terraform Variables

Copy and customize the example variables:

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region          = "eu-west-2"
function_name       = "heideltime"
lambda_memory_size  = 256     # MB
lambda_timeout      = 30      # seconds

# Security
function_url_auth_type = "AWS_IAM"  # or "NONE" for public access
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `eu-west-2` | AWS region for deployment |
| `ECR_REPOSITORY` | `heideltime` | ECR repository name |
| `IMAGE_TAG` | `latest` | Docker image tag |

## Deployment Commands

```bash
# Full deployment (build + terraform)
./scripts/deploy.sh --init

# Just rebuild and push Docker image
./scripts/deploy.sh --build

# Just run Terraform (after manual image push)
./scripts/deploy.sh --apply

# Destroy all infrastructure
./scripts/deploy.sh --destroy
```

## API Reference

### POST /

Extract temporal expressions from text.

**Request Body:**

```json
{
  "text": "string (required, unless sentences provided)",
  "language": "string (default: 'english')",
  "doc_type": "string (default: 'news')",
  "dct": "string (YYYY-MM-DD format, optional)",
  "resolve_with_dct": "boolean (default: true)",
  "find_dates": "boolean (default: true)",
  "find_times": "boolean (default: true)",
  "find_durations": "boolean (default: true)",
  "find_sets": "boolean (default: true)",
  "find_temponyms": "boolean (default: false)",
  "use_pos": "boolean (default: true)",
  "split_on_newlines": "boolean (default: false)",
  "sentences": "array (optional, pre-processed NLP data)"
}
```

**Pre-processed NLP Input:**

If you've already called Comprehend (or another NLP service) upstream, you can pass
the tokenized sentences directly to avoid redundant API calls:

```json
{
  "sentences": [
    {
      "text": "The meeting is on January 15, 2024.",
      "begin": 0,
      "end": 36,
      "tokens": [
        {"text": "The", "begin": 0, "end": 3, "pos": "DT", "token_id": 1},
        {"text": "meeting", "begin": 4, "end": 11, "pos": "NN", "token_id": 2},
        {"text": "is", "begin": 12, "end": 14, "pos": "VB", "token_id": 3},
        {"text": "on", "begin": 15, "end": 17, "pos": "IN", "token_id": 4},
        {"text": "January", "begin": 18, "end": 25, "pos": "NNP", "token_id": 5},
        {"text": "15", "begin": 26, "end": 28, "pos": "CD", "token_id": 6},
        {"text": ",", "begin": 28, "end": 29, "pos": ".", "token_id": 7},
        {"text": "2024", "begin": 30, "end": 34, "pos": "CD", "token_id": 8},
        {"text": ".", "begin": 34, "end": 35, "pos": ".", "token_id": 9}
      ]
    }
  ],
  "dct": "2024-01-10"
}
```

When `sentences` is provided, `text` is ignored and no Comprehend call is made.

**Document Types:**
- `news` - News articles (default)
- `narrative` - Historical/narrative text
- `colloquial` - Informal/conversational text
- `scientific` - Scientific/academic text

**Response:**

```json
{
  "timexes": [
    {
      "type": "DATE|TIME|DURATION|SET|TEMPONYM",
      "text": "original text span",
      "value": "normalized TimeML value",
      "begin": 0,
      "end": 10,
      "quant": "optional quantifier",
      "freq": "optional frequency",
      "mod": "optional modifier",
      "timex_id": "t1",
      "rule": "rule that matched"
    }
  ]
}
```

## Cost Considerations

### AWS Comprehend Pricing

Comprehend charges per unit (100 characters) for `DetectSyntax`:
- ~$0.0001 per unit in most regions
- Minimum 3 units per request

For a typical request with 500 characters:
- 5 units × $0.0001 = $0.0005 per request

### Lambda Pricing

With the container:
- Memory: 256MB
- Typical duration: 100-500ms
- Cost: ~$0.000001 per request

### Total Cost Example

1000 requests/day with average 500 char texts:
- Comprehend: 1000 × $0.0005 = $0.50/day
- Lambda: 1000 × $0.000001 = negligible
- **Total: ~$15/month**

## Monitoring

### View Logs

```bash
# Tail logs in real-time
aws logs tail /aws/lambda/heideltime --follow

# Last 10 minutes
aws logs tail /aws/lambda/heideltime --since 10m
```

### Test Function Directly

```bash
aws lambda invoke \
  --function-name heideltime \
  --payload '{"body": "{\"text\": \"January 15, 2024\"}"}' \
  output.json

cat output.json
```

## POS Tagging

HeidelTime uses POS tags to disambiguate words like "May" (month vs. verb). AWS Comprehend provides Universal Dependencies tags which are mapped to Penn Treebank:

| Comprehend | Penn Treebank | Used for |
|------------|---------------|----------|
| NOUN | NN | "second" as noun vs ordinal |
| VERB | VB | "march/may" as verb vs month |
| AUX | MD | "may" as modal verb |
| ADJ | JJ | Adjective disambiguation |

Set `use_pos=false` if you want to skip POS disambiguation entirely.

## Security

### Authentication Options

1. **NONE** (default): Public access
2. **AWS_IAM**: Requires AWS credentials

For production, consider:
- Setting `function_url_auth_type = "AWS_IAM"`
- Using API Gateway with API keys
- Restricting CORS origins

## Troubleshooting

### Comprehend Access Denied

Ensure the Lambda role has `comprehend:DetectSyntax` permission. The Terraform configuration includes this by default.

### Cold Start Still Slow?

The container is much smaller now, but first requests still need to:
1. Start the container
2. Initialize the HeidelTime rules

Typical cold start: <1 second

For consistent latency, use provisioned concurrency.

## License

This deployment infrastructure is licensed under GPL-3.0, the same license as HeidelTime.
