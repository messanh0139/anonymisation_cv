from app.models import StructuredCV, CVSection
import re

# ── Pré-traitement : nettoie les décorations de headers avant détection ──────
# Exemples couverts :
#   "─── FORMATION ───"  → "FORMATION"
#   "=== Skills ==="     → "Skills"
#   "*** Experience ***" → "Experience"
#   "__SKILLS__"         → "SKILLS"
#   "- - - Languages - -" → "Languages"
#   "1. Education"       → "Education"
#   "I. Work Experience" → "Work Experience"
#   "A. Skills"          → "Skills"
#   "[EXPERIENCE]"       → "EXPERIENCE"
#   "• FORMATION •"      → "FORMATION"
_DECO_BORDER_RE = re.compile(
    r'^[\s─═━\-=*#~+|_▬▪►•·\[\]{}<>]+|[\s─═━\-=*#~+|_▬▪►•·\[\]{}<>]+$'
)
_NUMBERED_PREFIX_RE = re.compile(
    r'^(?:\d{1,2}|[IVXivx]{1,4}|[A-Z])\s*[.)]\s+'
)


def _strip_header_decoration(line: str) -> str:
    """
    Retire les décorations typographiques autour d'un potentiel header.
    "─── FORMATION ───" → "FORMATION"
    "1. Education"      → "Education"
    "[Skills]"          → "Skills"
    """
    s = line.strip()
    # Retirer les bordures décoratives (caractères non alphanumériques répétés)
    s = _DECO_BORDER_RE.sub("", s).strip()
    # Retirer les préfixes numérotés/lettrés ("1. ", "I. ", "A. ", "ii) ")
    s = _NUMBERED_PREFIX_RE.sub("", s).strip()
    return s


# Regex date — pour exclure les lignes contenant une date (pas des headers)
_DATE_RE = re.compile(
    r'\b(19|20)\d{2}\b'
    r'(?:\s*[-–/]\s*(?:(19|20)\d{2}|present|actuel|aujourd[\'\u2019]?hui|ce jour|ongoing|en cours))?',
    re.IGNORECASE,
)

# Mots qui indiquent clairement que la ligne N'est PAS un header
# FR : articles/prépositions | EN : pronoms/articles/prépositions
_NOT_HEADER_STARTS = re.compile(
    r'^[-•*·▪▸►➢✓✔→]'
    # Français
    r'|^(je |j\'|mon |ma |mes |le |la |les |un |une |des |du |au |aux |'
    r'en |par |pour |avec |dans |sur |qui |que |qu\'|votre |notre |nous |'
    r'ce |cette |ces |cet |il |elle |ils |elles |on |y |dont )'
    # Anglais
    r'|^(i |i\'|my |your |his |her |its |our |their |we |he |she |they |it |'
    r'the |a |an |this |that |these |those |in |on |at |to |of |for |with |'
    r'by |from |as |is |are |was |were |have |has |had |been |be |do |does |'
    r'did |will |would |could |should |may |might |must |shall |'
    r'responsible |managed |led |developed |worked |helped |supported |'
    r'coordinated |implemented |designed |built |created |provided |ensured )',
    re.IGNORECASE,
)

EXACT_SECTION_HEADERS = {
    # ── Résumé / Profil ─────────────────────────────────────────────────────
    "profil",
    "profile",
    "about me",
    "about",
    "job objective",
    "job objective:",
    "career objective",
    "objective",
    "summary",
    "personal profile",
    "personal statement",
    "professional summary",
    "résumé",
    "résumé professionnel",
    "executive summary",
    "introduction",
    # ── Expériences ──────────────────────────────────────────────────────────
    "expériences",
    "expérience",
    "expérience professionnelle",
    "expériences professionnelles",
    "experience professionnelle",
    "work experience",
    "work history",
    "employment history",
    "employment",
    "professional experience",
    "professional experiences",
    "professional experiences:",
    "professional background",
    "relevant experience",
    "relevant work experience",
    "relevant work experience:",
    "career history",
    "job responsibilities in-service inspection:",
    "job responsibilities as welding inspector",
    "parcours professionnel",
    "historique professionnel",
    # ── Projets ──────────────────────────────────────────────────────────────
    "projets",
    "projets clés",
    "projets clé",
    "projets significatifs",
    "projects",
    "key projects",
    "notable projects",
    "personal projects",
    "side projects",
    "academic projects",
    "réalisations",
    "réalisations clés",
    "achievements",
    "key achievements",
    # ── Compétences ──────────────────────────────────────────────────────────
    "compétences",
    "compétences techniques",
    "technical skills",
    "technical expertise",
    "skills",
    "key skills",
    "core skills",
    "core competencies",
    "core competencies:",
    "areas of expertise",
    "expertise",
    "technologies",
    "technical certification",
    "technical certification:",
    "offshore trainings",
    "offshore trainings:",
    "authorized permit receiver training:",
    "certifications",
    "certification",
    "licenses & certifications",
    "licenses and certifications",
    "professional certifications",
    "training",
    "trainings",
    # ── Board / Mandats ──────────────────────────────────────────────────────
    "board experience",
    "board memberships",
    "board positions",
    "conseil d'administration",
    "mandats",
    # ── Soft Skills ──────────────────────────────────────────────────────────
    "soft skills",
    "qualités personnelles",
    "qualités",
    "compétences interpersonnelles",
    "key competencies",
    "key competencies:",
    "personal strengths",
    "personal attributes",
    "core strengths",
    "strengths",
    "professional strengths",
    # ── Formation ────────────────────────────────────────────────────────────
    "formation",
    "formations",
    "education",
    "education & training",
    "educational background",
    "educational qualification",
    "educational qualification:",
    "education / courses / certification",
    "academic background",
    "academic qualifications",
    "parcours académique",
    "diplômes",
    "degrees",
    "qualifications",
    # ── Langues ──────────────────────────────────────────────────────────────
    "languages",
    "languages:",
    "langues",
    "langues:",
    "langues et centres d'intérêt",
    "langues et centres d\u2019int\u00e9r\u00eat",
    # ── Divers ───────────────────────────────────────────────────────────────
    "others",
    "others :",
    "others:",
    "centres d'intérêt",
    "centres d\u2019int\u00e9r\u00eat",
    "loisirs",
    "hobbies",
    "interests",
    "hobbies & interests",
    "hobbies and interests",
    "extracurricular activities",
    "volunteer work",
    "volunteering",
    "bénévolat",
    "références",
    "references",
    "informations complémentaires",
    "additional information",
    "additional information:",
}


def normalize_lines(text: str) -> list[str]:
    return [line.strip() for line in text.split("\n") if line.strip()]


def normalize_header(line: str) -> str:
    return " ".join(line.strip().lower().split())


def is_exact_section_header(line: str) -> bool:
    return normalize_header(line) in EXACT_SECTION_HEADERS


def is_likely_section_header(line: str) -> bool:
    """
    Détecte automatiquement les headers de section inconnus grâce à des
    règles typographiques universelles applicables à tout CV.

    Un header de CV a typiquement les caractéristiques suivantes :
      - Court (1 à 6 mots)
      - Tout en MAJUSCULES, ou en Title Case
      - Peut se terminer par ':'
      - Ne contient pas de date
      - Ne commence pas par un bullet ni une phrase
      - Ne ressemble pas à un nom propre isolé (prénom/nom du candidat)
    """
    s = line.strip().rstrip(":")
    if not s:
        return False

    # Exclure les abréviations entre parenthèses : (CH). (UK). (US). etc.
    # Ce sont des codes pays/région dans un bloc d'expérience, pas des headers
    if re.match(r'^\([A-Za-z]{1,5}\)\.?$', s.strip()):
        return False

    words = s.split()
    n = len(words)

    # Trop long pour être un header
    if n > 6:
        return False

    # Contient une date → pas un header
    if _DATE_RE.search(s):
        return False

    # Commence par un bullet ou une phrase → pas un header
    if _NOT_HEADER_STARTS.search(s):
        return False

    # Tout en MAJUSCULES (1 à 6 mots) → header très probable
    # ex: "FORMATION", "PROJETS CLÉS", "LANGUES ET CENTRES D'INTÉRÊT"
    stripped_accents = s.replace("É","E").replace("È","E").replace("Ê","E") \
                        .replace("À","A").replace("Â","A").replace("Î","I") \
                        .replace("Ô","O").replace("Û","U").replace("Ç","C") \
                        .replace("Ù","U").replace("Ü","U")
    # Garder uniquement les caractères alphabétiques pour le test upper
    alpha_only = re.sub(r"[^A-Za-z]", "", stripped_accents)
    if alpha_only and alpha_only == alpha_only.upper() and n >= 1:
        # Exclure les lignes trop courtes qui sont juste des abréviations
        if n == 1 and len(s) <= 3:
            return False
        return True

    # Title Case UNIQUEMENT pour des patterns de 2 mots très typiques de headers
    # ex: "Soft Skills", "Key Projects", "Core Competencies"
    # Titre Case UNIQUEMENT pour des patterns de 2 mots très typiques de headers
    # ex: "Soft Skills", "Key Projects", "Core Competencies"
    # On exclut Title Case simple (3+ mots) car trop de faux positifs (noms d'écoles, villes…)
    # Exception : si la ligne contient un mot-clé sémantique de section → header reconnu
    # MAIS seulement si le PREMIER mot est lui-même un mot-clé ou un adjectif de section
    # (évite "My Experience", "Your Skills", "The Company", etc. — filtrés par _NOT_HEADER_STARTS)
    _SECTION_SEMANTIC_KW = re.compile(
        r'\b(skill|compétence|experience|expérience|project|projet|certif|licen|'
        r'education|formation|language|langue|interest|hobby|loisir|summary|profil|'
        r'achievement|r[eé]alisat|volunteer|board|mandat|award|publication|'
        r'reference|additional|training|cours|program|qualification)\b',
        re.IGNORECASE,
    )
    # Préfixes NON valides pour un header sémantique (possessifs, articles, verbes)
    _BAD_TITLE_PREFIX = re.compile(
        r'^(my|your|his|her|our|their|the|a|an|this|that|these|those|'
        r'mon|ma|mes|le|la|les|un|une|des|du|ce|cette|ces)\s',
        re.IGNORECASE,
    )
    _TITLE_CASE_HEADERS = {
        "soft skills", "key projects", "key achievements", "core competencies",
        "volunteer work", "personal projects", "side projects",
        "prix et distinctions", "awards and honors",
    }
    if normalize_header(line) in _TITLE_CASE_HEADERS:
        return True
    # Titre Case + mot-clé sémantique → header générique
    # Guard : le premier mot ne doit pas être un possessif/article
    if n <= 5 and not _BAD_TITLE_PREFIX.match(s) and _SECTION_SEMANTIC_KW.search(s):
        title_case_words = sum(1 for w in words if w[0].isupper())
        if title_case_words >= min(2, n):
            return True

    return False


def is_section_header(line: str) -> bool:
    """
    Détecte un header de section — 3 niveaux :
      1. Ligne brute → liste exacte connue
      2. Ligne brute → heuristique typographique
      3. Ligne avec décorations retirées → liste exacte + heuristique
         (couvre "─── FORMATION ───", "1. Education", "[Skills]", etc.)
    """
    if is_exact_section_header(line) or is_likely_section_header(line):
        return True
    # Essai avec décorations retirées (headers entourés de symboles, numérotés…)
    stripped = _strip_header_decoration(line)
    if stripped and stripped != line.strip():
        return is_exact_section_header(stripped) or is_likely_section_header(stripped)
    return False


def build_structured_cv(final_text: str, candidate_id: str) -> StructuredCV:
    """
    Structure le CV de façon fidèle :
    - aucun résumé
    - aucune reformulation
    - aucun thème inventé
    - ordre exact conservé
    - seuls les vrais headers du CV deviennent des thèmes
    """
    lines = normalize_lines(final_text)

    body_lines = [
        line for line in lines
        if line != f"Identifiant candidat : {candidate_id}"
    ]

    sections: list[CVSection] = []
    current_section = CVSection(theme="General", lines=[])

    for line in body_lines:
        if is_section_header(line):
            if current_section.lines:
                sections.append(current_section)

            # Utiliser le titre nettoyé (sans décorations) comme theme
            clean_theme = _strip_header_decoration(line)
            current_section = CVSection(theme=clean_theme or line, lines=[])
            continue

        current_section.lines.append(line)

    if current_section.lines:
        sections.append(current_section)

    return StructuredCV(
        candidate_id=candidate_id,
        final_anonymized_text=final_text,
        sections=sections,
    )