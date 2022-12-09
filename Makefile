PYTHON_BIN ?= poetry run python

format:
	$(PYTHON_BIN) -m monoformat .
