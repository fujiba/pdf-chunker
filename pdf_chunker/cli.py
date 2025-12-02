import argparse
import logging
import sys


def main(argv=None):
    # Configure logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )

    parser = argparse.ArgumentParser(
        prog="pdf-chunker", description="Split large PDFs into smaller chunks"
    )
    parser.add_argument("input_pdf", help="Input PDF file path")
    parser.add_argument(
        "output_dir", nargs="?", default=None, help="Output directory (optional)"
    )
    parser.add_argument(
        "--max-size",
        type=float,
        default=4.0,
        help="Max chunk size in MB (default: 4.0)",
    )
    parser.add_argument(
        "--image-max-dim",
        type=int,
        default=1500,
        help="Max dimension for images in pixels (default: 1500)",
    )

    args = parser.parse_args(argv)

    # Import here to avoid requiring heavy dependencies at module import time
    from .core import chunk_pdf

    # Convert MB to bytes
    size_in_bytes = int(args.max_size * 1024 * 1024)

    success = chunk_pdf(
        args.input_pdf,
        args.output_dir,
        max_chunk_size=size_in_bytes,
        image_max_dim=args.image_max_dim,
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
