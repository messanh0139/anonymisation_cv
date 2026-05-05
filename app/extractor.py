"""
extractor.py

Extraction de texte FIDÈLE depuis un PDF — stratégie "Best-of-Two" :
  1. Extraction native  (PyMuPDF/fitz) — préserve l'ordre exact du texte
  2. Extraction OCR     (Tesseract)    — pour les CVs scannés / images

PRINCIPE FONDAMENTAL : zéro modification du contenu.
  - Pas d'ajout de mots ou de phrases
  - Pas de suppression de mots ou de phrases
  - Pas d'amélioration ou de correction orthographique
  - Le texte extrait = exactement ce qui est dans le PDF

Les deux méthodes sont TOUJOURS exécutées. Un score de qualité est calculé
pour chacune et la meilleure est retenue. En cas d'égalité (< 5 pts d'écart),
la méthode native est préférée (plus fidèle à la mise en forme originale).

Score de qualité (0–100) :
  +30 pts  longueur brute (plafonné à 5000 chars)
  +20 pts  nombre de mots (plafonné à 300 mots)
  +20 pts  ratio caractères lisibles / total
  +20 pts  ratio mots plausibles (≥ 2 lettres) / total mots
  +10 pts  nombre de lignes non vides (plafonné à 30 lignes)
  −20 pts  pénalité pour caractères parasites
"""

import logging
import re
from pathlib import Path

from pypdf import PdfReader

from app.ocr_extractor import extract_text_with_ocr

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Erreur liée à l'extraction du texte PDF."""


# ── Critères minimaux ─────────────────────────────────────────────────────────
MIN_CHARS = 150
MIN_WORDS = 25
MIN_LINES = 4

_READABLE_RE = re.compile(r'[a-zA-ZÀ-ÿ0-9\s.,;:!?()\-\'\"/@#&+]')
_GARBAGE_RE  = re.compile(r'[^\x20-\x7Eà-ÿÀ-Ÿ\n\t]')


def _score_text(text: str) -> float:
    """Calcule un score de qualité entre 0.0 et 100.0."""
    if not text or not text.strip():
        return 0.0
    stripped     = text.strip()
    total_chars  = len(stripped)
    words        = stripped.split()
    total_words  = len(words)
    lines        = [l for l in stripped.splitlines() if l.strip()]

    score_length    = min(total_chars / 5000, 1.0) * 30
    score_words     = min(total_words / 300,  1.0) * 20
    score_readable  = (len(_READABLE_RE.findall(stripped)) / total_chars) * 20 if total_chars else 0
    plausible       = sum(1 for w in words if re.search(r'[a-zA-ZÀ-ÿ]{2,}', w))
    score_plausible = (plausible / total_words) * 20 if total_words else 0
    score_lines     = min(len(lines) / 30, 1.0) * 10
    penalty_garbage = (len(_GARBAGE_RE.findall(stripped)) / total_chars) * 20 if total_chars else 0

    return round(max(0.0, min(100.0,
        score_length + score_words + score_readable + score_plausible + score_lines - penalty_garbage
    )), 2)


def _is_usable(text: str) -> bool:
    """Vérifie les critères minimaux pour qu'un texte soit exploitable."""
    if not text or not text.strip():
        return False
    stripped = text.strip()
    words = stripped.split()
    lines = [l for l in stripped.splitlines() if l.strip()]
    return len(stripped) >= MIN_CHARS and len(words) >= MIN_WORDS and len(lines) >= MIN_LINES


# ── Détection dynamique du point de séparation entre colonnes ────────────────
def _detect_column_split(text_blocks: list, page_width: float) -> float | None:
    """
    Analyse la distribution horizontale des blocs texte pour détecter
    automatiquement s'il y a 2 colonnes et où se situe leur frontière.

    Couvre tous les layouts :
      - 50/50 (deux colonnes égales)
      - 30/70, 25/75 (sidebar étroite + contenu large)
      - 40/60 (sidebar modérée)

    Retourne :
      - La position X du split (en points) si 2 colonnes détectées
      - None si mise en page 1 colonne

    Algorithme :
      On projette les positions droites (x2) et gauches (x0) des blocs
      sur l'axe horizontal. Un "gap" (zone sans blocs) entre 20% et 80%
      de la largeur de page indique une séparation de colonnes.
    """
    if len(text_blocks) < 4:
        return None

    # Collecter les intervalles horizontaux occupés par chaque bloc
    # Discrétiser la largeur en 200 segments
    resolution = 200
    occupancy = [0] * resolution

    for b in text_blocks:
        x0, _, x2, _ = b[0], b[1], b[2], b[3]
        i0 = max(0, int(x0 / page_width * resolution))
        i2 = min(resolution - 1, int(x2 / page_width * resolution))
        for i in range(i0, i2 + 1):
            occupancy[i] += 1

    # Chercher un gap (zone non occupée) entre 15% et 85% de la largeur
    zone_start = int(0.15 * resolution)
    zone_end   = int(0.85 * resolution)

    # Trouver les positions avec zéro occupation dans la zone centrale
    gap_positions = [i for i in range(zone_start, zone_end) if occupancy[i] == 0]

    if not gap_positions:
        return None

    # Regrouper les positions de gap consécutives en segments
    segments: list[tuple[int, int]] = []
    seg_start = gap_positions[0]
    seg_prev  = gap_positions[0]
    for pos in gap_positions[1:]:
        if pos == seg_prev + 1:
            seg_prev = pos
        else:
            segments.append((seg_start, seg_prev))
            seg_start = seg_prev = pos
    segments.append((seg_start, seg_prev))

    # Garder le plus large segment de gap comme frontière de colonnes
    largest = max(segments, key=lambda s: s[1] - s[0])
    gap_width_pct = (largest[1] - largest[0]) / resolution * 100

    # Gap trop petit (<2% de la page) → probablement pas de vraie séparation
    if gap_width_pct < 2.0:
        return None

    # Point de split = centre du plus grand gap
    split_x = ((largest[0] + largest[1]) / 2.0) / resolution * page_width

    # Vérifier qu'il y a bien du contenu des deux côtés
    left_blocks  = [b for b in text_blocks if b[2] < split_x + 5]
    right_blocks = [b for b in text_blocks if b[0] > split_x - 5]

    if len(left_blocks) < 2 or len(right_blocks) < 2:
        return None

    return split_x


# ── Extraction native fidèle (PyMuPDF) ───────────────────────────────────────
def extract_text_native(file_path: str) -> str:
    """
    Extrait le texte numérique du PDF de façon 100% fidèle via PyMuPDF (fitz).

    PyMuPDF préserve :
      - L'ordre exact de lecture (haut→bas, gauche→droite)
      - Les sauts de ligne d'origine
      - Les espaces entre mots
      - Les caractères spéciaux et Unicode

    Aucune correction, aucun ajout, aucune suppression.
    Fallback sur pypdf si fitz n'est pas disponible.
    """
    path = Path(file_path)
    if not path.exists():
        raise ExtractionError(f"Fichier introuvable : {file_path}")
    if path.suffix.lower() != ".pdf":
        raise ExtractionError(f"Format non supporté : {path.suffix}")

    # ── Tentative avec PyMuPDF (fitz) — extraction la plus fidèle ────────────
    try:
        import fitz  # PyMuPDF
        doc   = fitz.open(str(path))
        pages = []
        for page in doc:
            # Détecter la mise en page multi-colonnes dynamiquement
            blocks = page.get_text("blocks", sort=True)  # blocs texte avec coordonnées
            page_width = page.rect.width

            # Filtrer les blocs ayant du contenu texte réel
            text_blocks = [b for b in blocks if b[4].strip()]

            # Analyser la distribution horizontale des blocs pour trouver
            # le vrai point de séparation (couvre les sidebars 25/75, 30/70, 40/60…)
            col_split = _detect_column_split(text_blocks, page_width)

            if col_split is not None:
                # Mise en page multi-colonnes détectée
                left_blocks  = [b for b in text_blocks if b[2] <= col_split + 5]
                right_blocks = [b for b in text_blocks if b[0] >= col_split - 5]
                left_text  = "\n".join(b[4] for b in sorted(left_blocks,  key=lambda b: b[1]))
                right_text = "\n".join(b[4] for b in sorted(right_blocks, key=lambda b: b[1]))
                text = left_text + "\n" + right_text
                logger.debug("[Native/fitz] Mise en page multi-colonnes détectée (split=%.0f%%)",
                             col_split / page_width * 100)
            else:
                # CV 1 colonne — lecture simple haut→bas
                text = page.get_text("text", sort=True)

            if text.strip():
                pages.append(text)
        doc.close()
        result = "\n".join(pages).strip()
        if result:
            logger.debug("[Native/fitz] %d chars extraits", len(result))
            return result
    except ImportError:
        logger.warning("[Native] PyMuPDF non disponible, fallback sur pypdf")
    except Exception as exc:
        logger.warning("[Native/fitz] Erreur : %s — fallback sur pypdf", exc)

    # ── Fallback : pypdf ──────────────────────────────────────────────────────
    try:
        reader = PdfReader(str(path))
        texts  = [page.extract_text() or "" for page in reader.pages]
        result = "\n".join(t for t in texts if t.strip()).strip()
        if result:
            logger.debug("[Native/pypdf] %d chars extraits", len(result))
            return result
        raise ExtractionError("pypdf n'a extrait aucun texte.")
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Erreur extraction native : {exc}") from exc


# ── Extraction principale : Best-of-Two ───────────────────────────────────────
def extract_text_from_pdf(file_path: str) -> tuple[str, str]:
    """
    Extrait le texte d'un PDF en utilisant TOUJOURS les deux méthodes
    (native + OCR), score chacune et retourne la meilleure.

    Retourne :
        (texte: str, method_used: str)
        method_used ∈ {"native", "ocr"}

    Lève ExtractionError si aucune méthode ne produit un texte exploitable.
    """
    native_text  = ""
    ocr_text     = ""
    native_score = 0.0
    ocr_score    = 0.0
    native_error = ""
    ocr_error    = ""

    # ── 1. Extraction native ──────────────────────────────────────────────────
    try:
        native_text  = extract_text_native(file_path)
        native_score = _score_text(native_text)
        logger.info("[Extraction] Native  → score=%.1f  chars=%d",
                    native_score, len(native_text))
    except ExtractionError as e:
        native_error = str(e)
        logger.warning("[Extraction] Native échouée : %s", native_error)

    # ── 2. Extraction OCR ─────────────────────────────────────────────────────
    try:
        ocr_text  = extract_text_with_ocr(file_path)
        ocr_score = _score_text(ocr_text)
        logger.info("[Extraction] OCR     → score=%.1f  chars=%d",
                    ocr_score, len(ocr_text))
    except Exception as e:
        ocr_error = str(e)
        logger.warning("[Extraction] OCR échouée : %s", ocr_error)

    # ── 3. Comparaison et sélection ───────────────────────────────────────────
    native_ok = _is_usable(native_text)
    ocr_ok    = _is_usable(ocr_text)

    logger.info(
        "[Extraction] Résultat → native=%.1f(%s)  ocr=%.1f(%s)",
        native_score, "✓" if native_ok else "✗",
        ocr_score,    "✓" if ocr_ok    else "✗",
    )

    if native_ok and ocr_ok:
        if native_score >= ocr_score - 5:
            logger.info("[Extraction] → NATIVE choisi (%.1f vs OCR %.1f)",
                        native_score, ocr_score)
            return native_text, "native"
        else:
            logger.info("[Extraction] → OCR choisi (%.1f vs Native %.1f)",
                        ocr_score, native_score)
            return ocr_text, "ocr"

    if native_ok:
        logger.info("[Extraction] → NATIVE choisi (OCR non exploitable)")
        return native_text, "native"

    if ocr_ok:
        logger.info("[Extraction] → OCR choisi (Native non exploitable)")
        return ocr_text, "ocr"

    raise ExtractionError(
        f"Aucune méthode n'a produit un texte exploitable.\n"
        f"  Native : score={native_score:.1f}  {native_error or ''}\n"
        f"  OCR    : score={ocr_score:.1f}  {ocr_error or ''}"
    )


# Rétro-compatibilité
def is_text_quality_sufficient(text: str) -> bool:
    return _is_usable(text)


def extract_text_from_pdf_detailed(file_path: str) -> tuple[str, str, float, float]:
    """
    Variante de extract_text_from_pdf qui retourne aussi les scores.

    Retourne :
        (texte, method_used, score_native, score_ocr)
    """
    native_text  = ""
    ocr_text     = ""
    native_score = 0.0
    ocr_score    = 0.0
    native_error = ""
    ocr_error    = ""

    try:
        native_text  = extract_text_native(file_path)
        native_score = _score_text(native_text)
        logger.info("[Extraction] Native  → score=%.1f  chars=%d", native_score, len(native_text))
    except ExtractionError as e:
        native_error = str(e)
        logger.warning("[Extraction] Native échouée : %s", native_error)

    try:
        ocr_text  = extract_text_with_ocr(file_path)
        ocr_score = _score_text(ocr_text)
        logger.info("[Extraction] OCR     → score=%.1f  chars=%d", ocr_score, len(ocr_text))
    except Exception as e:
        ocr_error = str(e)
        logger.warning("[Extraction] OCR échouée : %s", ocr_error)

    native_ok = _is_usable(native_text)
    ocr_ok    = _is_usable(ocr_text)

    logger.info("[Extraction] Résultat → native=%.1f(%s)  ocr=%.1f(%s)",
                native_score, "✓" if native_ok else "✗",
                ocr_score,    "✓" if ocr_ok    else "✗")

    if native_ok and ocr_ok:
        if native_score >= ocr_score - 5:
            return native_text, "native", native_score, ocr_score
        else:
            return ocr_text, "ocr", native_score, ocr_score

    if native_ok:
        return native_text, "native", native_score, ocr_score

    if ocr_ok:
        return ocr_text, "ocr", native_score, ocr_score

    raise ExtractionError(
        f"Aucune méthode n'a produit un texte exploitable.\n"
        f"  Native : score={native_score:.1f}  {native_error or ''}\n"
        f"  OCR    : score={ocr_score:.1f}  {ocr_error or ''}"
    )

