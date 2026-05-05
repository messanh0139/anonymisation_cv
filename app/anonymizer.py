import logging
import re
import uuid
from datetime import UTC, datetime
from typing import List, Tuple

logger = logging.getLogger(__name__)

# ── spaCy NER — chargé une seule fois au démarrage ───────────────────────────
# Utilisé comme couche de renforcement pour détecter les noms propres rares
# que les heuristiques regex ne capturent pas.
_NLP_FR = None
_NLP_EN = None

def _get_nlp_fr():
    global _NLP_FR
    if _NLP_FR is None:
        try:
            import spacy
            _NLP_FR = spacy.load("fr_core_news_md")
            logger.info("[NER] Modèle spaCy FR chargé")
        except Exception as e:
            logger.warning("[NER] Modèle FR non disponible : %s", e)
            _NLP_FR = False
    return _NLP_FR if _NLP_FR else None

def _get_nlp_en():
    global _NLP_EN
    if _NLP_EN is None:
        try:
            import spacy
            _NLP_EN = spacy.load("en_core_web_md")
            logger.info("[NER] Modèle spaCy EN chargé")
        except Exception as e:
            logger.warning("[NER] Modèle EN non disponible : %s", e)
            _NLP_EN = False
    return _NLP_EN if _NLP_EN else None


def _extract_persons_spacy(text: str) -> list[str]:
    """
    Détecte tous les noms de personnes dans le texte via spaCy NER.
    Utilise les deux modèles FR et EN, déduplique les résultats.
    Retourne uniquement les noms de ≥ 2 tokens (prénom + nom).
    """
    persons = set()
    # Limiter à 2000 chars pour la performance (le nom est toujours dans le début)
    sample = text[:2000]

    for nlp in [_get_nlp_fr(), _get_nlp_en()]:
        if nlp is None:
            continue
        try:
            doc = nlp(sample)
            for ent in doc.ents:
                if ent.label_ == "PER" and len(ent.text.split()) >= 2:
                    name = ent.text.strip()
                    if is_probable_person_name(name):
                        persons.add(name)
        except Exception as e:
            logger.warning("[NER] Erreur détection : %s", e)

    return list(persons)


GENERIC_FILENAME_WORDS = {
    "cv",
    "test",
    "resume",
    "profil",
    "profile",
    "document",
    "final",
    "version",
    "candidate",
    "candidat",
    "draft",
    "temp",
}

JOB_TITLE_KEYWORDS = {
    # ── Anglais ──────────────────────────────────────────────────────────────
    "engineer",
    "technician",
    "electrician",
    "manager",
    "director",
    "inspector",
    "analyst",
    "developer",
    "scientist",
    "supervisor",
    "fitter",
    "machinist",
    "welder",
    "operator",
    "lead",
    "offshore",
    "qc",
    "qa",
    "api",
    "account",
    "service",
    "workshop",
    "project",
    "managing",
    "customer",
    "consultant",
    "specialist",
    "coordinator",
    "administrator",
    "architect",
    "designer",
    "trainer",
    "auditor",
    "controller",
    "officer",
    "executive",
    "associate",
    "intern",
    "contractor",
    "technologist",
    # ── Français ─────────────────────────────────────────────────────────────
    "ingénieur",
    "ingenieur",
    "technicien",
    "technicienne",
    "responsable",
    "directeur",
    "directrice",
    "chef",
    "chargé",
    "chargée",
    "coordinateur",
    "coordinatrice",
    "consultant",
    "consultante",
    "analyste",
    "développeur",
    "développeuse",
    "architecte",
    "formateur",
    "formatrice",
    "auditeur",
    "auditrice",
    "contrôleur",
    "contrôleuse",
    "opérateur",
    "opératrice",
    "superviseur",
    "superviseure",
    "gestionnaire",
    "agent",
    "stagiaire",
    "assistant",
    "assistante",
    "expert",
    "experte",
    "spécialiste",
}


def normalize_text(text: str) -> str:
    """
    Normalise le texte :
    - uniformise les retours à la ligne
    - supprime les espaces multiples
    - réduit les lignes vides excessives
    """
    text = str(text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def generate_candidate_id(detected_name: str = "") -> str:
    """
    Génère un identifiant unique.
    Si un nom est détecté, utilise les initiales : ex. JD-AB12CD
    Sinon : CAND-AB12CD
    """
    random_part = uuid.uuid4().hex[:6].upper()

    if detected_name:
        parts = detected_name.strip().split()
        initials = "".join(p[0].upper() for p in parts if p)[:3]
        if len(initials) >= 2:
            return f"{initials}-{random_part}"

    return f"CAND-{random_part}"


def extract_name_from_filename(file_name: str) -> str:
    """
    Essaie d'extraire un nom depuis le nom du fichier,
    sauf si le nom est trop générique.
    """
    if not file_name:
        return ""

    base = re.sub(r"\.[^.]+$", "", file_name)
    base = re.sub(r"[_\-]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip()

    if not base:
        return ""

    words = set(base.lower().split())
    if words & GENERIC_FILENAME_WORDS:
        return ""

    if re.fullmatch(r"[A-Za-zÀ-ÿ' ]{4,}", base):
        return base

    return ""


def looks_like_job_title(line: str) -> bool:
    """
    Évite de confondre un poste avec un nom.
    """
    normalized = re.sub(r"[^A-Za-zÀ-ÿ ]+", " ", line).lower()
    words = set(normalized.split())
    return bool(words & JOB_TITLE_KEYWORDS)


def is_probable_person_name(name: str) -> bool:
    """
    Vérifie qu'on a probablement un vrai nom de personne.
    """
    if not name:
        return False

    clean = re.sub(r"[^A-Za-zÀ-ÿ' -]+", " ", name).strip()
    parts = [p for p in clean.split() if p]

    if len(parts) < 2 or len(parts) > 4:
        return False

    if looks_like_job_title(clean):
        return False

    if any(re.search(r"\d", p) for p in parts):
        return False

    if all(p.isupper() for p in parts):
        # Un nom en MAJUSCULES peut être un vrai nom, donc on ne rejette pas
        pass

    return True


def guess_name_from_text(text: str) -> str:
    """
    Détecte un nom probable dans les premières lignes du CV.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    lines = lines[:20]

    forbidden = re.compile(
        r"curriculum|vitae|cv|resume|profil|profile|contact|email|téléphone|telephone|adresse|address|linkedin|photo|name|dob|date of birth|residency|nationality|languages|langues|page|revis[aã]o|revision|job objective|core competencies|technical certification|professional experiences|work experience|personal profile|education|formation",
        re.IGNORECASE,
    )

    for line in lines:
        if forbidden.search(line):
            continue

        if looks_like_job_title(line):
            continue

        if re.search(r"\d", line):
            continue

        if re.fullmatch(
            r"[A-ZÀ-Ÿ][A-Za-zÀ-ÿ' -]+(?:\s+[A-ZÀ-Ÿ][A-Za-zÀ-ÿ' -]+){1,3}",
            line,
        ):
            if is_probable_person_name(line):
                return line

    return ""


def replace_name(text: str, detected_name: str, candidate_id: str) -> Tuple[str, bool]:
    """
    Remplace le nom détecté par le candidate_id.
    Ne remplace que si le nom ressemble réellement à un nom de personne.
    """
    if not is_probable_person_name(detected_name):
        return text, False

    replaced = False

    full_name_pattern = re.compile(rf"\b{re.escape(detected_name)}\b", re.IGNORECASE)
    text, count = full_name_pattern.subn(candidate_id, text)
    if count > 0:
        replaced = True

    for part in detected_name.split():
        if len(part) > 2:
            part_pattern = re.compile(rf"\b{re.escape(part)}\b", re.IGNORECASE)
            text, part_count = part_pattern.subn(candidate_id, text)
            if part_count > 0:
                replaced = True

    return text, replaced


def replace_name_labels(text: str, candidate_id: str) -> str:
    """
    Remplace les lignes explicites d'identité.
    """
    text = re.sub(
        r"\b(?:name|nom)\s*:\s*[^\n]*",
        candidate_id,
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b(?:surname|last name|family name)\s*:\s*[^\n]*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b(?:first name|firstname|prénom|prenom)\s*:\s*[^\n]*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text


def remove_emails(text: str) -> str:
    return re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "[EMAIL SUPPRIMÉ]",
        text,
        flags=re.IGNORECASE,
    )


def remove_phone_labels(text: str) -> str:
    """
    Supprime seulement les lignes explicites de téléphone.
    Couvre les formats FR, EN, et abréviations courantes.
    """
    patterns = [
        r"\bmobile(?:\s+no)?\s*:\s*[^\n]*",
        r"\bphone\s*:\s*[^\n]*",
        r"\btelephone\s*:\s*[^\n]*",
        r"\btéléphone\s*:\s*[^\n]*",
        r"\btel\.?\s*:\s*[^\n]*",
        r"\btél\.?\s*:\s*[^\n]*",
        r"\bmobile no\s*:\s*[^\n]*",
        r"\bmobile phone\s*:\s*[^\n]*",
        r"\bcell(?:ulaire)?\s*:\s*[^\n]*",
        r"\bgsm\s*:\s*[^\n]*",
        r"\bportable\s*:\s*[^\n]*",
        r"\bport\.?\s*:\s*[^\n]*",
        r"\bfax\s*:\s*[^\n]*",
        r"\bwhatsapp\s*:\s*[^\n]*",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "[TÉLÉPHONE SUPPRIMÉ]", text, flags=re.IGNORECASE)

    return text


def remove_standalone_phone_numbers(text: str) -> str:
    """
    Remplace seulement les numéros plausibles isolés.
    Très strict pour ne jamais casser :
    - candidate_id
    - années
    - périodes
    - diplômes
    - certifications
    """
    lines = text.split("\n")
    cleaned_lines = []

    phone_pattern = re.compile(
        r"(?<![A-Z])(?<!CAND-)(?<!\d)(?:\+?\d[\d\s().\-]{7,}\d)(?![A-Z])(?!\d)"
    )

    for line in lines:
        line_lower = line.lower()

        # On protège les lignes avec des années / périodes
        if re.search(r"\b(19|20)\d{2}\b", line):
            cleaned_lines.append(line)
            continue

        # On protège les lignes avec références techniques / diplômes / certifications
        if re.search(
            r"certificate|certificat|diploma|diplôme|api|cswip|irata|opito|gwo|iso|asme|aws|nace|level|university|college|institute",
            line_lower,
        ):
            cleaned_lines.append(line)
            continue

        def replacer(match: re.Match) -> str:
            value = match.group(0)

            # Protéger les identifiants candidat (CAND-XXXXXX ou initiales JD-XXXXXX)
            if re.search(r'[A-Z]{2,4}-(?:\d{8}-)?[A-F0-9]{6}', value):
                return value

            digits = re.sub(r"\D", "", value)

            if 8 <= len(digits) <= 15:
                return "[TÉLÉPHONE SUPPRIMÉ]"

            return value

        cleaned_lines.append(phone_pattern.sub(replacer, line))

    return "\n".join(cleaned_lines)


def remove_phones(text: str) -> str:
    """
    Version sûre :
    - lignes explicites
    - numéros isolés plausibles
    """
    text = remove_phone_labels(text)
    text = remove_standalone_phone_numbers(text)
    return text


def remove_linkedin(text: str) -> str:
    text = re.sub(
        r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s]+",
        "[LINKEDIN SUPPRIMÉ]",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\blinkedin\b\s*:\s*[^\n]*",
        "LinkedIn : [LINKEDIN SUPPRIMÉ]",
        text,
        flags=re.IGNORECASE,
    )

    return text


def remove_personal_links(text: str) -> str:
    """
    Supprime les liens personnels identifiables :
    - Libellés explicites : portfolio, website, github, skype, twitter, behance…
    - URLs personnelles (http/https) hors domaines professionnels connus
    """
    # Libellés avec valeur sur la même ligne
    text = re.sub(
        r"\b(?:portfolio|website|site\s+web|github|gitlab|bitbucket|"
        r"skype(?:\s+id)?|twitter|x\.com|behance|dribbble|"
        r"blog|viadeo|xing|whatsapp)\b\s*[:\-]?\s*[^\n]*",
        "[LIEN PERSONNEL SUPPRIMÉ]",
        text,
        flags=re.IGNORECASE,
    )
    # URLs génériques (http/https) qui ne sont pas LinkedIn (déjà géré par remove_linkedin)
    text = re.sub(
        r"https?://(?!(?:www\.)?linkedin\.com)[^\s,;\"\'<>]+",
        "[LIEN SUPPRIMÉ]",
        text,
        flags=re.IGNORECASE,
    )
    # www. sans http
    text = re.sub(
        r"(?<!\blinkedin\.)www\.[a-zA-Z0-9][-a-zA-Z0-9.]+\.[a-zA-Z]{2,}(?:/[^\s]*)?",
        "[LIEN SUPPRIMÉ]",
        text,
        flags=re.IGNORECASE,
    )
    return text


def remove_birth_info(text: str) -> str:
    return re.sub(
        r"\b(?:dob|date of birth|birth date|born|né\(e\)? le|date de naissance|né le)\b\s*:\s*[^\n]*",
        "[DATE DE NAISSANCE SUPPRIMÉE]",
        text,
        flags=re.IGNORECASE,
    )


def remove_nationality(text: str) -> str:
    return re.sub(
        r"\b(?:nationality|nationalité)\b\s*:\s*[^\n]*",
        "[NATIONALITÉ SUPPRIMÉE]",
        text,
        flags=re.IGNORECASE,
    )


def normalize_language_section(text: str) -> str:
    return re.sub(
        r"\blanguages?\b\s*:\s*",
        "Languages:\n",
        text,
        flags=re.IGNORECASE,
    )


def remove_residency(text: str) -> str:
    return re.sub(
        r"\bresidency\b\s*:\s*[^\n]*",
        "[RÉSIDENCE SUPPRIMÉE]",
        text,
        flags=re.IGNORECASE,
    )


def remove_address(text: str) -> str:
    text = re.sub(
        r"\b(?:address|adresse)\b\s*[:\-]?\s*[^\n]*",
        "Adresse : [ADRESSE SUPPRIMÉE]",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b\d{1,4}[,\s]+(?:rue|street|avenue|av\.|road|rd|boulevard|blvd|lane|allée|allee|impasse|chemin|route)\b[^\n]*",
        "[ADRESSE SUPPRIMÉE]",
        text,
        flags=re.IGNORECASE,
    )

    return text


def remove_location_markers(text: str) -> str:
    return re.sub(
        r"^[^\n]*📍[^\n]*$",
        "",
        text,
        flags=re.MULTILINE,
    )


def remove_photo_mentions(text: str) -> str:
    return re.sub(
        r"\b(?:photo|picture|portrait)\b\s*[:\-]?\s*[^\n]*",
        "[PHOTO SUPPRIMÉE]",
        text,
        flags=re.IGNORECASE,
    )


def remove_sensitive_misc(text: str) -> str:
    return re.sub(
        r"\b(?:marital status|situation familiale|âge|age|passport|id number|numéro de pièce|hobbies)\b\s*[:\-]?\s*[^\n]*",
        "[INFORMATION SENSIBLE SUPPRIMÉE]",
        text,
        flags=re.IGNORECASE,
    )


def remove_document_artifacts(text: str) -> str:
    text = re.sub(r"\bpage\s+\d+\s+of\s+\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[A-Z]{2,5}-\d{3,4}-[A-Z]{2,5}-\d{3,4}\b[^\n]*", "", text)
    text = re.sub(r"\brevis[aã]o\s*:\s*\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\brevision\s*:\s*\d+\b", "", text, flags=re.IGNORECASE)
    return text


def final_cleanup(text: str, detected_name: str, candidate_id: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^\s*[-,:;|]\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    if detected_name and is_probable_person_name(detected_name) and lines:
        if lines[0].lower() == detected_name.lower():
            lines[0] = candidate_id

    if candidate_id not in lines:
        if lines and lines[0] == "[PHOTO SUPPRIMÉE]":
            lines.insert(1, candidate_id)
        else:
            lines.insert(0, candidate_id)

    return "\n".join(lines).strip()


def identify_candidate(text: str, file_name: str = "") -> dict:
    normalized_text = normalize_text(text)

    # 1. Détection heuristique (rapide)
    detected_name = guess_name_from_text(normalized_text) or extract_name_from_filename(file_name)

    if not is_probable_person_name(detected_name):
        detected_name = ""

    # 2. Renforcement spaCy NER — capture les noms rares non détectés par les heuristiques
    spacy_persons = _extract_persons_spacy(normalized_text)
    if not detected_name and spacy_persons:
        # Prendre le nom le plus long (prénom + nom complet)
        detected_name = max(spacy_persons, key=lambda n: len(n.split()))
        logger.info("[NER] Nom détecté via spaCy : %r", detected_name)
    elif detected_name:
        # Vérifier si spaCy confirme ou affine le nom heuristique
        for name in spacy_persons:
            if detected_name.lower() in name.lower() and len(name) > len(detected_name):
                detected_name = name  # version plus complète
                break

    candidate_id = generate_candidate_id(detected_name)

    return {
        "normalized_text": normalized_text,
        "detected_name": detected_name,
        "candidate_id": candidate_id,
        "spacy_persons": spacy_persons,  # pour traçabilité
    }


def anonymize_text_with_candidate_id(
    text: str,
    detected_name: str,
    candidate_id: str,
    spacy_persons: list | None = None,
) -> dict:
    removed_fields: List[str] = []

    original = text
    text = replace_name_labels(text, candidate_id)
    if text != original:
        removed_fields.append("name_label_replaced")

    text, name_replaced = replace_name(text, detected_name, candidate_id)
    if name_replaced:
        removed_fields.append("name_replaced")

    # Remplacement des noms supplémentaires détectés par spaCy
    if spacy_persons:
        for extra_name in spacy_persons:
            if extra_name == detected_name:
                continue
            if is_probable_person_name(extra_name):
                text, replaced = replace_name(text, extra_name, candidate_id)
                if replaced:
                    removed_fields.append(f"spacy_name_replaced:{extra_name[:20]}")
                    logger.info("[NER] Nom supplémentaire anonymisé : %r", extra_name)

    original = text
    text = remove_emails(text)
    if text != original:
        removed_fields.append("email")

    original = text
    text = remove_phones(text)
    if text != original:
        removed_fields.append("phone")

    original = text
    text = remove_linkedin(text)
    if text != original:
        removed_fields.append("linkedin")

    original = text
    text = remove_personal_links(text)
    if text != original:
        removed_fields.append("personal_links")

    original = text
    text = remove_birth_info(text)
    if text != original:
        removed_fields.append("birth_date")

    original = text
    text = remove_nationality(text)
    if text != original:
        removed_fields.append("nationality")

    text = normalize_language_section(text)

    original = text
    text = remove_residency(text)
    if text != original:
        removed_fields.append("residency")

    original = text
    text = remove_address(text)
    if text != original:
        removed_fields.append("address")

    original = text
    text = remove_location_markers(text)
    if text != original:
        removed_fields.append("location")

    original = text
    text = remove_photo_mentions(text)
    if text != original:
        removed_fields.append("photo")

    original = text
    text = remove_sensitive_misc(text)
    if text != original:
        removed_fields.append("other_sensitive_fields")

    original = text
    text = remove_document_artifacts(text)
    if text != original:
        removed_fields.append("document_artifacts")

    text = final_cleanup(text, detected_name, candidate_id)

    return {
        "candidate_id": candidate_id,
        "detected_name": detected_name,
        "anonymized_text": text,
        "removed_fields": removed_fields,
    }


def anonymize_cv_text(text: str, file_name: str = "") -> dict:
    if not text or not isinstance(text, str):
        raise ValueError("Le texte du CV est vide ou invalide.")

    identity = identify_candidate(text, file_name)

    return anonymize_text_with_candidate_id(
        text=identity["normalized_text"],
        detected_name=identity["detected_name"],
        candidate_id=identity["candidate_id"],
    )
