#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pikepdf

SERIF_HINTS = ("times", "timesnewroman")
TF_PATTERN = re.compile(r"/([A-Za-z0-9_.+-]+)\s+[-+]?\d*\.?\d+\s+Tf")


def has_serif_hint(name: str | None) -> bool:
    if not name:
        return False
    normalized = name.strip("/").lower()
    return any(hint in normalized for hint in SERIF_HINTS)


def extract_font_name_from_da(da_value: object) -> str | None:
    match = TF_PATTERN.search(str(da_value))
    if not match:
        return None
    return match.group(1)


def obj_to_text(value: object) -> str:
    try:
        return value.to_unicode()
    except Exception:
        return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate PDF against the client acceptance criteria."
    )
    parser.add_argument("pdf", help="PDF file to validate (e.g. output.pdf)")
    parser.add_argument(
        "--expect-text",
        default=None,
        help="Optional text that should appear in at least one form field value.",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"FAIL: file not found: {pdf_path}")
        return 1

    failures: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    with pikepdf.open(pdf_path) as pdf:
        root = pdf.Root
        acroform = root.get("/AcroForm")

        if pdf.is_encrypted:
            failures.append("PDF is still encrypted/locked.")
        else:
            info.append("PDF is unlocked.")

        if acroform is None:
            failures.append("No /AcroForm dictionary found.")
            print_report(pdf_path, failures, warnings, info)
            return 1
        info.append("AcroForm exists.")

        if "/XFA" in acroform:
            failures.append("/XFA still present in /AcroForm.")
        else:
            info.append("No /XFA in AcroForm.")

        if "/Fields" not in acroform or len(acroform["/Fields"]) == 0:
            failures.append("No AcroForm fields found.")
        else:
            info.append(f"Field count: {len(acroform['/Fields'])}")

        need_appearances = acroform.get("/NeedAppearances") if "/NeedAppearances" in acroform else None
        if need_appearances is True:
            warnings.append(
                "/NeedAppearances is true. Chrome may regenerate appearance using fallback fonts."
            )
        else:
            info.append("/NeedAppearances is not true (better for appearance consistency).")

        dr_fonts = {}
        if "/DR" in acroform and "/Font" in acroform["/DR"]:
            dr_fonts = acroform["/DR"]["/Font"]
            info.append(f"AcroForm /DR /Font entries: {len(dr_fonts)}")
        else:
            warnings.append("AcroForm /DR /Font is missing.")

        dr_has_serif = False
        for font_name, font_obj in dr_fonts.items():
            base_font = str(font_obj["/BaseFont"]) if "/BaseFont" in font_obj else None
            if has_serif_hint(str(font_name)) or has_serif_hint(base_font):
                dr_has_serif = True
        if not dr_has_serif:
            warnings.append("No obvious serif font found in AcroForm /DR /Font.")

        da_non_serif_count = 0
        ap_non_serif_count = 0
        matched_expected_text = False

        fields = acroform["/Fields"] if "/Fields" in acroform else []
        for field in fields:
            nodes = [field]
            if "/Kids" in field:
                nodes.extend(list(field["/Kids"]))

            for node in nodes:
                if "/DA" in node:
                    da_font = extract_font_name_from_da(node["/DA"])
                    if da_font and not has_serif_hint(da_font):
                        da_non_serif_count += 1

                if args.expect_text and "/V" in node:
                    if args.expect_text in obj_to_text(node["/V"]):
                        matched_expected_text = True

                if "/AP" in node and "/N" in node["/AP"]:
                    n_obj = node["/AP"]["/N"]
                    if isinstance(n_obj, pikepdf.Stream):
                        stream_text = n_obj.read_bytes().decode("latin-1", errors="ignore")
                        font_tokens = TF_PATTERN.findall(stream_text)
                        if font_tokens:
                            ap_fonts = {}
                            if "/Resources" in n_obj and "/Font" in n_obj["/Resources"]:
                                ap_fonts = n_obj["/Resources"]["/Font"]
                            for token in font_tokens:
                                font_obj = ap_fonts.get(f"/{token}")
                                base_font = None
                                if font_obj is not None and "/BaseFont" in font_obj:
                                    base_font = str(font_obj["/BaseFont"])
                                if not (has_serif_hint(token) or has_serif_hint(base_font)):
                                    ap_non_serif_count += 1

        if da_non_serif_count > 0:
            failures.append(f"{da_non_serif_count} field/widget /DA entries use non-serif fonts.")
        else:
            info.append("All detected /DA entries use serif-like font names.")

        if ap_non_serif_count > 0:
            warnings.append(
                f"{ap_non_serif_count} appearance-stream font usages are non-serif or unresolved."
            )
        else:
            info.append("All detected appearance-stream fonts are serif-like.")

        if args.expect_text:
            if matched_expected_text:
                info.append(f'Expected text "{args.expect_text}" found in at least one field value.')
            else:
                failures.append(
                    f'Expected text "{args.expect_text}" not found in field values (/V).'
                )

    print_report(pdf_path, failures, warnings, info)
    return 1 if failures else 0


def print_report(path: Path, failures: list[str], warnings: list[str], info: list[str]) -> None:
    print(f"Verification target: {path}")
    print()
    status = "PASS" if not failures else "FAIL"
    print(f"Status: {status}")
    print()

    if failures:
        print("Failures:")
        for item in failures:
            print(f"- {item}")
        print()

    if warnings:
        print("Warnings:")
        for item in warnings:
            print(f"- {item}")
        print()

    if info:
        print("Checks:")
        for item in info:
            print(f"- {item}")


if __name__ == "__main__":
    sys.exit(main())
