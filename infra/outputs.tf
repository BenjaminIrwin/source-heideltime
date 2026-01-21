# HeidelTime Python - Terraform Outputs
# License: GPL-3.0

output "function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.heideltime.function_name
}

output "function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.heideltime.arn
}

output "function_url" {
  description = "Lambda Function URL endpoint"
  value       = aws_lambda_function_url.heideltime.function_url
}

output "api_gateway_url" {
  description = "API Gateway endpoint (if enabled)"
  value       = var.create_api_gateway ? "${aws_apigatewayv2_api.heideltime[0].api_endpoint}/extract" : null
}

output "log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}
