PYTHON ?= python3
DOCITOOL := ../docitool/__main__.py
DOCITOOLOPTS := -v

WP := weasyprint
WPOPTS :=

all: document.pdf

document.pdf: document.html
	$(WP) $(WPOPTS) $< $@

document.html: index.html
	$(PYTHON) $(DOCITOOL) $(DOCITOOLOPTS) $< $@

.INTERMEDIATE: document.html

clean:
	rm -fv document.pdf document.html
