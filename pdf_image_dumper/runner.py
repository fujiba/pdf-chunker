import argparse
import os
import sys

# heavy dependency (pikepdf) はここでインポート
try:
    from pikepdf import Name, Pdf, PdfImage
except ImportError:
    print("Error: pikepdf library is not installed.")
    print("Please install it: pip install pikepdf")
    sys.exit(1)


def _detect_jpeg_app_markers(data: bytes):
    """Detect JPEG APPn markers in raw JPEG bytes.

    Returns list of strings like 'APP0:JFIF', 'APP1:Exif' or 'APP1:...' for found markers.
    If data is not a JPEG or no APP markers found, returns empty list.
    """
    markers = []
    if not data or len(data) < 4:
        return markers
    # JPEG SOI
    if not (data[0] == 0xFF and data[1] == 0xD8):
        return markers

    pos = 2
    L = len(data)
    while pos + 1 < L:
        # find 0xFF
        if data[pos] != 0xFF:
            pos += 1
            continue
        # marker byte
        if pos + 1 >= L:
            break
        marker = data[pos + 1]
        pos += 2

        # End of image
        if marker == 0xD9:
            break
        # Start of scan - image data until EOI; stop parsing markers
        if marker == 0xDA:
            break

        # For markers that have a length field
        if pos + 1 >= L:
            break
        seglen = (data[pos] << 8) | data[pos + 1]
        payload_start = pos + 2
        payload_end = payload_start + max(0, seglen - 2)

        if 0xE0 <= marker <= 0xEF:
            # APPn marker
            payload = (
                data[payload_start:payload_end]
                if payload_end <= L
                else data[payload_start:]
            )
            # try to get a short identifier
            ident = b""
            if payload:
                # prefix until first NUL or up to 32 bytes
                ident = payload[:32].split(b"\x00", 1)[0]
            try:
                ident_s = ident.decode("ascii", errors="replace")
            except Exception:
                ident_s = ""
            markers.append(f"APP{marker - 0xE0}:{ident_s}")

        pos = payload_end

    return markers


def analyze_pdf_images(pdf_path):
    """指定されたPDFファイル内の全画像情報を抽出して表示する。"""
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        return

    print(f"\n--- Analyzing PDF: {pdf_path} ---")

    try:
        with Pdf.open(pdf_path) as pdf:
            total_images = 0
            # Collect rows for table output
            headers = [
                "Page",
                "Name",
                "Width",
                "Height",
                "Size (bytes)",
                "ColorSpace",
                "Filter",
                "Bits/Comp",
                "APP",
            ]
            rows = []

            for i, page in enumerate(pdf.pages):
                page_images = 0

                # ページ内の全画像をループ
                for name, image_obj in page.images.items():
                    total_images += 1
                    page_images += 1

                    try:
                        # 情報を抽出
                        p_img = PdfImage(image_obj)
                        raw_data = image_obj.read_raw_bytes()

                        # サイズ情報
                        width = p_img.width
                        height = p_img.height

                        # その他の情報
                        colorspace = image_obj.get("/ColorSpace")
                        filter_name = image_obj.get("/Filter")
                        bits_per_component = image_obj.get("/BitsPerComponent", "N/A")

                        # Normalize values for table
                        def _s(x):
                            if x is None:
                                return ""
                            return str(x)

                        # detect APP markers for JPEG images
                        app_list = []
                        try:
                            app_list = _detect_jpeg_app_markers(raw_data)
                        except Exception:
                            app_list = []

                        rows.append(
                            [
                                str(i + 1),
                                _s(name),
                                str(width),
                                str(height),
                                f"{len(raw_data):,}",
                                _s(colorspace),
                                _s(filter_name),
                                _s(bits_per_component),
                                ",".join(app_list),
                            ]
                        )

                    except Exception as e:
                        rows.append(
                            [
                                str(i + 1),
                                _s(name),
                                "ERR",
                                "ERR",
                                "ERR",
                                "ERR",
                                "ERR",
                                str(e),
                                "",
                            ]
                        )

                if page_images > 0:
                    # keep a short per-page note in output
                    pass

                # Print table
                def _print_table(headers, rows):
                    # calculate column widths
                    cols = (
                        list(zip(*([headers] + rows)))
                        if rows
                        else [[h] for h in headers]
                    )
                    widths = [max(len(str(v)) for v in col) for col in cols]

                    # decide which columns are numeric and should be right-aligned
                    # Right-align: Page, Width, Height, Size (bytes)
                    numeric_cols = set()
                    for idx, h in enumerate(headers):
                        if h in ("Page", "Width", "Height", "Size (bytes)"):
                            numeric_cols.add(idx)

                    # header
                    header_cells = []
                    for idx, (h, w) in enumerate(zip(headers, widths)):
                        header_cells.append(
                            h.rjust(w) if idx in numeric_cols else h.ljust(w)
                        )
                    header_line = " | ".join(header_cells)
                    sep_line = "-+-".join("-" * w for w in widths)
                    print(header_line)
                    print(sep_line)

                    for r in rows:
                        cells = []
                        for idx, (c, w) in enumerate(zip(r, widths)):
                            s = str(c)
                            cells.append(
                                s.rjust(w) if idx in numeric_cols else s.ljust(w)
                            )
                        print(" | ".join(cells))

            if rows:
                _print_table(headers, rows)

            print(f"--- Analysis Complete: Total {total_images} image(s) found. ---")

    except Exception as e:
        print(f"Critical Error opening or processing PDF: {e}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="pdf-image-dumper", description="Display image details inside a PDF file."
    )
    parser.add_argument("input_pdf", help="Input PDF file path to analyze.")

    args = parser.parse_args(argv)
    analyze_pdf_images(args.input_pdf)


if __name__ == "__main__":
    main()
