test:
	python setup.py test

upload_docs:
	make -C docs html SPHINXOPTS=-Aonline=1
	python setup.py upload_docs

.PHONY: test upload_docs
