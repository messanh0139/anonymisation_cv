import os
import logging
import numpy as np
import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)

if os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

POPPLER_PATH = r"C:\Program Files\poppler\Library\bin" if os.name == "nt" else None

# Configuration Tesseract pour extraction FIDÈLE :
#   --oem 3  : moteur LSTM (le plus précis)
#   --psm 6  : bloc de texte uniforme — préserve l'ordre des lignes
#   preserve_interword_spaces=1 : espaces exacts entre mots conservés
#   tessedit_do_invert=0        : pas d'inversion des couleurs
_TESS_CONFIG = r"--oem 3 --psm 6 -c preserve_interword_spaces=1 -c tessedit_do_invert=0"


class OCRExtractionError(Exception):
    """Erreur liée à l'extraction OCR."""


def _detect_image_quality(image: Image.Image) -> str:
    """
    Évalue la qualité de l'image pour choisir le niveau de prétraitement.
    Retourne : "good" | "medium" | "poor"
    """
    try:
        import cv2
        img_array = np.array(image.convert("L"))
        # Laplacian variance = mesure de netteté
        laplacian_var = cv2.Laplacian(img_array, cv2.CV_64F).var()
        if laplacian_var > 500:
            return "good"
        elif laplacian_var > 100:
            return "medium"
        else:
            return "poor"
    except Exception:
        return "medium"


def _preprocess_image(image: Image.Image) -> Image.Image:
    """
    Prétraitement adaptatif selon la qualité de l'image.

    - Bonne qualité  → simple contraste + netteté (léger)
    - Qualité moyenne → débruitage + contraste + netteté
    - Mauvaise qualité → pipeline complet : redressement + binarisation adaptative

    Ces traitements n'ajoutent/suppriment AUCUN texte —
    ils rendent seulement le texte existant plus lisible pour Tesseract.
    """
    quality = _detect_image_quality(image)
    logger.debug("[OCR] Qualité image détectée : %s", quality)

    if quality == "good":
        # Prétraitement léger
        image = image.convert("L")
        image = ImageEnhance.Contrast(image).enhance(1.2)
        return image

    if quality == "medium":
        # Prétraitement standard
        image = image.convert("L")
        image = ImageEnhance.Contrast(image).enhance(1.3)
        image = image.filter(ImageFilter.SHARPEN)
        return image

    # Mauvaise qualité → pipeline OpenCV complet
    try:
        import cv2
        img_array = np.array(image.convert("L"))

        # 1. Débruitage (supprime le bruit de fond sans affecter le texte)
        denoised = cv2.fastNlMeansDenoising(img_array, h=10)

        # 2. Redressement automatique (deskew) — corrige l'inclinaison du scan
        coords = np.column_stack(np.where(denoised < 128))
        if len(coords) > 100:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = 90 + angle
            if abs(angle) > 0.5:
                (h, w) = denoised.shape
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                denoised = cv2.warpAffine(denoised, M, (w, h),
                                          flags=cv2.INTER_CUBIC,
                                          borderMode=cv2.BORDER_REPLICATE)
                logger.debug("[OCR] Redressement : %.1f°", angle)

        # 3. Binarisation adaptative (noir/blanc net, résiste aux ombres)
        binary = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 10
        )

        return Image.fromarray(binary)

    except ImportError:
        # Fallback sans OpenCV
        image = image.convert("L")
        image = ImageEnhance.Contrast(image).enhance(1.5)
        image = image.filter(ImageFilter.SHARPEN)
        return image
    except Exception as e:
        logger.warning("[OCR] Prétraitement avancé échoué : %s", e)
        return image.convert("L")


def extract_text_with_ocr(file_path: str) -> str:
    """
    Extrait le texte d'un PDF scanné via Tesseract OCR.

    Principe : extraction FIDÈLE — Tesseract lit ce qui est écrit
    sans corriger, sans ajouter, sans supprimer de contenu.
    Le prétraitement image améliore la lisibilité sans modifier le contenu.
    """
    try:
        images = convert_from_path(file_path, dpi=300, poppler_path=POPPLER_PATH)
        pages_text = []

        for i, image in enumerate(images):
            # Prétraitement pour améliorer la qualité de reconnaissance
            processed = _preprocess_image(image)

            text = pytesseract.image_to_string(
                processed,
                lang="fra+eng",
                config=_TESS_CONFIG,
            ).strip()

            if text:
                pages_text.append(text)
                logger.debug("[OCR] Page %d → %d chars", i + 1, len(text))

        full_text = "\n".join(pages_text).strip()

        if not full_text:
            raise OCRExtractionError("Aucun texte OCR extrait.")

        return full_text

    except OCRExtractionError:
        raise
    except Exception as exc:
        raise OCRExtractionError(f"Erreur OCR : {exc}") from exc



# import os
# import pytesseract
# from pdf2image import convert_from_path


# if os.name == "nt":
#     pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# class OCRExtractionError(Exception):
#     """Erreur liée à l'extraction OCR."""


# def extract_text_with_ocr(file_path: str) -> str:
#     try:
#         images = convert_from_path(file_path, dpi=300)
#         pages_text = []

#         for image in images:
#             text = pytesseract.image_to_string(image, lang="eng+fra").strip()
#             if text:
#                 pages_text.append(text)

#         full_text = "\n".join(pages_text).strip()

#         if not full_text:
#             raise OCRExtractionError("Aucun texte OCR extrait.")

#         return full_text

#     except Exception as exc:
#         raise OCRExtractionError(f"Erreur OCR : {exc}") from exc