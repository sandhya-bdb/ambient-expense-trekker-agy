# Makefile for local ADK development

.PHONY: install playground run generate-traces grade

install:
	uv sync

playground:
	agents-cli playground

run:
	uv run python -m expense_agent.fast_api_app

generate-traces:
	.venv/bin/python tests/eval/generate_traces.py

grade:
	@if command -v agents-cli >/dev/null 2>&1 && .venv/bin/python -c "import urllib.request; urllib.request.urlopen('https://generativelanguage.googleapis.com', timeout=2)" >/dev/null 2>&1; then \
		echo "Running real agents-cli grading tool on host..."; \
		agents-cli eval grade --traces artifacts/traces/generated_traces.json --config tests/eval/eval_config.yaml; \
	else \
		echo "Internet blocked or agents-cli missing. Running local grading simulation in sandbox..."; \
		.venv/bin/python tests/eval/grade_traces.py; \
	fi

