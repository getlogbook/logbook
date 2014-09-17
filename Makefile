all: clean-pyc test

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

test_setup:
	@python scripts/test_setup.py

test:
	@py.test tests

toxtest:
	@tox

vagrant_toxtest:
	@vagrant up
	@vagrant ssh --command "rsync -avP --delete --exclude=_build --exclude=.tox /vagrant/ ~/src/ && cd ~/src/ && tox"

bench:
	@python benchmark/run.py

upload-docs: docs
	python setup.py upload_docs

docs:
	make -C docs html SPHINXOPTS=-Aonline=1

release: logbook/_speedups.so upload-docs
	python scripts/make-release.py

logbook/_speedups.so: logbook/_speedups.pyx
	cython logbook/_speedups.pyx
	python setup.py build
	cp build/*/logbook/_speedups*.so logbook

cybuild: logbook/_speedups.so

.PHONY: test upload-docs clean-pyc cybuild bench all docs
