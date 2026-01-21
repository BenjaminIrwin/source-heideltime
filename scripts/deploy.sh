#!/bin/bash
# HeidelTime Python - AWS Lambda Deployment Script
# License: GPL-3.0
#
# This script builds and deploys HeidelTime to AWS Lambda using
# Docker and Terraform.
#
# Usage:
#   ./scripts/deploy.sh [--init] [--destroy]
#
# Options:
#   --init      Run terraform init before apply
#   --destroy   Destroy all infrastructure
#   --build     Only build and push Docker image (skip Terraform)
#   --apply     Only run Terraform apply (skip Docker build)

set -e

# Configuration (can be overridden with environment variables)
AWS_REGION="${AWS_REGION:-eu-west-2}"
ECR_REPOSITORY="${ECR_REPOSITORY:-heideltime}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
INFRA_DIR="$PROJECT_DIR/infra"

echo -e "${GREEN}HeidelTime Lambda Deployment${NC}"
echo "Project directory: $PROJECT_DIR"
echo "AWS Region: $AWS_REGION"
echo ""

# Parse arguments
DO_INIT=false
DO_DESTROY=false
DO_BUILD=true
DO_APPLY=true

for arg in "$@"; do
    case $arg in
        --init)
            DO_INIT=true
            ;;
        --destroy)
            DO_DESTROY=true
            ;;
        --build)
            DO_APPLY=false
            ;;
        --apply)
            DO_BUILD=false
            ;;
        --help|-h)
            echo "Usage: $0 [--init] [--destroy] [--build] [--apply]"
            echo ""
            echo "Options:"
            echo "  --init      Run terraform init before apply"
            echo "  --destroy   Destroy all infrastructure"
            echo "  --build     Only build and push Docker image"
            echo "  --apply     Only run Terraform apply"
            exit 0
            ;;
    esac
done

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"
    
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}Error: AWS CLI is not installed${NC}"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        exit 1
    fi
    
    if ! command -v terraform &> /dev/null; then
        echo -e "${RED}Error: Terraform is not installed${NC}"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}Error: AWS credentials not configured${NC}"
        echo "Run: aws configure"
        exit 1
    fi
    
    echo -e "${GREEN}All prerequisites met${NC}"
}

# Get AWS account ID
get_aws_account_id() {
    aws sts get-caller-identity --query Account --output text
}

# Build and push Docker image
build_and_push() {
    echo -e "${YELLOW}Building Docker image...${NC}"
    
    ACCOUNT_ID=$(get_aws_account_id)
    ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"
    
    # Build image
    cd "$PROJECT_DIR"
    docker build -t "${ECR_REPOSITORY}:${IMAGE_TAG}" .
    
    # Tag for ECR
    docker tag "${ECR_REPOSITORY}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
    
    echo -e "${YELLOW}Logging into ECR...${NC}"
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    
    echo -e "${YELLOW}Pushing image to ECR...${NC}"
    docker push "${ECR_URI}:${IMAGE_TAG}"
    
    echo -e "${GREEN}Docker image pushed successfully${NC}"
}

# Run Terraform
run_terraform() {
    cd "$INFRA_DIR"
    
    if [ "$DO_INIT" = true ]; then
        echo -e "${YELLOW}Initializing Terraform...${NC}"
        terraform init
    fi
    
    if [ "$DO_DESTROY" = true ]; then
        echo -e "${RED}Destroying infrastructure...${NC}"
        terraform destroy -auto-approve
        echo -e "${GREEN}Infrastructure destroyed${NC}"
        return
    fi
    
    echo -e "${YELLOW}Applying Terraform configuration...${NC}"
    terraform apply -auto-approve
    
    echo ""
    echo -e "${GREEN}Deployment complete!${NC}"
    echo ""
    echo "Function URL:"
    terraform output -raw function_url
    echo ""
}

# Main
check_prerequisites

if [ "$DO_DESTROY" = true ]; then
    run_terraform
    exit 0
fi

if [ "$DO_BUILD" = true ]; then
    # First, we need ECR repository to exist
    # Run terraform for just the ECR repo first if it doesn't exist
    cd "$INFRA_DIR"
    if [ "$DO_INIT" = true ] || [ ! -d ".terraform" ]; then
        terraform init
    fi
    
    # Create ECR repository if it doesn't exist
    ACCOUNT_ID=$(get_aws_account_id)
    if ! aws ecr describe-repositories --repository-names "$ECR_REPOSITORY" --region "$AWS_REGION" &> /dev/null; then
        echo -e "${YELLOW}Creating ECR repository...${NC}"
        terraform apply -target=aws_ecr_repository.heideltime -auto-approve
        terraform apply -target=aws_ecr_lifecycle_policy.heideltime -auto-approve
    fi
    
    build_and_push
fi

if [ "$DO_APPLY" = true ]; then
    run_terraform
fi

echo ""
echo -e "${GREEN}Done!${NC}"
echo ""
echo "Test with:"
echo "  curl -X POST <function_url> \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\": \"The meeting is on January 15, 2024\", \"dct\": \"2024-01-10\"}'"
