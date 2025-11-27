import io
import os

from pikepdf import Pdf

from .images import process_page_images

# 4.0MB limit (a bit of headroom)
MAX_CHUNK_SIZE = 4.0 * 1024 * 1024


def get_pdf_size(pdf_obj):
    """Write to memory and return size in bytes."""
    temp = io.BytesIO()
    pdf_obj.save(temp)
    return temp.tell()


def chunk_pdf(input_path, output_dir=None):
    if not os.path.exists(input_path):
        print(f"Error: File not found: {input_path}")
        return False

    if output_dir is None:
        output_dir = os.path.dirname(input_path) or "."

    os.makedirs(output_dir, exist_ok=True)

    src_pdf = Pdf.open(input_path)
    base_name, ext = os.path.splitext(os.path.basename(input_path))

    current_chunk = Pdf.new()
    chunk_count = 1

    print(f"Processing: {input_path} ({len(src_pdf.pages)} pages)")

    pages = src_pdf.pages
    i = 0
    total_pages = len(pages)

    while i < total_pages:
        page = pages[i]
        current_chunk.pages.append(page)
        current_size = get_pdf_size(current_chunk)

        if current_size > MAX_CHUNK_SIZE:
            print(
                f"  [Limit Reached] Chunk size: {current_size / 1024 / 1024:.2f}MB at Page {i + 1}"
            )

            if len(current_chunk.pages) > 1:
                del current_chunk.pages[-1]
                output_filename = f"{base_name}_part{chunk_count:02d}{ext}"
                output_name = os.path.join(output_dir, output_filename)
                current_chunk.save(output_name)
                print(f"  -> Saved: {output_name}")
                chunk_count += 1
                current_chunk = Pdf.new()
                continue

            else:
                print(
                    f"  [Compressing] Page {i + 1} is single & huge. Downsampling images..."
                )
                target_page = current_chunk.pages[0]
                process_page_images(current_chunk, target_page)
                compressed_size = get_pdf_size(current_chunk)
                print(f"  -> Compressed size: {compressed_size / 1024 / 1024:.2f}MB")

                if compressed_size > MAX_CHUNK_SIZE:
                    print(
                        f"  [Error] Failed to compress the page under the size limit ({MAX_CHUNK_SIZE / 1024 / 1024:.2f}MB)."
                    )
                    print("  Aborting process for this file.")
                    return False

                output_filename = f"{base_name}_part{chunk_count:02d}{ext}"
                output_name = os.path.join(output_dir, output_filename)
                current_chunk.save(output_name)
                print(f"  -> Saved (Compressed): {output_name}")
                chunk_count += 1
                current_chunk = Pdf.new()
                i += 1
        else:
            i += 1

    if len(current_chunk.pages) > 0:
        output_filename = f"{base_name}_part{chunk_count:02d}{ext}"
        output_name = os.path.join(output_dir, output_filename)
        current_chunk.save(output_name)
        print(f"  -> Saved (Final): {output_name}")

    return True
