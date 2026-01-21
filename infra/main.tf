# HeidelTime Python - AWS Lambda Infrastructure
# License: GPL-3.0
#
# This Terraform configuration deploys HeidelTime as an AWS Lambda
# function using a container image, with an HTTP API endpoint.

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Get AWS account ID for ARN construction
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
  ecr_image  = "${local.account_id}.dkr.ecr.${local.region}.amazonaws.com/${var.ecr_repository_name}:${var.image_tag}"
}

# ===========================================
# ECR REPOSITORY
# ===========================================

resource "aws_ecr_repository" "heideltime" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "heideltime" {
  repository = aws_ecr_repository.heideltime.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ===========================================
# IAM ROLE
# ===========================================

resource "aws_iam_role" "lambda_role" {
  name = "${var.function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# Basic Lambda execution policy (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Comprehend access for NLP preprocessing
resource "aws_iam_role_policy" "comprehend_access" {
  name = "${var.function_name}-comprehend-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "comprehend:DetectSyntax",
          "comprehend:BatchDetectSyntax"
        ]
        Resource = "*"
      }
    ]
  })
}

# ===========================================
# LAMBDA FUNCTION
# ===========================================

resource "aws_lambda_function" "heideltime" {
  function_name = var.function_name
  role          = aws_iam_role.lambda_role.arn
  package_type  = "Image"
  image_uri     = local.ecr_image
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size
  architectures = [var.lambda_architecture]

  environment {
    variables = {
      HEIDELTIME_RESOURCES = "/var/task/resources"
    }
  }

  tags = var.tags

  depends_on = [
    aws_ecr_repository.heideltime,
    aws_cloudwatch_log_group.lambda_logs
  ]
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# ===========================================
# LAMBDA FUNCTION URL (Simple HTTP endpoint)
# ===========================================

resource "aws_lambda_function_url" "heideltime" {
  function_name      = aws_lambda_function.heideltime.function_name
  authorization_type = var.function_url_auth_type

  cors {
    allow_origins     = var.cors_allow_origins
    allow_methods     = ["POST", "OPTIONS"]
    allow_headers     = ["content-type"]
    allow_credentials = false
    max_age           = 86400
  }
}

# Permission for public access (if using NONE auth)
resource "aws_lambda_permission" "function_url_public" {
  count = var.function_url_auth_type == "NONE" ? 1 : 0

  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.heideltime.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# ===========================================
# API GATEWAY (Optional, more features)
# ===========================================

resource "aws_apigatewayv2_api" "heideltime" {
  count = var.create_api_gateway ? 1 : 0

  name          = "${var.function_name}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["content-type"]
    allow_methods = ["POST", "OPTIONS"]
    allow_origins = var.cors_allow_origins
  }

  tags = var.tags
}

resource "aws_apigatewayv2_integration" "heideltime" {
  count = var.create_api_gateway ? 1 : 0

  api_id                 = aws_apigatewayv2_api.heideltime[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.heideltime.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "heideltime_post" {
  count = var.create_api_gateway ? 1 : 0

  api_id    = aws_apigatewayv2_api.heideltime[0].id
  route_key = "POST /extract"
  target    = "integrations/${aws_apigatewayv2_integration.heideltime[0].id}"
}

resource "aws_apigatewayv2_stage" "heideltime_default" {
  count = var.create_api_gateway ? 1 : 0

  api_id      = aws_apigatewayv2_api.heideltime[0].id
  name        = "$default"
  auto_deploy = true

  tags = var.tags
}

resource "aws_lambda_permission" "apigw" {
  count = var.create_api_gateway ? 1 : 0

  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.heideltime.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.heideltime[0].execution_arn}/*/*"
}
