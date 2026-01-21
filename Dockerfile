# HeidelTime Python - AWS Lambda Container Image
# License: GPL-3.0
#
# This Dockerfile creates a Lambda-compatible container image for
# the HeidelTime temporal expression extraction service.
# Uses AWS Comprehend for NLP preprocessing.

FROM public.ecr.aws/lambda/python:3.11

# Copy requirements first for better caching
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Install Python dependencies
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy application code
COPY *.py ${LAMBDA_TASK_ROOT}/
COPY processors/ ${LAMBDA_TASK_ROOT}/processors/
COPY resources/ ${LAMBDA_TASK_ROOT}/resources/

# Set environment variables
ENV HEIDELTIME_RESOURCES=${LAMBDA_TASK_ROOT}/resources

# Set the handler
CMD ["lambda_handler.handler"]
