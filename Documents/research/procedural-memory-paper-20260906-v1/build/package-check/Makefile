.PHONY: all analyze clean qa package FORCE
all: iab.pdf aiwild.pdf
FORCE:
analyze:
	python3 scripts/analyze.py
	python3 scripts/render_assets.py
iab.pdf: iab.tex manuscript.tex preamble.tex references.bib neurips_2026.sty $(wildcard sections/*.tex) $(wildcard generated/*.tex) $(wildcard figures/*.pdf) FORCE
	latexmk -pdf -interaction=nonstopmode -halt-on-error iab.tex
aiwild.pdf: aiwild.tex manuscript.tex preamble.tex references.bib neurips_2026.sty $(wildcard sections/*.tex) $(wildcard generated/*.tex) $(wildcard figures/*.pdf) FORCE
	latexmk -pdf -interaction=nonstopmode -halt-on-error aiwild.tex
qa: all
	python3 scripts/qa.py
package: all qa
	python3 scripts/package.py
clean:
	latexmk -c iab.tex aiwild.tex
