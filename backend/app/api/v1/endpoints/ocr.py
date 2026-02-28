import io
import shutil
import subprocess
import tempfile
from datetime import datetime

import fitz
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import Case, Document, User
from app.core.logger import logger

try:
    import pytesseract
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime dependency
    pytesseract = None
    Image = None

router = APIRouter()

PAGE_BREAK = "\n\n<<<PAGE_BREAK>>>\n\n"


def _normalize_lang(language: str | None) -> str:
    if not language:
        return "mal+eng"
    value = language.strip().lower().replace(",", "+").replace(" ", "")
    return value or "mal+eng"


def _is_pdf(file: UploadFile) -> bool:
    content_type = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    return "pdf" in content_type or name.endswith(".pdf")


def _extract_pdf_native_text(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [(page.extract_text() or "").strip() for page in reader.pages]


def _pixmap_to_pil(pix: fitz.Pixmap):
    if Image is None:
        raise RuntimeError("Pillow is not available")
    mode = "RGBA" if pix.alpha else "RGB"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)


def _ocr_pdf_pages(pdf_bytes: bytes, language: str) -> list[str]:
    if pytesseract is None or Image is None:
        raise RuntimeError("pytesseract/Pillow not installed")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_texts: list[str] = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = _pixmap_to_pil(pix)
        text = pytesseract.image_to_string(image, lang=language).strip()
        page_texts.append(text)
    doc.close()
    return page_texts


def _ocr_image(image_bytes: bytes, language: str) -> str:
    if pytesseract is None or Image is None:
        raise RuntimeError("pytesseract/Pillow not installed")
    image = Image.open(io.BytesIO(image_bytes))
    return pytesseract.image_to_string(image, lang=language).strip()


def _extract_page_texts(file_bytes: bytes, is_pdf: bool, language: str, force_ocr: bool) -> tuple[list[str], str]:
    if is_pdf:
        native_pages = _extract_pdf_native_text(file_bytes)
        has_native_text = any(bool(t.strip()) for t in native_pages)

        if has_native_text and not force_ocr:
            return native_pages, "native-pdf-text"

        try:
            ocr_pages = _ocr_pdf_pages(file_bytes, language)
            if has_native_text:
                merged = [ocr_pages[i] if ocr_pages[i].strip() else native_pages[i] for i in range(len(native_pages))]
                return merged, "tesseract+native-fallback"
            return ocr_pages, "tesseract"
        except RuntimeError as exc:
            if has_native_text:
                return native_pages, "native-pdf-text"
            raise HTTPException(
                status_code=500,
                detail=(
                    "OCR engine unavailable. Install Tesseract + Malayalam trained data and pytesseract. "
                    f"Runtime error: {str(exc)}"
                ),
            )

    try:
        return [_ocr_image(file_bytes, language)], "tesseract"
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Image OCR requires Tesseract + Malayalam trained data (mal) and pytesseract. "
                f"Runtime error: {str(exc)}"
            ),
        )


def _render_overlay(page_width: float, page_height: float, text: str) -> PdfReader:
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    text_obj = can.beginText(12, max(page_height - 20, 20))
    text_obj.setFont("Helvetica", 9)
    text_obj.setLeading(11)
    if hasattr(text_obj, "setTextRenderMode"):
        text_obj.setTextRenderMode(3)  # invisible text layer for search
    else:
        can.setFillColorRGB(1, 1, 1)

    safe_text = (text or "").replace("\r", "\n")
    for line in safe_text.split("\n"):
        text_obj.textLine(line[:1000])

    can.drawText(text_obj)
    can.save()
    packet.seek(0)
    return PdfReader(packet)


def _create_searchable_pdf_from_pdf(pdf_bytes: bytes, page_texts: list[str]) -> bytes:
    original_pdf = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    for i, page in enumerate(original_pdf.pages):
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        overlay_reader = _render_overlay(page_width, page_height, page_texts[i] if i < len(page_texts) else "")
        page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _create_searchable_pdf_from_image(image_bytes: bytes, text: str) -> bytes:
    if Image is None:
        raise HTTPException(status_code=500, detail="Pillow is required for image OCR.")
    image = Image.open(io.BytesIO(image_bytes))
    width, height = image.size

    output = io.BytesIO()
    can = canvas.Canvas(output, pagesize=(width, height))
    can.drawImage(ImageReader(io.BytesIO(image_bytes)), 0, 0, width=width, height=height)

    text_obj = can.beginText(12, max(height - 20, 20))
    text_obj.setFont("Helvetica", 9)
    text_obj.setLeading(11)
    if hasattr(text_obj, "setTextRenderMode"):
        text_obj.setTextRenderMode(3)
    else:
        can.setFillColorRGB(1, 1, 1)

    for line in (text or "").replace("\r", "\n").split("\n"):
        text_obj.textLine(line[:1000])
    can.drawText(text_obj)
    can.showPage()
    can.save()
    output.seek(0)
    return output.read()


def _convert_to_pdfa_if_available(pdf_bytes: bytes, language: str) -> tuple[bytes, bool]:
    ocrmypdf_path = shutil.which("ocrmypdf")
    if not ocrmypdf_path:
        return pdf_bytes, False

    with tempfile.TemporaryDirectory() as tmp_dir:
        input_path = f"{tmp_dir}/input.pdf"
        output_path = f"{tmp_dir}/output-pdfa.pdf"
        with open(input_path, "wb") as f:
            f.write(pdf_bytes)

        cmd = [
            ocrmypdf_path,
            "--output-type",
            "pdfa",
            "--skip-text",
            "--language",
            language,
            input_path,
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logger.warning("ocrmypdf failed, returning regular searchable PDF: %s", proc.stderr)
            return pdf_bytes, False

        with open(output_path, "rb") as f:
            return f.read(), True


def _run_ocrmypdf(
    file_bytes: bytes,
    source_ext: str,
    language: str,
    output_type: str,
    force_ocr: bool,
) -> tuple[bytes, int | None]:
    """
    Use OCRmyPDF as primary searchable PDF/PDF-A generation engine.
    This produces a standards-compliant OCR text layer with proper Unicode mapping.
    """
    ocrmypdf_path = shutil.which("ocrmypdf")
    if not ocrmypdf_path:
        raise RuntimeError("ocrmypdf is not installed")

    with tempfile.TemporaryDirectory() as tmp_dir:
        input_ext = source_ext if source_ext.startswith(".") else f".{source_ext}"
        input_path = f"{tmp_dir}/input{input_ext}"
        output_path = f"{tmp_dir}/output.pdf"

        with open(input_path, "wb") as f:
            f.write(file_bytes)

        cmd = [
            ocrmypdf_path,
            "--language",
            language,
            "--output-type",
            "pdfa" if output_type == "pdfa" else "pdf",
            "--jobs",
            "2",
            "--optimize",
            "0",
            "--oversample",
            "300",
        ]
        # For raw images (png/jpg/tiff), OCRmyPDF needs explicit DPI when metadata is missing.
        image_dpi_used: int | None = None
        if input_ext != ".pdf":
            image_dpi = None
            try:
                if Image is not None:
                    with Image.open(io.BytesIO(file_bytes)) as img:
                        dpi = img.info.get("dpi")
                        if isinstance(dpi, tuple) and dpi and dpi[0]:
                            image_dpi = int(dpi[0])
                        elif isinstance(dpi, (int, float)):
                            image_dpi = int(dpi)
                        # If missing/invalid, estimate DPI from width to keep natural page size.
                        # Example: 618px => ~75 DPI -> close to letter/A4 width in PDF viewers.
                        if not image_dpi or image_dpi < 30 or image_dpi > 1200:
                            est = int(round(img.width / 8.27)) if img.width > 0 else 96
                            image_dpi = max(72, min(est, 300))
            except Exception:
                image_dpi = 96
            image_dpi_used = max(image_dpi or 96, 72)
            cmd.extend(["--image-dpi", str(image_dpi_used)])

        if force_ocr:
            cmd.append("--force-ocr")
        else:
            cmd.append("--skip-text")
        cmd.extend([input_path, output_path])

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "ocrmypdf failed").strip())

        with open(output_path, "rb") as f:
            return f.read(), image_dpi_used


def _searchability_stats(pdf_bytes: bytes) -> tuple[int, int]:
    """
    Returns (total_pages, pages_with_extractable_text).
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total = len(reader.pages)
    text_pages = 0
    for page in reader.pages:
        if (page.extract_text() or "").strip():
            text_pages += 1
    return total, text_pages


@router.post("/extract")
async def extract_text(
    file: UploadFile = File(...),
    language: str = Form("mal+eng"),
    force_ocr: bool = Form(False),
    current_user: User = Depends(get_current_user),
):
    try:
        contents = await file.read()
        page_texts, engine = _extract_page_texts(
            file_bytes=contents,
            is_pdf=_is_pdf(file),
            language=_normalize_lang(language),
            force_ocr=force_ocr,
        )
        return {
            "text": PAGE_BREAK.join(page_texts),
            "pageTexts": page_texts,
            "pages": len(page_texts),
            "language": _normalize_lang(language),
            "ocrEngine": engine,
            "pageBreakToken": PAGE_BREAK.strip(),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/create-searchable-pdf")
async def create_searchable_pdf(
    file: UploadFile = File(...),
    text: str | None = Form(None),
    language: str = Form("mal+eng"),
    output_format: str = Form("pdf"),
    force_ocr: bool = Form(False),
    current_user: User = Depends(get_current_user),
):
    """
    Create searchable PDF by adding invisible OCR text layer.
    - Supports PDF/image upload
    - Malayalam via language=eng+mal
    - PDF/A output if ocrmypdf is installed and output_format=pdfa
    """
    try:
        file_bytes = await file.read()
        is_pdf = _is_pdf(file)
        normalized_lang = _normalize_lang(language)
        format_normalized = output_format.strip().lower()
        requested_format = "pdfa" if format_normalized == "pdfa" else "pdf"
        source_name = (file.filename or "").lower()
        source_ext = ".pdf" if is_pdf else (
            ".png" if source_name.endswith(".png")
            else ".jpg" if source_name.endswith(".jpg") or source_name.endswith(".jpeg")
            else ".tif" if source_name.endswith(".tif") or source_name.endswith(".tiff")
            else ".png"
        )

        # Preferred path: OCRmyPDF (reliable searchable text layer for Malayalam/English).
        ocrmypdf_available = shutil.which("ocrmypdf") is not None
        try:
            final_pdf = _run_ocrmypdf(
                file_bytes=file_bytes,
                source_ext=source_ext,
                language=normalized_lang,
                output_type=requested_format,
                force_ocr=force_ocr,
            )
            final_pdf, image_dpi_used = final_pdf
            filename = "searchable-pdfa.pdf" if requested_format == "pdfa" else "searchable.pdf"
            pdf_format_header = requested_format
            ocr_engine_header = "ocrmypdf"
            page_count, text_page_count = _searchability_stats(final_pdf)
        except Exception as ocrmypdf_error:
            if ocrmypdf_available:
                # If OCRmyPDF exists but fails, fail loudly so we can fix infra/runtime.
                raise HTTPException(
                    status_code=500,
                    detail=f"OCRmyPDF failed during searchable generation: {str(ocrmypdf_error)}",
                )
            logger.warning("ocrmypdf not installed; using fallback overlay engine.")

            # Fallback path: existing overlay-based generation.
            if text and text.strip():
                page_texts = [p.strip() for p in text.split(PAGE_BREAK)]
            else:
                page_texts, _engine = _extract_page_texts(
                    file_bytes=file_bytes,
                    is_pdf=is_pdf,
                    language=normalized_lang,
                    force_ocr=force_ocr,
                )

            if is_pdf:
                searchable_pdf = _create_searchable_pdf_from_pdf(file_bytes, page_texts)
            else:
                searchable_pdf = _create_searchable_pdf_from_image(file_bytes, page_texts[0] if page_texts else "")

            filename = "searchable.pdf"
            pdf_format_header = "pdf"
            final_pdf = searchable_pdf
            ocr_engine_header = "fallback-overlay"
            image_dpi_used = None
            page_count, text_page_count = _searchability_stats(final_pdf)
            if requested_format == "pdfa":
                final_pdf, is_pdfa = _convert_to_pdfa_if_available(searchable_pdf, normalized_lang)
                filename = "searchable-pdfa.pdf" if is_pdfa else "searchable.pdf"
                pdf_format_header = "pdfa" if is_pdfa else "pdf"
                page_count, text_page_count = _searchability_stats(final_pdf)

        # Hard guard: generated file must be searchable for at least one page.
        if text_page_count == 0:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Generated PDF is not searchable (0 extractable text pages). "
                    f"engine={ocr_engine_header}, format={pdf_format_header}"
                ),
            )

        return StreamingResponse(
            io.BytesIO(final_pdf),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-PDF-Format": pdf_format_header,
                "X-OCR-Language": normalized_lang,
                "X-OCR-Pages": str(max(page_count, 1)),
                "X-OCR-Engine": ocr_engine_header,
                "X-OCR-Text-Pages": str(text_page_count),
                "X-OCR-Searchable": "true" if text_page_count > 0 else "false",
                "X-Image-DPI": str(image_dpi_used or ""),
            },
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/save-to-case")
async def save_to_case(
    file: UploadFile = File(...),
    text: str = Form(...),
    case_id: str = Form(...),
    format: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Saves OCR document to case"""
    # Verify case ownership
    case = db.query(Case).filter(
        Case.id == case_id,
        Case.advocate_id == current_user.id
    ).first()
    
    if not case:
        raise HTTPException(404, "Case not found")
    
    # Generate S3 key
    filename = f"ocr_{datetime.utcnow().timestamp()}_{file.filename}"
    s3_key = f"{case.efiling_number}/ocr/{filename}"
    
    # Create document or searchable PDF based on format
    if format == "searchable_pdf":
        # Use create_searchable_pdf logic, upload to S3
        pass  # TODO: S3 upload
    else:
        # Save as txt to S3
        pass  # TODO: S3 upload
    
    # Save metadata
    doc = Document(
        case_id=case_id,
        khc_document_id=f"OCR_{datetime.utcnow().timestamp()}",
        category="misc",
        title=f"OCR - {file.filename}",
        s3_key=s3_key,
        file_size=len(text.encode()),
        upload_status="completed"
    )
    db.add(doc)
    db.commit()
    
    return {"message": "Saved successfully", "document_id": str(doc.id)}
