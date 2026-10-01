"""Image preprocessing (OpenCV/Pillow) and OCR (Tesseract)."""
import cv2
import pytesseract
from django.conf import settings


class OCRError(Exception):
    pass


def _preprocess(path):
    img = cv2.imread(path)
    if img is None:
        raise OCRError("Please upload a valid JPG, PNG or WEBP image.")
    h, w = img.shape[:2]
    scale = 1800 / max(h, w)  # normalise: upscale small photos, shrink huge ones
    if scale != 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 12)
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)


def extract_text(path):
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    try:
        text = pytesseract.image_to_string(_preprocess(path))
    except OCRError:
        raise
    except Exception:
        raise OCRError("Text could not be extracted. Please upload a clearer image.")
    text = " ".join(text.split()) if len(text.split()) < 8 else "\n".join(l.strip() for l in text.splitlines() if l.strip())
    if len(text) < 25:
        raise OCRError("We couldn't clearly read the uploaded image. Please upload a clearer image.")
    return text[:6000]
