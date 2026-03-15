#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.app.services.pdf_processor import PdfProcessingError, fix_pdf_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unlock and normalize a PDF form to preserve serif font appearance across viewers."
    )
    parser.add_argument("-i", "--input", default="input.pdf", help="Input PDF path (default: input.pdf)")
    parser.add_argument("-o", "--output", default="output.pdf", help="Output PDF path (default: output.pdf)")
    parser.add_argument(
        "--font-resource",
        default="/Times",
        help="AcroForm font resource name (default: /Times)",
    )
    parser.add_argument(
        "--base-font",
        default="/Times-Roman",
        help="Base font to apply (default: /Times-Roman)",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=12,
        help="Font size for default appearance (default: 12)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        fix_pdf_file(
            input_path,
            output_path,
            font_resource_name=args.font_resource,
            base_font=args.base_font,
            font_size=args.font_size,
        )
    except PdfProcessingError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"PDF processed successfully -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
