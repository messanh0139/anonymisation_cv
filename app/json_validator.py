"""
json_validator.py
─────────────────
Valide un JSON structuré avant la génération PDF.
Détecte les problèmes courants et les corrige quand c'est possible.
"""
from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r'\b(19|20)\d{2}\b')


def validate_and_fix(data: dict) -> tuple[dict, list[str]]:
    """
    Valide et corrige le JSON structuré.

    Returns:
        (data_corrigé, liste_avertissements)
    """
    warnings: list[str] = []

    # ── Champs obligatoires ──────────────────────────────────────
    if not data.get("candidate_id"):
        warnings.append("candidate_id manquant")
        data["candidate_id"] = "UNKNOWN"

    if not data.get("sections"):
        warnings.append("Aucune section trouvée dans le JSON")
        data["sections"] = []

    # ── Nettoyer les sections ────────────────────────────────────
    cleaned_sections = []
    for sec in data.get("sections", []):
        theme = (sec.get("theme") or "").strip()
        lines = [l.strip() for l in sec.get("lines", []) if l and l.strip()]

        # Ignorer les sections vides
        if not lines:
            warnings.append(f"Section vide ignorée : {repr(theme)}")
            continue

        # Limiter les lignes trop longues (artefact OCR)
        fixed_lines = []
        for line in lines:
            if len(line) > 500:
                warnings.append(f"Ligne tronquée (>{500} chars) dans {repr(theme)}")
                line = line[:500]
            fixed_lines.append(line)

        cleaned_sections.append({"theme": theme, "lines": fixed_lines})

    data["sections"] = cleaned_sections

    # ── Vérifier qu'il y a au moins une section utile ────────────
    non_empty = [s for s in cleaned_sections if s["lines"]]
    if not non_empty:
        warnings.append("Toutes les sections sont vides après nettoyage")

    # ── Vérifier le texte anonymisé ──────────────────────────────
    anon_text = data.get("final_anonymized_text", "")
    if not anon_text or len(anon_text.strip()) < 50:
        warnings.append("Texte anonymisé vide ou trop court")

    if warnings:
        logger.warning(
            "[VALID] %s — %d avertissement(s) : %s",
            data.get("candidate_id", "?"),
            len(warnings),
            "; ".join(warnings),
        )
    else:
        logger.info("[VALID] %s — JSON valide ✓", data.get("candidate_id", "?"))

    return data, warnings
