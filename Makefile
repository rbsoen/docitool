PYTHON ?= python3
PREPROCESSOR = tools/preprocess.py

WP := weasyprint
WPOPTS :=

all: document.pdf

document.pdf: document.html
	$(WP) $(WPOPTS) $< $@

document.html: index.html
	$(PYTHON) $(PREPROCESSOR) $< > $@

.INTERMEDIATE: document.html

clean:
	rm -fv document.pdf document.html
