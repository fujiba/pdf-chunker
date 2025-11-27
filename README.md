# pdf_chunker

CLI tool and small library to split large PDF files into smaller chunks and optionally downsample embedded images.

Quickstart (uv):

```bash
# ensure uv is installed (user already has uv v0.8.11)
uv lock
uv sync
``` 

Run the CLI:

```bash
pdf-chunker input.pdf --out-dir output
```

Or use as a module:

```python
from pdf_chunker import chunk_pdf
chunk_pdf("input.pdf", "output")
```

Note: `pikepdf` requires `qpdf` (native binary). On macOS install with `brew install qpdf`.
