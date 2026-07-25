# A Makefile is the simplest "modular commands" interface: each target is one
# well-named action. `make test`, `make run` -- easy to remember, easy to wire
# into CI. This is the book's "make it modular" advice at the task level.

.PHONY: install test run serve query clean

install:            ## install dev dependencies (pytest)
	pip install -r requirements-dev.txt

test:               ## run the test suite
	python -m pytest

run:                ## push the sample dataset through the whole pipeline
	python run_pipeline.py batch

serve:              ## start the ingestion HTTP API on :8000
	python run_pipeline.py serve

query:              ## print analytics over whatever is currently persisted
	python run_pipeline.py query

clean:              ## delete generated data (stream log + warehouse db)
	rm -f data/stream.jsonl data/warehouse.db
	find . -name __pycache__ -type d -exec rm -rf {} +
