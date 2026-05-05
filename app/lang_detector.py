"""
lang_detector.py
────────────────
Détection automatique de la langue d'un CV.
Utilise langdetect avec fallback heuristique FR/EN.
"""
from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)

# Mots très fréquents FR/EN pour le fallback heuristique
_FR_WORDS = re.compile(r'\b(le|la|les|de|du|des|et|en|un|une|pour|avec|dans|sur|par|je|mon|ma|mes|notre|votre)\b', re.I)
_EN_WORDS = re.compile(r'\b(the|and|of|to|in|a|for|with|on|at|by|my|our|your|is|are|was|were|have|has)\b', re.I)


def detect_language(text: str) -> str:
    """
    Détecte la langue dominante du texte.

    Returns:
        Code ISO 639-1 : "fr", "en", ou autre code ("de", "es"...)
        Retourne "en" par défaut si la détection échoue.
    """
    if not text or len(text.strip()) < 20:
        return "en"

    # Essayer langdetect (statistique, précis)
    try:
        from langdetect import detect, LangDetectException
        sample = text[:3000].replace("\n", " ")
        lang = detect(sample)
        logger.debug("[LANG] Langue détectée : %s", lang)
        return lang
    except Exception:
        pass

    # Fallback heuristique FR vs EN par fréquence de mots
    sample = text[:2000].lower()
    fr_count = len(_FR_WORDS.findall(sample))
    en_count = len(_EN_WORDS.findall(sample))

    if fr_count > en_count:
        return "fr"
    return "en"
