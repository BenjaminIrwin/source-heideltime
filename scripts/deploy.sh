#!/bin/bash
# HeidelTime Python - AWS Lambda Deployment Script
# License: GPL-3.0
#
# Builds the HeidelTime container image (spaCy + model + HeidelTime), pushes it to
# ECR, and deploys the Lambda from that image with Terraform.
#
# The Lambda is a container image (not a zip) because spaCy + its model + numpy/
# thinc/blis exceed Lambda's 250 MB unzipped zip limit.
#
# Usage:
#   ./scripts/deploy.sh [--init] [--destroy]
#
# Env overrides:
#   SPACY_MODEL       spaCy model to bake in (default: en_core_web_md; sm/md/trf)
#   IMAGE_TAG         image tag to build/push/deploy (default: latest)
#   LAMBDA_PLATFORM   docker build platform (default: linux/amd64 for x86_64 Lambda)

set -euo pipefail

# Configuration (overridable via environment)
SPACY_MODEL="${SPACY_MODEL:-en_core_web_md}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
LAMBDA_PLATFORM="${LAMBDA_PLATFORM:-linux/amd64}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
INFRA_DIR="$PROJECT_DIR/infra"

echo -e "${GREEN}HeidelTime Lambda Deployment (container image)${NC}"
echo "Project directory: $PROJECT_DIR"
echo "spaCy model:       $SPACY_MODEL"
echo "Image tag:         $IMAGE_TAG"
echo "Build platform:    $LAMBDA_PLATFORM"
echo ""

# Parse arguments
DO_INIT=false
DO_DESTROY=false

for arg in "$@"; do
    case $arg in
        --init)
            DO_INIT=true
            ;;
        --destroy)
            DO_DESTROY=true
            ;;
        --help|-h)
            echo "Usage: $0 [--init] [--destroy]"
            echo ""
            echo "Options:"
            echo "  --init      Run terraform init before apply"
            echo "  --destroy   Destroy all infrastructure"
            exit 0
            ;;
    esac
done

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"

    for tool in aws terraform docker; do
        if ! command -v "$tool" &> /dev/null; then
            echo -e "${RED}Error: $tool is not installed${NC}"
            exit 1
        fi
    done

    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}Error: AWS credentials not configured${NC}"
        echo "Run: aws configure"
        exit 1
    fi

    echo -e "${GREEN}All prerequisites met${NC}"
}

terraform_init() {
    cd "$INFRA_DIR"
    if [ "$DO_INIT" = true ] || [ ! -d ".terraform" ]; then
        echo -e "${YELLOW}Initializing Terraform...${NC}"
        terraform init
    fi
}

# Ensure the ECR repository exists before we build/push (it is a Terraform resource,
# so create just that target first to avoid a chicken-and-egg with the image digest).
ensure_ecr_repo() {
    cd "$INFRA_DIR"
    echo -e "${YELLOW}Ensuring ECR repository exists...${NC}"
    terraform apply -target=aws_ecr_repository.heideltime -auto-approve
}

# Build and push the container image to ECR.
build_and_push_image() {
    cd "$INFRA_DIR"
    ECR_URL="$(terraform output -raw ecr_repository_url)"
    REGISTRY="${ECR_URL%%/*}"
    # Registry host: <account>.dkr.ecr.<region>.amazonaws.com -> region is field 4.
    REGION="$(echo "$REGISTRY" | cut -d. -f4)"

    echo -e "${YELLOW}Logging in to ECR ($REGISTRY)...${NC}"
    aws ecr get-login-password --region "$REGION" \
        | docker login --username AWS --password-stdin "$REGISTRY"

    echo -e "${YELLOW}Building image ${ECR_URL}:${IMAGE_TAG} (model=${SPACY_MODEL})...${NC}"
    cd "$PROJECT_DIR"
    docker build \
        --platform "$LAMBDA_PLATFORM" \
        --build-arg "SPACY_MODEL=${SPACY_MODEL}" \
        -t "${ECR_URL}:${IMAGE_TAG}" \
        .

    echo -e "${YELLOW}Pushing image...${NC}"
    docker push "${ECR_URL}:${IMAGE_TAG}"
    echo -e "${GREEN}Image pushed: ${ECR_URL}:${IMAGE_TAG}${NC}"
}

# Deploy the Lambda (and the rest of the stack) from the pushed image.
terraform_apply() {
    cd "$INFRA_DIR"
    echo -e "${YELLOW}Applying Terraform configuration...${NC}"
    terraform apply -auto-approve

    echo ""
    echo -e "${GREEN}Deployment complete!${NC}"
    echo ""
    echo "Function URL:"
    terraform output -raw function_url || true
    echo ""
}

terraform_destroy() {
    cd "$INFRA_DIR"
    echo -e "${RED}Destroying infrastructure...${NC}"
    terraform destroy -auto-approve
    echo -e "${GREEN}Infrastructure destroyed${NC}"
}

# Main
check_prerequisites
terraform_init

if [ "$DO_DESTROY" = true ]; then
    terraform_destroy
    exit 0
fi

ensure_ecr_repo
build_and_push_image
terraform_apply

echo ""
echo -e "${GREEN}Done!${NC}"
echo ""
echo "Test with:"
echo "  curl -X POST \$(terraform -chdir=infra output -raw function_url) \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\": \"The meeting is on January 15, 2024\", \"dct\": \"2024-01-10\", \"preprocessor\": \"spacy\"}'"
