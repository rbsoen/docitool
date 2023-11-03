# docitool

This is a preprocessor that aims to ease writing technical and academic documents using pure HTML and CSS.

Its output can be presented as both a viewable web page, or converted into a printable format using tools like [Weasyprint](https://weasyprint.org/).

See `sample-doc.pdf` and the `doc/` folder in this repository for more information on how to use this tool.

## Installation

At the moment, the package has not yet been published in PyPI. So to obtain it:
```
pip install "docitool @ git+https://github.com/rbsoen/docitool"
```
The following extras are available:
- **citations**: Allows using `citeproc-py` to render citations.
- **formulas**: Allows embedding KaTeX formulas in the document.
- **plots**: Allows using Matplotlib to render graphs in the document, via Python programs.
- **markdown**: Allows embedding Markdown documents.

For example, to install docitool with the **citations** and **markdown** extra features:
```
pip install "docitool[citations, markdown] @ git+https://github.com/rbsoen/docitool"
```
