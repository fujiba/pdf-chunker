import importlib


def test_import_pdf_chunker():
    mod = importlib.import_module("pdf_chunker")
    assert hasattr(mod, "__version__")


def test_version_string():
    import pdf_chunker

    v = pdf_chunker.__version__
    assert isinstance(v, str) and v
