"""
section_classifier.py
─────────────────────
Classificateur de sections de CV basé sur les embeddings sémantiques.
Remplace (et complète) les regex fragiles de _fuzzy_classify_theme.

Fonctionnement :
  1. Calcule l'embedding du titre de section inconnu
  2. Compare par similarité cosinus avec les embeddings de référence
  3. Si score > threshold → retourne le groupe canonique
  4. Sinon → retourne None (le fallback regex prend le relais)

Le modèle est chargé une seule fois (lazy) et les embeddings de référence
sont mis en cache sur disque pour éviter le recalcul à chaque démarrage.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Groupes canoniques avec leurs labels de référence multilingues ─────────
# Plus il y a de labels variés, plus la classification est robuste.
_REFERENCE_LABELS: dict[str, list[str]] = {
    "resume": [
        "profil", "résumé", "summary", "profile", "objective", "about me",
        "introduction", "career objective", "professional summary",
        "présentation", "aperçu", "overview", "statement",
    ],
    "experience": [
        "expérience professionnelle", "professional experience", "work experience",
        "emplois", "parcours professionnel", "career history", "employment history",
        "work history", "expériences", "postes occupés", "missions",
        "board experience", "volunteer experience", "bénévolat",
        "military service", "freelance", "consulting experience",
        "internship experience", "stage", "career highlights",
    ],
    "education": [
        "formation", "education", "études", "diplômes", "academic background",
        "qualifications", "degrees", "scolarité", "parcours académique",
        "academic training", "educational background", "cursus",
    ],
    "skills": [
        "compétences techniques", "technical skills", "hard skills",
        "skills", "expertise", "outils", "tools", "technologies",
        "technical background", "areas of expertise", "technical proficiency",
        "stack technique", "compétences informatiques", "savoir-faire technique",
    ],
    "soft_skills": [
        "soft skills", "qualités personnelles", "interpersonal skills",
        "personal attributes", "core strengths", "strengths", "personal strengths",
        "compétences comportementales", "savoir-être", "key competencies",
        "professional strengths",
    ],
    "languages": [
        "langues", "languages", "compétences linguistiques", "linguistic skills",
        "spoken languages", "language proficiency", "idiomas",
    ],
    "certifications": [
        "certifications", "licences", "accréditations", "formations complémentaires",
        "permits", "habilitations", "badges", "diplômes complémentaires",
        "professional certifications", "accreditations",
    ],
    "projects": [
        "projets", "projects", "réalisations", "achievements", "accomplishments",
        "publications", "research", "patents", "brevets",
        "speaking engagements", "conférences", "distinctions",
        "awards", "honors", "prix", "portfolio",
    ],
    "other_right": [
        "centres d'intérêt", "interests", "hobbies", "loisirs",
        "activités", "community involvement", "bénévolat associatif",
        "activités associatives", "informations complémentaires",
        "additional information", "divers", "autres",
    ],
}

# ── Chemins de cache ───────────────────────────────────────────────────────
_CACHE_DIR  = Path(__file__).parent.parent / "temp"
_CACHE_FILE = _CACHE_DIR / "embeddings_cache.pkl"

# ── Singleton modèle ───────────────────────────────────────────────────────
_MODEL = None
_REF_EMBEDDINGS: dict[str, object] | None = None   # group → tensor moyen


def _get_model():
    global _MODEL
    if _MODEL is None:
        try:
            from app.config_loader import CFG
            model_name = CFG.get("models", {}).get(
                "embedding", "paraphrase-multilingual-MiniLM-L12-v2"
            )
            from sentence_transformers import SentenceTransformer
            logger.info("[EMBED] Chargement modèle %s ...", model_name)
            _MODEL = SentenceTransformer(model_name)
            logger.info("[EMBED] Modèle chargé ✓")
        except Exception as e:
            logger.warning("[EMBED] Modèle non disponible : %s", e)
            _MODEL = False
    return _MODEL if _MODEL else None


def _build_ref_embeddings(model) -> dict:
    """Calcule les embeddings moyens pour chaque groupe de référence."""
    import numpy as np
    refs = {}
    for group, labels in _REFERENCE_LABELS.items():
        embs = model.encode(labels, normalize_embeddings=True)
        refs[group] = np.mean(embs, axis=0)
    return refs


def _get_ref_embeddings(model):
    global _REF_EMBEDDINGS
    if _REF_EMBEDDINGS is not None:
        return _REF_EMBEDDINGS

    # Essayer de charger depuis le cache disque
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "rb") as f:
                _REF_EMBEDDINGS = pickle.load(f)
            logger.info("[EMBED] Embeddings de référence chargés depuis cache ✓")
            return _REF_EMBEDDINGS
        except Exception:
            pass

    # Recalculer et sauvegarder
    logger.info("[EMBED] Calcul des embeddings de référence...")
    _REF_EMBEDDINGS = _build_ref_embeddings(model)
    _CACHE_DIR.mkdir(exist_ok=True)
    with open(_CACHE_FILE, "wb") as f:
        pickle.dump(_REF_EMBEDDINGS, f)
    logger.info("[EMBED] Embeddings sauvegardés dans cache ✓")
    return _REF_EMBEDDINGS


def classify_section(theme: str, threshold: float | None = None) -> str | None:
    """
    Classifie un titre de section par similarité sémantique.

    Args:
        theme     : titre brut de la section (ex: "Réalisations clés")
        threshold : seuil minimum de similarité cosinus (défaut: config.yaml)

    Returns:
        Groupe canonique (ex: "experience") ou None si sous le seuil.
    """
    if not theme or not theme.strip():
        return None

    model = _get_model()
    if model is None:
        return None  # Fallback silencieux si modèle non dispo

    if threshold is None:
        try:
            from app.config_loader import CFG
            threshold = CFG.get("models", {}).get("embedding_threshold", 0.45)
        except Exception:
            threshold = 0.45

    import numpy as np

    ref_embeddings = _get_ref_embeddings(model)
    query_emb = model.encode([theme.strip()], normalize_embeddings=True)[0]

    best_group = None
    best_score = -1.0

    for group, ref_emb in ref_embeddings.items():
        score = float(np.dot(query_emb, ref_emb))
        if score > best_score:
            best_score = score
            best_group = group

    if best_score >= threshold:
        logger.debug(
            "[EMBED] %r → %r (score=%.3f)", theme, best_group, best_score
        )
        return best_group

    logger.debug("[EMBED] %r → aucun groupe (meilleur=%.3f < %.3f)", theme, best_score, threshold)
    return None


def invalidate_cache() -> None:
    """Supprime le cache disque des embeddings (utile si les labels changent)."""
    global _REF_EMBEDDINGS
    _REF_EMBEDDINGS = None
    if _CACHE_FILE.exists():
        _CACHE_FILE.unlink()
        logger.info("[EMBED] Cache invalidé")
