.PHONY: setup download build score benchmark serve dev web test

setup:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e . && cd web && npm install
	printf 'import sys, os\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../src")))\n' > .venv/lib/python3.12/site-packages/sitecustomize.py

download:
	.venv/bin/ct download

build:
	.venv/bin/ct build

score:
	.venv/bin/ct score && .venv/bin/ct benchmark

web:
	cd web && npm run build

serve: web
	.venv/bin/ct serve

dev:
	(.venv/bin/uvicorn cancer_targets.api.main:app --port 8000 --reload &) && cd web && npm run dev

test:
	.venv/bin/pytest -q
