all: clean-pyc test

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

test:
	@python test_logbook.py --verbose

upload-docs:
	make -C docs html SPHINXOPTS=-Aonline=1
	python setup.py upload_docs

.PHONY: test upload-docs clean-pyc all
