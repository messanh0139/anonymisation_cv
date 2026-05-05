import re


USELESS_HEADERS = {
    "curriculum vitae",
    "oap cv format",
    "contact",
}

PLACEHOLDER_LINES = {
    "[PHOTO SUPPRIMÉE]",
    "[EMAIL SUPPRIMÉ]",
    "[TÉLÉPHONE SUPPRIMÉ]",
    "[LINKEDIN SUPPRIMÉ]",
    "[ADRESSE SUPPRIMÉE]",
    "[DATE DE NAISSANCE SUPPRIMÉE]",
    "[NATIONALITÉ SUPPRIMÉE]",
    "[RÉSIDENCE SUPPRIMÉE]",
    "[INFORMATION SENSIBLE SUPPRIMÉE]",
    "[LIEN PERSONNEL SUPPRIMÉ]",
}


def remove_empty_contact_lines(text: str) -> str:
    """
    Supprime les lignes d'identité/contact inutiles du rendu final,
    y compris les lignes déjà anonymisées comme :
    - E-mail: [EMAIL SUPPRIMÉ]
    - Mobile Phone: [TÉLÉPHONE SUPPRIMÉ]
    """
    lines = text.split("\n")
    cleaned = []

    patterns = [
        r"^email\s*:",
        r"^e-mail\s*:",
        r"^mail id\s*:",
        r"^mobile\s*:?",
        r"^mobile no\s*:",
        r"^mobile phone\s*:",
        r"^téléphone\s*:",
        r"^telephone\s*:",
        r"^phone\s*:",
        r"^linkedin\s*:",
        r"^adresse\s*:",
        r"^address\s*:",
        r"^dob\s*:",
        r"^date of birth\s*:",
        r"^residency\s*:",
        r"^nationality\s*:",
        r"^nom\s*:",
        r"^name\s*:",
        r"^skype\s*:",
        r"^contact\s*:",
        r"^surname\s*:",
        r"^first name\s*:",
        r"^firstname\s*:",
    ]

    for line in lines:
        line_clean = line.strip()
        line_lower = line_clean.lower()

        # Supprime les lignes de contact explicites
        if any(re.search(pattern, line_lower) for pattern in patterns):
            continue

        # Supprime les lignes constituées uniquement d'un placeholder
        if line_clean in PLACEHOLDER_LINES:
            continue

        # Supprime aussi les lignes qui contiennent encore un placeholder sensible
        if "[EMAIL SUPPRIMÉ]" in line_clean:
            continue
        if "[TÉLÉPHONE SUPPRIMÉ]" in line_clean:
            continue
        if "[LINKEDIN SUPPRIMÉ]" in line_clean:
            continue
        if "[ADRESSE SUPPRIMÉE]" in line_clean:
            continue
        if "[DATE DE NAISSANCE SUPPRIMÉE]" in line_clean:
            continue
        if "[NATIONALITÉ SUPPRIMÉE]" in line_clean:
            continue
        if "[RÉSIDENCE SUPPRIMÉE]" in line_clean:
            continue
        if "[INFORMATION SENSIBLE SUPPRIMÉE]" in line_clean:
            continue
        if "[LIEN PERSONNEL SUPPRIMÉ]" in line_clean:
            continue

        cleaned.append(line_clean)

    return "\n".join(cleaned)


def remove_document_artifacts(text: str) -> str:
    """
    Supprime le bruit documentaire.
    """
    lines = text.split("\n")
    cleaned = []

    artifact_patterns = [
        r"\bpage\s+\d+\s+of\s+\d+\b",
        r"\brevis[aã]o\s*:\s*\d+\b",
        r"\brevision\s*:\s*\d+\b",
        r"\b[A-Z]{2,5}-\d{3,4}-[A-Z]{2,5}-\d{3,4}\b",
    ]

    for line in lines:
        line_clean = line.strip()

        if not line_clean:
            cleaned.append("")
            continue

        if line_clean.lower() in USELESS_HEADERS:
            continue

        if any(re.search(pattern, line_clean, flags=re.IGNORECASE) for pattern in artifact_patterns):
            continue

        cleaned.append(line_clean)

    return "\n".join(cleaned)


def remove_candidate_id_duplicates(text: str, candidate_id: str) -> str:
    """
    Supprime les doublons de candidate_id dans le corps du texte.
    """
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        if line.strip() == candidate_id:
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


def clean_extra_spaces(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_final_anonymized_text(text: str, candidate_id: str) -> str:
    """
    Produit le texte final anonymisé, prêt à être structuré.
    """
    text = remove_empty_contact_lines(text)
    text = remove_document_artifacts(text)
    text = remove_candidate_id_duplicates(text, candidate_id)
    text = clean_extra_spaces(text)

    final_text = f"Identifiant candidat : {candidate_id}\n\n{text}"
    return final_text.strip()