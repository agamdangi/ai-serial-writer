.PHONY: install doctor test demo-fake demo-submission lint clean

install:
	pip install -r requirements.txt
	pip install -e .

doctor:
	python -m serial_writer doctor

test:
	python -m pytest

lint:
	python -m compileall -q serial_writer tests

demo-fake:
	python -m serial_writer demo --fake --run assignment_demo

demo-submission:
	python -m serial_writer demo --fake --run assignment_demo
	python -m serial_writer finalize --run assignment_demo

clean:
	rm -rf build dist *.egg-info .pytest_cache
	find . -name "__pycache__" -exec rm -rf {} +
