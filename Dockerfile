# HeidelTime Lambda container image.
# Container (not zip) is required because spaCy + model + numpy/thinc/blis exceed
# Lambda's 250 MB unzipped zip limit. License: GPL-3.0 (same as HeidelTime).

FROM public.ecr.aws/lambda/python:3.11

# Which spaCy model to bake in. Swap without code changes: sm (fast) / md (default,
# accuracy sweet spot) / trf (max accuracy, needs torch + spacy-transformers).
ARG SPACY_MODEL=en_core_web_md

# Python deps (spacy, boto3 for the Comprehend fallback). Model is installed below.
# numpy is pinned < 2.1: newer numpy wheels target manylinux_2_28 (glibc 2.28) which
# is incompatible with this Lambda base image's glibc, forcing a from-source build
# (no compiler in the image). The 2.0.x line ships manylinux2014 wheels that install
# cleanly. This is a build constraint, not a logical dependency.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
# `click` is required by spaCy's CLI (used below to download the model) but is not
# always pulled in transitively by the installed typer version.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "numpy<2.1" click -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Transformer models pull in spacy-transformers (+ torch); CNN models do not.
RUN if echo "${SPACY_MODEL}" | grep -q "trf"; then \
        pip install --no-cache-dir spacy-transformers; \
    fi
RUN python -m spacy download "${SPACY_MODEL}"

# Application code + HeidelTime resources.
COPY *.py ${LAMBDA_TASK_ROOT}/
COPY processors/ ${LAMBDA_TASK_ROOT}/processors/
COPY resources/english/ ${LAMBDA_TASK_ROOT}/resources/english/

# Make the runtime default model match the baked-in one, and keep OpenMP single-
# threaded (avoids the multiprocessing "OMP errno 38" failure when loading trf on
# Lambda; harmless for CNN models on Lambda's ~1 vCPU).
ENV SPACY_MODEL=${SPACY_MODEL} \
    OMP_NUM_THREADS=1 \
    HEIDELTIME_RESOURCES=/var/task/resources

CMD ["lambda_handler.handler"]
