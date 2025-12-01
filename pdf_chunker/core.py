import io
import logging
import os

from pikepdf import Pdf

from .images import process_page_images

logger = logging.getLogger(__name__)

# Default setting (4MB)
DEFAULT_CHUNK_SIZE = 4.0 * 1024 * 1024
DEFAULT_IMAGE_MAX_DIM = 1500


def get_pdf_size(pdf_obj):
    """Write to memory and return size in bytes."""
    temp = io.BytesIO()
    pdf_obj.save(temp)
    return temp.tell()


def chunk_pdf(
    input_path,
    output_dir=None,
    max_chunk_size=DEFAULT_CHUNK_SIZE,
    image_max_dim=DEFAULT_IMAGE_MAX_DIM,
    save_callback=None,
):
    """
    Split a PDF into chunks.

    Args:
        input_path (str): Path to the source PDF.
        output_dir (str, optional): Directory to save chunks. Defaults to input dir.
        max_chunk_size (int, optional): Max size in bytes per chunk. Defaults to 4MB.
        image_max_dim (int, optional): Max dimension for images. Defaults to 1500px.
        save_callback (callable, optional): Function to handle saving.
                                          Signature: (pdf_obj: pikepdf.Pdf, filename: str) -> None
                                          If provided, files are NOT saved to disk automatically.
    """
    if not os.path.exists(input_path):
        logger.error(f"File not found: {input_path}")
        raise FileNotFoundError(f"Error: File not found: {input_path}")

    if output_dir is None:
        output_dir = os.path.dirname(input_path) or "."

    if not save_callback:
        os.makedirs(output_dir, exist_ok=True)

    src_pdf = Pdf.open(input_path)
    base_name, ext = os.path.splitext(os.path.basename(input_path))

    current_chunk = Pdf.new()
    chunk_count = 1

    logger.info(f"Processing: {input_path}")
    logger.info(f"  - Pages: {len(src_pdf.pages)}")
    logger.info(f"  - Max Chunk Size: {max_chunk_size / 1024 / 1024:.2f} MB")
    logger.info(f"  - Image Max Dim: {image_max_dim} px")

    def save_chunk(chunk, suffix=""):
        nonlocal chunk_count
        output_filename = f"{base_name}_part{chunk_count:02d}{ext}"

        if save_callback:
            logger.info(f"  -> Handing over to callback: {output_filename} {suffix}")
            save_callback(chunk, output_filename)
        else:
            output_path = os.path.join(output_dir, output_filename)
            chunk.save(output_path)
            logger.info(f"  -> Saved: {output_path} {suffix}")

        chunk_count += 1

    pages = src_pdf.pages
    i = 0
    total_pages = len(pages)

    while i < total_pages:
        page = pages[i]

        process_page_images(src_pdf, page, max_dim=image_max_dim)

        current_chunk.pages.append(page)
        current_size = get_pdf_size(current_chunk)

        if current_size > max_chunk_size:
            if len(current_chunk.pages) > 1:
                del current_chunk.pages[-1]

                logger.info(
                    f"  [Limit Reached] Chunk size: {get_pdf_size(current_chunk) / 1024 / 1024:.2f}MB at Page {i}"
                )
                save_chunk(current_chunk)

                current_chunk = Pdf.new()
                continue
            else:
                logger.warning(
                    f"  [Warning] Page {i + 1} is single & huge ({current_size / 1024 / 1024:.2f}MB) even after optimization."
                )

                save_chunk(current_chunk, suffix="(Large)")

                current_chunk = Pdf.new()
                i += 1
        else:
            i += 1

    if len(current_chunk.pages) > 0:
        save_chunk(current_chunk, suffix="(Final)")

    return True
