from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pikepdf
from pikepdf import PasswordError, PdfError


class PdfProcessingError(RuntimeError):
    pass


def _normalize_font_name(name: str) -> str:
    return name if name.startswith("/") else f"/{name}"


def _set_da_recursively(field: pikepdf.Object, da_string: str) -> None:
    field["/DA"] = da_string

    for kid in field.get("/Kids", []):
        _set_da_recursively(kid, da_string)


def _build_times_font_dict(base_font: str) -> pikepdf.Dictionary:
    return pikepdf.Dictionary(Type="/Font", Subtype="/Type1", BaseFont=base_font)


def apply_acroform_serif_defaults(
    pdf: pikepdf.Pdf,
    *,
    font_resource_name: str = "/Times",
    base_font: str = "/Times-Roman",
    font_size: int = 12,
) -> None:
    root = pdf.Root
    acroform = root.get("/AcroForm")

    if acroform is None:
        raise PdfProcessingError("No AcroForm found in PDF.")

    # Ensure viewers use AcroForm fields only.
    if "/XFA" in acroform:
        del acroform["/XFA"]

    if "/DR" not in acroform:
        acroform["/DR"] = pikepdf.Dictionary()

    dr = acroform["/DR"]
    if "/Font" not in dr:
        dr["/Font"] = pikepdf.Dictionary()

    font_resource_name = _normalize_font_name(font_resource_name)
    base_font = _normalize_font_name(base_font)
    dr["/Font"][font_resource_name] = _build_times_font_dict(base_font)

    da_string = f"{font_resource_name} {font_size} Tf 0 g"
    acroform["/DA"] = da_string
    acroform["/NeedAppearances"] = False

    for field in acroform.get("/Fields", []):
        _set_da_recursively(field, da_string)


def fix_pdf_file(
    input_path: Path,
    output_path: Path,
    *,
    font_resource_name: str = "/Times",
    base_font: str = "/Times-Roman",
    font_size: int = 12,
) -> dict[str, str | int | bool]:
    if not input_path.exists() or input_path.stat().st_size == 0:
        raise PdfProcessingError(f"Input file is missing or empty: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        pdf = pikepdf.open(input_path)
    except PasswordError as exc:
        raise PdfProcessingError("PDF is locked with a password that was not provided.") from exc
    except PdfError as exc:
        raise PdfProcessingError(f"Could not open PDF: {exc}") from exc

    with pdf:
        apply_acroform_serif_defaults(
            pdf,
            font_resource_name=font_resource_name,
            base_font=base_font,
            font_size=font_size,
        )
        pdf.save(output_path)

    return {
        "input": str(input_path),
        "output": str(output_path),
        "unlocked": True,
    }


def compress_pdf_file(
    input_path: Path,
    output_path: Path,
    *,
    linearize: bool = False,
) -> dict[str, str | int | bool]:
    if not input_path.exists() or input_path.stat().st_size == 0:
        raise PdfProcessingError(f"Input file is missing or empty: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        pdf = pikepdf.open(input_path)
    except PasswordError as exc:
        raise PdfProcessingError("PDF is locked with a password that was not provided.") from exc
    except PdfError as exc:
        raise PdfProcessingError(f"Could not open PDF: {exc}") from exc

    with pdf:
        pdf.save(
            output_path,
            compress_streams=True,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            linearize=linearize,
        )

    return {
        "input": str(input_path),
        "output": str(output_path),
        "compressed": True,
    }


def merge_pdf_files(
    input_paths: Sequence[Path],
    output_path: Path,
) -> dict[str, str | int | bool]:
    if len(input_paths) < 2:
        raise PdfProcessingError("Merge requires at least 2 PDF files.")

    for path in input_paths:
        if not path.exists() or path.stat().st_size == 0:
            raise PdfProcessingError(f"Input file is missing or empty: {path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with pikepdf.Pdf.new() as merged_pdf:
            for input_path in input_paths:
                with pikepdf.open(input_path) as source_pdf:
                    merged_pdf.pages.extend(source_pdf.pages)
            if len(merged_pdf.pages) == 0:
                raise PdfProcessingError("Merge produced an empty PDF.")
            merged_pdf.save(output_path)
    except PasswordError as exc:
        raise PdfProcessingError("One of the PDFs is locked with a password that was not provided.") from exc
    except PdfError as exc:
        raise PdfProcessingError(f"Could not merge PDFs: {exc}") from exc

    return {
        "output": str(output_path),
        "merged": True,
        "inputs_count": len(input_paths),
    }
