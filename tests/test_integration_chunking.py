import importlib

import pytest

pytest.importorskip("pikepdf")  # skip if pikepdf (native) is not available


def test_chunk_pdf_compresses_and_writes(tmp_path):
    """Create a large single-page PDF (via Pillow), set a tiny MAX_CHUNK_SIZE,
    run chunk_pdf and assert output chunk file is produced.
    """
    # delayed imports so top-level import doesn't require heavy deps
    from PIL import Image

    pdf_chunker = importlib.import_module("pdf_chunker")
    core = importlib.import_module("pdf_chunker.core")

    # create a large image and save as PDF
    img = Image.new("RGB", (3000, 3000), (255, 255, 255))
    input_pdf = tmp_path / "big.pdf"
    img.save(str(input_pdf), format="PDF")

    # force a small chunk size to trigger compress branch but allow compressed output
    old_limit = getattr(core, "MAX_CHUNK_SIZE", None)
    core.MAX_CHUNK_SIZE = 100 * 1024  # 100KB to allow compressed output to fit

    try:
        success = pdf_chunker.chunk_pdf(str(input_pdf), str(tmp_path))
        assert success is True

        # check that at least one output part exists
        parts = list(tmp_path.glob("big_part*.pdf"))
        assert len(parts) >= 1
        # files should be non-empty
        assert any(p.stat().st_size > 0 for p in parts)
    finally:
        # restore
        if old_limit is None:
            delattr(core, "MAX_CHUNK_SIZE")
        else:
            core.MAX_CHUNK_SIZE = old_limit
