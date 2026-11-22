FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

WORKDIR /app
COPY selector.py patch_model.py scheduler.py semantic.py fixture_index.json process_index.json semantic_index.json dialect_index.json escape_index.json code_index.json.gz coverage.json.gz expression_usage.json.gz typing_index.json.gz typing_usage.json.gz function_index.json.gz /app/

ENV PYTHONDONTWRITEBYTECODE=1
ENV BLAST_CLASS_PROBE=1
USER 65534:65534
CMD ["python", "/app/selector.py"]
