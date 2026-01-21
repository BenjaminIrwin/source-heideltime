#!/bin/bash
# HeidelTime Python - AWS Lambda Deployment Script
# License: GPL-3.0
#
# This script packages and deploys HeidelTime to AWS Lambda using
# a zip package and Terraform.
#
# Usage:
#   ./scripts/deploy.sh [--init] [--destroy]

set -e

# Configuration (can be overridden with environment variables)
AWS_REGION="${AWS_REGION:-eu-west-2}"

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
    
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}Error: AWS CLI is not installed${NC}"
        exit 1
    fi
    
    if ! command -v terraform &> /dev/null; then
        echo -e "${RED}Error: Terraform is not installed${NC}"
        exit 1
    fi
    
    if ! command -v zip &> /dev/null; then
        echo -e "${RED}Error: zip is not installed${NC}"
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

# Create Lambda zip package
create_package() {
    echo -e "${YELLOW}Creating Lambda package...${NC}"
    
    cd "$PROJECT_DIR"
    
    # Remove old package
    rm -f lambda.zip
    
    # Create zip with Python files and resources
    zip -r lambda.zip \
        *.py \
        processors/ \
        resources/english/ \
        -x "*.pyc" \
        -x "__pycache__/*" \
        -x "*.egg-info/*"
    
    # Show package size
    PACKAGE_SIZE=$(du -h lambda.zip | cut -f1)
    echo -e "${GREEN}Package created: lambda.zip (${PACKAGE_SIZE})${NC}"
}

# Run Terraform
run_terraform() {
    cd "$INFRA_DIR"
    
    if [ "$DO_INIT" = true ] || [ ! -d ".terraform" ]; then
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

create_package
run_terraform

echo ""
echo -e "${GREEN}Done!${NC}"
echo ""
echo "Test with:"
echo "  curl -X POST \$(terraform -chdir=infra output -raw function_url) \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\": \"The meeting is on January 15, 2024\", \"dct\": \"2024-01-10\"}'"
