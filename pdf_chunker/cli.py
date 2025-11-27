import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="pdf-chunker", description="Split large PDFs into smaller chunks"
    )
    parser.add_argument("input_pdf", help="Input PDF file path")
    parser.add_argument(
        "output_dir", nargs="?", default=None, help="Output directory (optional)"
    )
    args = parser.parse_args(argv)

    # Import here to avoid requiring heavy dependencies at module import time
    from .core import chunk_pdf

    success = chunk_pdf(args.input_pdf, args.output_dir)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
