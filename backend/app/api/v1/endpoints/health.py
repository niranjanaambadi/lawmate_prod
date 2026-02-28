"""
Health and readiness checks – verify S3 and Bedrock connectivity.
"""
import json
import shutil
import subprocess
from fastapi import APIRouter
from app.core.config import settings
from app.core.logger import logger

router = APIRouter()


def _check_s3() -> tuple[str, str]:
    """Returns (status, detail). Status is 'ok' or 'error'."""
    try:
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        bucket = settings.S3_BUCKET_NAME
        client.head_bucket(Bucket=bucket)
        return "ok", f"Bucket '{bucket}' accessible"
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        return "error", f"S3: {code} - {str(e)}"
    except Exception as e:
        return "error", f"S3: {str(e)}"


def _check_bedrock() -> tuple[str, str]:
    """Returns (status, detail). Status is 'ok' or 'error'."""
    try:
        import boto3

        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        model_id = settings.BEDROCK_MODEL_ID
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 32,
            "temperature": 0,
            "messages": [
                {"role": "user", "content": "Reply with exactly: OK"}
            ],
        })
        response = client.invoke_model(modelId=model_id, body=body)
        response_body = json.loads(response["body"].read())
        text = response_body.get("content", [{}])[0].get("text", "").strip()
        return "ok", f"Bedrock responded: {text[:50]}"
    except Exception as e:
        logger.exception("Bedrock check failed")
        return "error", f"Bedrock: {str(e)}"


def _check_ocr_capabilities() -> dict:
    """
    Runtime capability check for OCR pipeline:
    - tesseract binary
    - Malayalam traineddata (mal)
    - ocrmypdf binary (for PDF/A output)
    - python OCR libs
    """
    result = {
        "status": "ok",
        "tesseract": {"available": False, "version": None, "languages": []},
        "malayalam": {"available": False, "detail": ""},
        "ocrmypdf": {"available": False, "version": None},
        "pythonLibs": {"pytesseract": False, "pillow": False, "pymupdf": False},
    }

    # Python libs
    try:
        import pytesseract  # type: ignore
        result["pythonLibs"]["pytesseract"] = True
    except Exception:
        pass
    try:
        from PIL import Image  # noqa: F401
        result["pythonLibs"]["pillow"] = True
    except Exception:
        pass
    try:
        import fitz  # noqa: F401
        result["pythonLibs"]["pymupdf"] = True
    except Exception:
        pass

    # Tesseract binary and languages
    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        result["tesseract"]["available"] = True
        try:
            ver = subprocess.run(
                ["tesseract", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            first_line = (ver.stdout or "").splitlines()[0] if ver.stdout else ""
            result["tesseract"]["version"] = first_line or "unknown"
        except Exception:
            result["tesseract"]["version"] = "unknown"

        try:
            langs = subprocess.run(
                ["tesseract", "--list-langs"],
                capture_output=True,
                text=True,
                check=False,
            )
            parsed = [line.strip() for line in (langs.stdout or "").splitlines() if line.strip()]
            # first line is usually "List of available languages..."
            cleaned = [line for line in parsed if "List of available languages" not in line]
            result["tesseract"]["languages"] = cleaned
            if "mal" in cleaned:
                result["malayalam"]["available"] = True
                result["malayalam"]["detail"] = "Malayalam traineddata (mal) is installed."
            else:
                result["malayalam"]["detail"] = "Malayalam traineddata (mal) not found."
        except Exception as e:
            result["malayalam"]["detail"] = f"Could not list Tesseract languages: {str(e)}"
    else:
        result["malayalam"]["detail"] = "Tesseract binary not found."

    # OCRmyPDF availability (required for true PDF/A conversion path)
    ocrmypdf_path = shutil.which("ocrmypdf")
    if ocrmypdf_path:
        result["ocrmypdf"]["available"] = True
        try:
            ver = subprocess.run(
                ["ocrmypdf", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            result["ocrmypdf"]["version"] = (ver.stdout or ver.stderr or "").strip() or "unknown"
        except Exception:
            result["ocrmypdf"]["version"] = "unknown"

    has_core_python = (
        result["pythonLibs"]["pytesseract"]
        and result["pythonLibs"]["pillow"]
        and result["pythonLibs"]["pymupdf"]
    )
    has_ocr = result["tesseract"]["available"] and result["malayalam"]["available"] and has_core_python
    result["status"] = "ok" if has_ocr else "degraded"
    result["searchablePdfReady"] = has_ocr
    result["pdfaReady"] = has_ocr and result["ocrmypdf"]["available"]
    return result


@router.get("/ready")
def readiness():
    """
    Check if AWS services are reachable. Use this to verify S3 and Bedrock setup.
    - s3: head_bucket on configured bucket
    - bedrock: minimal invoke_model (single message "Reply with exactly: OK")
    """
    s3_status, s3_detail = _check_s3()
    bedrock_status, bedrock_detail = _check_bedrock()

    healthy = s3_status == "ok" and bedrock_status == "ok"
    return {
        "status": "healthy" if healthy else "degraded",
        "s3": {"status": s3_status, "detail": s3_detail},
        "bedrock": {"status": bedrock_status, "detail": bedrock_detail},
    }


@router.get("/ocr")
def ocr_health():
    """
    Check OCR runtime readiness for Malayalam searchable PDF and PDF/A.
    """
    details = _check_ocr_capabilities()
    return details
