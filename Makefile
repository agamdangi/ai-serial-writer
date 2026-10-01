.PHONY: install doctor test demo-fake clean

install:
	pip install -r requirements.txt
	pip install -e .

doctor:
	python -m serial_writer doctor

test:
	python -m pytest

demo-fake:
	python -m serial_writer demo --fake

clean:
	rm -rf build dist *.egg-info .pytest_cache
	find . -name "__pycache__" -exec rm -rf {} +
