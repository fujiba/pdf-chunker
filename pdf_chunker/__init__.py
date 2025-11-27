"""pdf_chunker package

Public API exports live here.
"""

__version__ = "0.1.0"


# Delay importing heavy dependencies (pikepdf) until attributes are accessed.
# This allows `import pdf_chunker` to succeed in minimal environments.
def __getattr__(name):
    if name == "chunk_pdf":
        from .core import chunk_pdf as _chunk_pdf

        return _chunk_pdf
    if name == "__version__":
        return __version__
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["chunk_pdf", "__version__"]
