"""
latex_builder.py

Remplit dynamiquement le template cv_pretty.tex avec les données du JSON
structuré et compile le résultat en PDF via pdflatex.

Ordre canonique des sections :
  Colonne gauche  : Profil → Expériences → Projets → Certifications → Autres
  Barre latérale  : Compétences → Soft Skills → Formation → Langues → Divers
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


from app.structurer import is_section_header as _is_section_header

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# ── Ordre canonique ────────────────────────────────────────────────────────────
LEFT_GROUPS_ORDER = [
    "resume",
    "experience",
    "projects",
    "certifications",
]

RIGHT_GROUPS_ORDER = [
    "skills",
    "soft_skills",
    "education",
    "languages",
]

# Correspondance thème normalisé → groupe
THEME_TO_GROUP: dict[str, str] = {
    # ── Résumé / Profil ───────────────────────────────────────────────────────
    "profil":                        "resume",
    "profile":                       "resume",
    "about me":                      "resume",
    "about":                         "resume",
    "job objective":                 "resume",
    "job objective:":                "resume",
    "career objective":              "resume",
    "objective":                     "resume",
    "summary":                       "resume",
    "professional summary":          "resume",
    "personal profile":              "resume",
    "personal statement":            "resume",
    "résumé":                        "resume",
    "résumé professionnel":          "resume",
    "executive summary":             "resume",
    "introduction":                  "resume",
    # ── Expériences ───────────────────────────────────────────────────────────
    "expériences":                   "experience",
    "expérience":                    "experience",
    "expérience professionnelle":    "experience",
    "expériences professionnelles":  "experience",
    "experience professionnelle":    "experience",
    "work experience":               "experience",
    "work history":                  "experience",
    "employment history":            "experience",
    "employment":                    "experience",
    "professional experience":       "experience",
    "professional experiences":      "experience",
    "professional experiences:":     "experience",
    "professional background":       "experience",
    "relevant experience":           "experience",
    "relevant work experience":      "experience",
    "relevant work experience:":     "experience",
    "career history":                "experience",
    "job responsibilities in-service inspection:": "experience",
    "job responsibilities as welding inspector":   "experience",
    "parcours professionnel":        "experience",
    "historique professionnel":      "experience",
    # ── Projets ───────────────────────────────────────────────────────────────
    "projets":                       "projects",
    "projets clés":                  "projects",
    "projets clé":                   "projects",
    "projets significatifs":         "projects",
    "projects":                      "projects",
    "key projects":                  "projects",
    "notable projects":              "projects",
    "personal projects":             "projects",
    "side projects":                 "projects",
    "academic projects":             "projects",
    "réalisations":                  "projects",
    "réalisations clés":             "projects",
    "achievements":                  "projects",
    "key achievements":              "projects",
    # ── Compétences techniques ────────────────────────────────────────────────
    "compétences":                   "skills",
    "compétences techniques":        "skills",
    "technical skills":              "skills",
    "technical expertise":           "skills",
    "skills":                        "skills",
    "key skills":                    "skills",
    "core skills":                   "skills",
    "core competencies":             "skills",
    "core competencies:":            "skills",
    "areas of expertise":            "skills",
    "expertise":                     "skills",
    "technologies":                  "skills",
    # ── Certifications ────────────────────────────────────────────────────────
    "technical certification":       "certifications",
    "technical certification:":      "certifications",
    "offshore trainings":            "certifications",
    "offshore trainings:":           "certifications",
    "authorized permit receiver training:": "certifications",
    "certifications":                "certifications",
    "certification":                 "certifications",
    "licenses & certifications":     "certifications",
    "licenses and certifications":   "certifications",
    "professional certifications":   "certifications",
    "training":                      "certifications",
    "trainings":                     "certifications",
    # ── Expériences — variantes board/conseil ─────────────────────────────────
    "board experience":              "experience",
    "board memberships":             "experience",
    "board positions":               "experience",
    "conseil d'administration":      "experience",
    "mandats":                       "experience",
    # ── Soft skills ───────────────────────────────────────────────────────────
    "soft skills":                   "soft_skills",
    "qualités personnelles":         "soft_skills",
    "qualités":                      "soft_skills",
    "compétences interpersonnelles": "soft_skills",
    "interpersonal skills":          "soft_skills",
    "personal skills":               "soft_skills",
    "key competencies":              "soft_skills",
    "key competencies:":             "soft_skills",
    "personal strengths":            "soft_skills",
    "personal attributes":           "soft_skills",
    "core strengths":                "soft_skills",
    "strengths":                     "soft_skills",
    "professional strengths":        "soft_skills",
    # ── Formation ─────────────────────────────────────────────────────────────
    "formation":                     "education",
    "formations":                    "education",
    "education":                     "education",
    "education & training":          "education",
    "educational background":        "education",
    "educational qualification":     "education",
    "educational qualification:":    "education",
    "education / courses / certification": "education",
    "academic background":           "education",
    "academic qualifications":       "education",
    "parcours académique":           "education",
    "diplômes":                      "education",
    "degrees":                       "education",
    "qualifications":                "education",
    # ── Langues ───────────────────────────────────────────────────────────────
    "languages":                     "languages",
    "languages:":                    "languages",
    "langues":                       "languages",
    "langues:":                      "languages",
    "langues et centres d'intérêt":  "languages",
    "langues et centres d\u2019int\u00e9r\u00eat": "languages",
    # ── Divers / Intérêts ─────────────────────────────────────────────────────
    "others":                        "other_right",
    "others :":                      "other_right",
    "others:":                       "other_right",
    "centres d'intérêt":             "other_right",
    "centres d\u2019int\u00e9r\u00eat": "other_right",
    "loisirs":                       "other_right",
    "hobbies":                       "other_right",
    "interests":                     "other_right",
    "hobbies & interests":           "other_right",
    "hobbies and interests":         "other_right",
    "extracurricular activities":    "other_right",
    "volunteer work":                "other_right",
    "volunteering":                  "other_right",
    "bénévolat":                     "other_right",
    "références":                    "other_right",
    "references":                    "other_right",
    "informations complémentaires":  "other_right",
    "additional information":        "other_right",
    "additional information:":       "other_right",
}

# Titres affichés dans le PDF
GROUP_DISPLAY_TITLE: dict[str, str] = {
    "resume":         "Profil",
    "experience":     "Expérience Professionnelle",
    "projects":       "Projets Clés",
    "certifications": "Certifications \\& Formations Complémentaires",
    "skills":         "Compétences Techniques",
    "soft_skills":    "Soft Skills \\& Hard Skills",
    "education":      "Formation",
    "languages":      "Langues",
    "other_left":     "Autres Informations",
    "other_right":    "Informations Complémentaires",
}

# Regex date (année seule ou plage)
_DATE_RE = re.compile(
    r'\b(19|20)\d{2}\b'
    r'(?:\s*[-–/]\s*(?:(19|20)\d{2}|present|actuel|aujourd[\'\u2019]?hui|ce jour|ongoing|en cours))?',
    re.IGNORECASE,
)

# Mois FR + EN (formes longues et abrégées) pour détecter les périodes
_MONTHS = (
    # Français
    r'Janv?(?:ier)?|Févr?(?:ier)?|Mars|Avr(?:il)?|Mai|Juin|'
    r'Juil(?:let)?|Ao[ûu]t|Sept?(?:embre)?|Oct(?:obre)?|Nov(?:embre)?|Déc(?:embre)?|'
    # Anglais
    r'Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
    r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?'
)

# Fin de période : année, présent, actuel, en cours, ongoing, to date
_PERIOD_END = (
    r'(?:(19|20)\d{2}|'
    r'présent|present|actuel|en cours|ongoing|to date|'
    r'aujourd[\'\u2019]?hui|ce jour|now)'
)

# Période complète : "Mois YYYY [- fin]" ou "YYYY - fin"
_PERIOD_RE = re.compile(
    rf'((?:{_MONTHS})\.?\s+(19|20)\d{{2}}'
    rf'(?:\s*[-–]\s*(?:(?:{_MONTHS})\.?\s+(19|20)\d{{2}}|{_PERIOD_END}))?'
    rf'|(19|20)\d{{2}}\s*[-–]\s*(?:(19|20)\d{{2}}|{_PERIOD_END})'
    rf'(?:\s*\([^)]*\))?'
    rf')',
    re.IGNORECASE,
)


def _split_title_from_period(s: str) -> tuple[str, str] | None:
    """
    Si la ligne contient un titre suivi d'une période (éventuellement collée),
    retourne (titre, période). Sinon None.
    Exemples gérés :
      "Enseignant de Mathématiques Sep. 2015 - Juin 2022"
      "Projet Personnel: ClassificationAoût 2025 - Sept. 2025"
      "Projet Académique: Prédiction du Diabète Nov. 2024 - Janv. 2025"
      "Master 2 Expert en IA 2025 - 2026 (en cours)"
    """
    m = _PERIOD_RE.search(s)
    if not m:
        return None

    period = m.group(0).strip()
    before = s[:m.start()].rstrip()

    # Vérifier qu'il reste un titre avant la période
    if not before:
        return None  # la ligne est entièrement une période

    # Nettoyer les séparateurs collés ou espaces finaux
    title = before.rstrip(' :,–-').strip()
    if not title:
        return None

    return title, period


# Seuil ligne brisée : rejoindre si < N mots
_WRAP_WORD_THRESHOLD = 12


# ── Helpers LaTeX ──────────────────────────────────────────────────────────────
def _esc(text: str) -> str:
    """Échappe les caractères spéciaux LaTeX."""
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&",  r"\&"),
        ("%",  r"\%"),
        ("$",  r"\$"),
        ("#",  r"\#"),
        ("_",  r"\_"),
        ("{",  r"\{"),
        ("}",  r"\}"),
        ("~",  r"\textasciitilde{}"),
        ("^",  r"\textasciicircum{}"),
        ("\u2019", "'"),
        ("\u2018", "'"),
        ("\u201c", "\""),
        ("\u201d", "\""),
        ("\u2013", "--"),
        ("\u2014", "---"),
        ("\u00a0", "~"),
        # Bullets et flèches décoratifs → tiret simple
        ("\u27a2", "-"),
        ("\u25ba", "-"),
        ("\u25b8", "-"),
        ("\u2192", "-"),
        ("\u2022", "-"),
        ("\u25aa", "-"),
        ("\u25cf", "-"),
        ("\u2023", "-"),
        ("\u25c6", "-"),
        ("\u2714", "-"),
        ("\u2713", "-"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _norm(theme: str) -> str:
    return theme.strip().lower()


# ── Recolle les lignes brisées ─────────────────────────────────────────────────
def _rejoin_lines(lines: list[str]) -> list[str]:
    """
    Recolle les fragments de phrases brisés par l'extracteur PDF.
    Une ligne est un fragment si :
      - elle ne commence pas par un bullet
      - la ligne précédente ne se termine pas par . ? ! :
      - elle commence par une minuscule (continuation évidente)
        OU elle contient peu de mots (< seuil)
      - elle ne ressemble pas à un header autonome
      - ce n'est pas une ligne de date isolée
    """
    if not lines:
        return []

    # Tous les types de bullets reconnus (ASCII + Unicode étendu)
    _BULLET_PAT = re.compile(r'^[-•*·▪▸►➢→✓✔✦]\s?')

    def is_bullet(s: str) -> bool:
        return bool(_BULLET_PAT.match(s.strip()))

    def ends_sentence(s: str) -> bool:
        return bool(re.search(r'[.!?:]\s*$', s.rstrip()))

    def is_date_line(s: str) -> bool:
        # Ne pas fusionner si la ligne contient une date (fin de titre/période)
        return bool(_DATE_RE.search(s))

    def starts_lowercase(s: str) -> bool:
        """Commence par une lettre minuscule → continuation d'une phrase."""
        c = s.strip()[:1]
        return c.islower()

    def is_standalone_header(s: str) -> bool:
        words = s.strip().split()
        if not words:
            return False
        # Tout en majuscules 1-6 mots = header autonome → ne pas fusionner
        alpha = re.sub(r'[^A-Za-z]', '', s)
        return bool(alpha) and alpha == alpha.upper() and 1 <= len(words) <= 6

    result: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        can_merge = (
            result
            and result[-1]
            and not is_bullet(line)
            and not is_bullet(result[-1])
            and not is_date_line(line)
            and not is_date_line(result[-1])   # aussi la ligne précédente
            and not is_standalone_header(line)
            and not ends_sentence(result[-1])
            and (starts_lowercase(line) or len(line.split()) < _WRAP_WORD_THRESHOLD)
        )

        if can_merge:
            result[-1] = result[-1].rstrip() + " " + line
        else:
            result.append(line)

    return result


# ── Re-segmentation interne ────────────────────────────────────────────────────
def _resegment(sections: list[dict]) -> list[dict]:
    """
    Parcourt les lignes de chaque section. Si une ligne est en réalité un header
    (connu ou détecté automatiquement), on crée une nouvelle section à partir
    de ce point. Cela corrige les JSON où des headers sont dans les lines.
    """
    result: list[dict] = []

    for sec in sections:
        current_theme = sec.get("theme", "")
        current_lines: list[str] = []

        for line in sec.get("lines", []):
            ln_norm = _norm(line)
            theme_norm = _norm(current_theme)

            if _is_section_header(line) and ln_norm != theme_norm:
                if current_lines:
                    result.append({"theme": current_theme, "lines": current_lines})
                current_theme = line.strip()
                current_lines = []
            else:
                current_lines.append(line)

        result.append({"theme": current_theme, "lines": current_lines})

    return result


# ── Regroupement par groupe canonique ──────────────────────────────────────────

# Groupes dont les lignes sont du texte courant → appliquer _rejoin_lines
_TEXT_GROUPS = {"resume", "other_right"}

import logging as _logging
_log = _logging.getLogger(__name__)

# ── Classification floue : gère n'importe quelle section inconnue ──────────────
# Chaque règle = (pattern sur le nom de section, groupe cible)
# Ordre du plus spécifique au plus général.
_FUZZY_THEME_RULES: list[tuple[re.Pattern, str]] = [
    # Profil / résumé  (prefix matching — pas de \b terminal)
    (re.compile(r'\b(profile|profil|summar|objective|about\b|introduction|r[eé]sum[eé]|statement|overview|highlight)', re.I), "resume"),
    # Compétences techniques (avant expériences pour éviter faux positifs)
    (re.compile(r'\b(skill|comp[eé]tenc|expertise|technical|technolog|tool\b|outils|capabilit|proficien|'
                r'stack\b|framework|software|logiciel|instrument|equipment|background)', re.I), "skills"),
    # Soft skills / qualités (core strengths, strengths seul, etc.)
    (re.compile(r'\b(soft.skill|interpersonal|personal.attr|core.strength|strength\b|qualit[eé]|trait\b|'
                r'competenc[ey]|comportement)', re.I), "soft_skills"),
    # Formation
    (re.compile(r'\b(educat|formation|stud[yi]|academic|degree|qualif|school|universit|college|'
                r'cours\b|cursus|program|parcours|training)', re.I), "education"),
    # Certifications / permis / accréditations
    (re.compile(r'\b(certif|licen|permit|accredit|habilitat|diploma|diplôme|badge)', re.I), "certifications"),
    # Langues
    (re.compile(r'\b(language|langue|linguistic|spoken|written|idioma)', re.I), "languages"),
    # Projets / réalisations / publications / brevets / prix / conférences / distinctions
    (re.compile(r'\b(project|r[eé]alisat|achievement|portfolio|contribution|deliverable|'
                r'publication|research|patent|brevet|conf[eé]ren|'
                r'presentation|speaking|talk|distinction|award|prix|honor|honour|'
                r'accolade|recognition|scholarly|academic.project|projet|académ)', re.I), "projects"),
    # Expériences (board, bénévolat, missions, militaire, freelance inclus)
    (re.compile(r'\b(experience|expérience|work\b|employ|career|histor|responsibilit|'
                r'mission|board|advisor|mandat|conseil|volunteer|b[eé]n[eé]volat|'
                r'internship|stage\b|apprenticeship|assignment|'
                r'freelance|consulting|militar|service\b|poste|fonction)', re.I), "experience"),
    # Activités communautaires / associatives / engagement civic
    (re.compile(r'\b(communit|associati|activit[eé]|involvement|civic|club\b|'
                r'volunteering|affiliation|membership|b[eé]n[eé]volat)', re.I), "other_right"),
    # Divers / intérêts / autres
    (re.compile(r'\b(interest|hobby|hobbies|loisir|passion|divers\b|other\b|miscellaneous|'
                r'additional|extra\b|information|reference)', re.I), "other_right"),
]

def _fuzzy_classify_theme(theme: str) -> str | None:
    """Classifie une section inconnue en testant les patterns sémantiques.
    Retourne le groupe canonique ou None si aucune règle ne correspond."""
    for pattern, group in _FUZZY_THEME_RULES:
        if pattern.search(theme):
            return group
    return None


def _group_sections(sections: list[dict]) -> dict[str, list[str]]:
    # Initialiser tous les groupes connus (y compris other_left/other_right)
    all_groups = LEFT_GROUPS_ORDER + RIGHT_GROUPS_ORDER + ["other_left", "other_right"]
    groups: dict[str, list[str]] = {g: [] for g in all_groups}

    # Lignes de profil détectées dans la section General à ajouter en tête du resume
    general_resume_lines: list[str] = []

    for sec in sections:
        tn = _norm(sec.get("theme", ""))
        tn_clean = tn.rstrip(":").strip()

        # ── Section "General" (contenu avant le 1er header) ──────────────────
        # On re-segmente les lignes General en groupes pertinents :
        # - lignes de description → resume
        # - lignes contact/état-civil → ignorées
        # - lignes bullets → resume (profil)
        if tn in ("general", ""):
            raw = [l.strip() for l in sec.get("lines", []) if l.strip()]
            _CONTACT_RE = re.compile(
                r'@|\bTel\b|\bFax\b|www\.|linkedin\.com'
                r'|\bPhone\b|\bMobile\b|\bEmail\b|^\+\d'
                r'|Married|Single|Divorced|Widowed|Nationality|Nationalité'
                r'|Date\s+of\s+birth|Date\s+de\s+naissance'
                r'|Localisation|Location|Based\s+in|Residency',
                re.IGNORECASE,
            )
            for l in raw:
                if not _CONTACT_RE.search(l):
                    general_resume_lines.append(l)
            continue

        # 1. Correspondance exacte dans THEME_TO_GROUP
        group = THEME_TO_GROUP.get(tn) or THEME_TO_GROUP.get(tn_clean)

        # 2. Embeddings sémantiques (plus robuste que les regex)
        if group is None:
            try:
                from app.section_classifier import classify_section
                group = classify_section(sec.get("theme", ""))
                if group:
                    _log.info("Section %r → groupe %r (embeddings)", sec.get("theme", ""), group)
            except Exception:
                pass

        # 3. Fallback : classification floue par mots-clés sémantiques (regex)
        if group is None:
            group = _fuzzy_classify_theme(tn)
            if group:
                _log.info("Section %r → groupe %r (classification floue)", sec.get("theme", ""), group)
            else:
                # Dernier recours : contenu non classifiable → other_right pour ne rien perdre
                preview = " | ".join((sec.get("lines") or [])[:2])
                _log.warning(
                    "Section non classifiable → other_right : %r  (aperçu: %s)",
                    sec.get("theme", ""), preview[:80]
                )
                group = "other_right"

        raw_lines = sec.get("lines", [])
        # Recoller les lignes brisées uniquement pour les sections texte libre
        if group in _TEXT_GROUPS:
            lines = _rejoin_lines(raw_lines)
        else:
            lines = [l.strip() for l in raw_lines if l.strip()]
        groups[group].extend(lines)

    # Injecter le contenu General en tête du resume
    # Seulement les lignes qui ressemblent à un profil (texte suffisamment long
    # ou bullets de compétences) — pas les lignes ultra-courtes d'info
    if general_resume_lines:
        profile_lines = []
        for l in general_resume_lines:
            words = l.split()
            # Garder si : longue phrase (≥6 mots) OU bullet descriptif (≥4 mots après bullet)
            clean = re.sub(r'^[-•*·▪▸►➢→✓✔✦]\s?', '', l).strip()
            if len(clean.split()) >= 4:
                profile_lines.append(l)
        if profile_lines:
            groups["resume"] = profile_lines + groups["resume"]

    return groups


# ── Détection du titre de poste ────────────────────────────────────────────────
# Mots-clés métier — liste étendue pour couvrir tous types de postes
_JOB_TITLE_KEYWORDS = re.compile(
    r'\b(engineer|ingénieur|manager|directeur|director|consultant|analyst|analyste|'
    r'inspector|inspecteur|supervisor|superviseur|officer|chargé|technicien|technician|'
    r'chef|lead|senior|junior|expert|spécialiste|specialist|coordinateur|coordinator|'
    r'responsable|developer|développeur|architect|architecte|controller|contrôleur|'
    r'quality|qualité|project|projet|supply|logistic|hse|qhse|ndt|welding|soudure|'
    r'data|scientist|intelligence|artificielle|artificial|machine learning|deep learning|'
    r'designer|developer|devops|fullstack|frontend|backend|programmer|programmeur|'
    r'accountant|comptable|financier|finance|auditeur|auditor|juriste|lawyer|avocat|'
    r'médecin|doctor|nurse|infirmier|pharmacien|biologiste|biologist|chercheur|researcher|'
    r'professeur|teacher|formateur|trainer|coach|commercial|sales|marketing|'
    r'acheteur|buyer|logisticien|planificateur|planner|electrician|électricien|'
    r'soudeur|welder|mécanicien|mechanic|opérateur|operator|technicien|'
    r'assistant|secrétaire|secretary|administrateur|administrator|rh|hr|'
    r'géologue|geologist|géophysicien|topographe|surveyor|driller|foreur)\b',
    re.IGNORECASE,
)

# Patterns de titres sans mots-clés mais clairement un poste
# ex: "Data Scientist", "Chef de Projet", "Business Intelligence"
_JOB_TITLE_PATTERNS = re.compile(
    r'\b(data|business|project|chief|head of|responsable de|chargé de|'
    r'directeur de|director of|vp |vice.president)\b',
    re.IGNORECASE,
)

def _is_job_title(s: str) -> bool:
    """Détermine si une ligne est un titre de poste.
    Combine mots-clés métier + heuristique Title Case pour rester générique."""
    s = s.strip()
    # Exclure bullets / puces
    if re.match(r'^[-•*·▪▸►➢✓✔→✦▪]\s?', s):
        return False
    words = s.split()
    if not s or len(words) < 2 or len(words) > 9:
        return False
    # Exclure les lignes contenant une date
    if _DATE_RE.search(s):
        return False
    # Exclure les lignes info-contact (email, téléphone, url, @)
    if re.search(r'[@:/]|www\.|\d{5,}', s):
        return False
    # Exclure les lignes état-civil / localisation
    if re.search(
        r'\b(married|single|divorced|widowed|nationality|based\s+in|born|'
        r'marié|célibataire|divorcé|nationalité|né\s+(le|en)|réside)\b',
        s, re.IGNORECASE
    ):
        return False
    # Exclure les lignes avec séparateur bullet interne (info personnelle concaténée)
    # ex: "Norwegian • Married • Based in Orkanger"
    if re.search(r'[•·▪]', s):
        return False
    # Contient un mot-clé métier explicite → oui directement
    if _JOB_TITLE_KEYWORDS.search(s):
        return True
    # Pattern type "Data Scientist", "Chef de Projet"
    if _JOB_TITLE_PATTERNS.search(s):
        return True
    # Heuristique générique : Title Case (≥ 2 mots capitalisés sur 2-6 mots)
    # ex: "Managing Director", "Supply Chain Analyst", "Chargé d'Affaires"
    if 2 <= len(words) <= 6:
        capitalized = sum(1 for w in words if w[0].isupper() and not w.isupper())
        if capitalized >= min(2, len(words)) and not s.isupper():
            # Pas de verbe conjugué / mots d'état-civil
            if not re.search(
                r'\b(is|are|was|were|have|has|been|est|sont|était|avec|pour|dans|chez|depuis|'
                r'including|including|and|or|et|ou)\b', s, re.I
            ):
                return True
    return False

def _clean_title(s: str) -> str:
    """Nettoie les symboles parasites d'un titre de poste."""
    # Supprimer les bullets/flèches en début
    s = re.sub(r'^[-•*·▪▸►➢✓✔✦→]\s*', '', s.strip())
    # Supprimer tout ce qui suit ➢ ou | ou • en milieu de chaîne
    s = re.sub(r'\s*[➢►▸•|]\s.*$', '', s)
    return s.strip()

def _detect_job_title(sections: list[dict], final_text: str) -> str:
    """
    Cherche le titre de poste dans cet ordre de priorité :
      1. Section "general" (lignes avant le 1er header)
      2. Premier titre d'expérience
      3. Toute ligne courte du texte ressemblant à un poste
    """
    # 1. Section général (avant le premier vrai header)
    for sec in sections:
        if _norm(sec.get("theme", "")) == "general":
            for line in sec.get("lines", []):
                s = line.strip()
                if _is_job_title(s):
                    return _clean_title(s)

    # 2. Premier titre dans les expériences
    for sec in sections:
        if _norm(sec.get("theme", "")) in ("general",):
            continue
        group = THEME_TO_GROUP.get(_norm(sec.get("theme", "")))
        if group == "experience":
            blocks = _parse_experience_blocks(
                [l.strip() for l in sec.get("lines", []) if l.strip()]
            )
            if blocks and blocks[0].get("title"):
                return _clean_title(blocks[0]["title"])
            break

    # 3. Fallback : parcourir le texte brut
    skip_next = False
    for line in final_text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.lower().startswith("identifiant candidat"):
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        if _is_job_title(s):
            return _clean_title(s)

    return ""


# ── Parseur de blocs d'expérience ─────────────────────────────────────────────
def _parse_experience_blocks(lines: list[str]) -> list[dict]:
    """
    Découpe les lignes en blocs {title, company, period, bullets}.

    Formats gérés :
      A) Titre  [sur ligne séparée]          puis  Date  (FR classique)
      B) Titre + Date  sur la même ligne     (espace entre les deux)
      C) Titre + Date  collés sans espace    (artefact PDF)
      D) Date: Entreprise  sur une ligne     puis  Titre  (format Angola/UK)
         ex: "Jan. 2022 – Present: Ocean Atlantic Petroleum, Angola"
      E) Date • Titre, Entreprise  sur une ligne  (format Proserv/NO)
         ex: "2024 – Present • Sales Director, Proserv Norge AS"
    """
    blocks: list[dict] = []
    current: dict | None = None
    pending_headers: list[str] = []

    # Lignes à ignorer dans les blocs d'expérience (artefacts OCR ou état-civil)
    _NOISE_LINE_RE = re.compile(
        r'^(\d{1,2}|[A-Z]{1,3})$'          # "1", "2", "B", "UK" seuls
        r'|Married|Single|Divorced|Widowed'  # état-civil
        r'|Based\s+in|Nationality'           # localisation
        r'|^\s*[•\-]\s*$',                  # bullet vide
        re.IGNORECASE,
    )

    def is_bullet(s: str) -> bool:
        return bool(re.match(r'^[-•*·▪▸►➢→✓✔✦]\s?', s.strip()))

    def is_pure_period(s: str) -> bool:
        stripped = s.strip()
        if _PERIOD_RE.fullmatch(stripped):
            return True
        if _DATE_RE.search(stripped) and len(stripped.split()) <= 8:
            return True
        return False

    def flush(title: str, company: str, period: str) -> None:
        nonlocal current
        if current is not None:
            blocks.append(current)
        current = {"title": title, "company": company, "period": period, "bullets": []}

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # Ignorer les lignes-bruit (artefacts OCR, état-civil parasite)
        if _NOISE_LINE_RE.search(s):
            continue

        # ── Bullets ───────────────────────────────────────────────────────────
        # Tester d'abord les formats avec date en tête, AVANT de tester bullet
        # car "2024 • Sales Director" commence par une date, pas un bullet

        # ── Format D : "Période: Entreprise"  (date en tête suivie de ':') ───
        # ex: "Jan. 2022 – Present: Ocean Atlantic Petroleum, Angola"
        m_d = _PERIOD_RE.match(s)
        if m_d:
            period_part = m_d.group(0).strip()
            rest = s[m_d.end():].lstrip(': –-').strip()
            if rest:
                # Titre viendra sur la prochaine ligne non-bullet
                flush("", rest, period_part)
            else:
                # Ligne = période pure, le titre est dans pending_headers
                if len(pending_headers) >= 2:
                    title   = pending_headers[0]
                    company = " | ".join(pending_headers[1:])
                elif len(pending_headers) == 1:
                    title, company = pending_headers[0], ""
                else:
                    title, company = "", ""
                pending_headers = []
                flush(title, company, period_part)
            continue

        # ── Format E : "Période • Titre, Entreprise"  (bullet comme séparateur)
        # ex: "2024 – Present • Sales Director, Proserv Norge AS (Trondheim)"
        m_e = _PERIOD_RE.search(s)
        if m_e and m_e.start() == 0:
            after_period = s[m_e.end():].lstrip()
            # Vérifier qu'il y a un séparateur bullet ou tiret après la date
            sep_m = re.match(r'^[\u2022\u00b7\u25aa\u25b8\u25ba\u27a2\u2714\u2713\-\u2013,]\s*', after_period)
            if sep_m:
                rest = after_period[sep_m.end():].strip()
                # rest = "Sales Director, Proserv Norge AS"
                if ',' in rest:
                    parts = rest.split(',', 1)
                    title_part   = parts[0].strip()
                    company_part = parts[1].strip()
                else:
                    title_part, company_part = rest, ""
                flush(title_part, company_part, m_e.group(0).strip())
                continue

        # ── Bullets ───────────────────────────────────────────────────────────
        # (après les formats D/E pour ne pas capturer "2024 • ..." comme bullet)
        if is_bullet(s):
            if current is None:
                current = {"title": "", "company": "", "period": "", "bullets": []}
            clean = re.sub(r'^[-•*·▪▸►➢✓✔]\s?', '', s).strip()
            if clean:
                current["bullets"].append(clean)
            continue

        # ── Format B/C : Titre + Date sur la même ligne ───────────────────────
        split = _split_title_from_period(s)
        if split:
            title_part, period_part = split
            full_title = " – ".join(pending_headers + [title_part]) if pending_headers else title_part
            pending_headers = []
            flush(full_title, "", period_part)
            continue

        # ── Format A : ligne de texte ordinaire ───────────────────────────────
        if current is None or not current["period"]:
            # Avant toute période → en-tête en attente
            pending_headers.append(s)
        else:
            # Après la période — classification intelligente
            words_s = s.split()
            n_words  = len(words_s)

            # Continuation d'un bullet (commence par minuscule)
            if s[0].islower() and current["bullets"]:
                current["bullets"][-1] = current["bullets"][-1].rstrip() + " " + s

            # Le titre du bloc courant est vide et la ligne est courte → titre du poste
            elif not current["title"] and n_words <= 8 and not _DATE_RE.search(s):
                current["title"] = s

            # Ligne ressemblant à un nom d'entreprise/organisation (courte, pas de verbe d'action)
            elif (not current.get("company") and n_words <= 6
                  and not re.match(
                      r'^(responsible|managed|led|developed|worked|helped|'
                      r'implemented|designed|built|ensured|coordinated|'
                      r'réalisé|géré|assuré|développé|contribué)', s, re.I
                  )):
                current["company"] = s

            else:
                # Ligne longue ou phrase d'action → bullet implicite
                current["bullets"].append(s)

    # ── Flush final ───────────────────────────────────────────────────────────
    if pending_headers:
        if current is not None:
            if not current.get("company"):
                current["company"] = " | ".join(pending_headers)
        else:
            current = {
                "title":   pending_headers[0],
                "company": " | ".join(pending_headers[1:]) if len(pending_headers) > 1 else "",
                "period":  "",
                "bullets": [],
            }
    if current is not None:
        blocks.append(current)

    return blocks


# ── Rendu LaTeX ────────────────────────────────────────────────────────────────
def _render_itemize(lines: list[str], color: str = "Ink") -> str:
    items = []
    for line in lines:
        # Nettoyer tous types de bullets (y compris ➢ → ▪)
        s = re.sub(r'^[-•*·▪▸►➢→✓✔✦]\s?', '', line.strip())
        if s:
            items.append(f"\\item {_esc(s)}")
    if not items:
        return ""
    color_cmd = f"\\color{{{color}}}\n" if color != "Ink" else ""
    return f"\\begin{{itemize}}\n{color_cmd}" + "\n".join(items) + "\n\\end{itemize}"


def _render_itemizea(lines: list[str]) -> str:
    items = []
    for line in lines:
        s = re.sub(r'^[-•*·▪▸►➢→✓✔✦]\s?', '', line.strip())
        if s:
            items.append(f"\\item {_esc(s)}")
    if not items:
        return ""
    return "\\begin{itemizea}\n" + "\n".join(items) + "\n\\end{itemizea}"


# Regex : détecte "Clé: valeur1, valeur2" (skills catégorisés)
_CATEGORY_ITEM_RE = re.compile(r'^([^:]{2,40}):\s+(.+)$')

def _render_skills(lines: list[str], sidebar: bool = False) -> str:
    """
    Rend les compétences.
    Si les lignes sont au format "Catégorie: item1, item2, item3", on rend
    chaque catégorie en gras suivie de ses items — générique FR/EN.
    Sinon, rendu liste standard.
    """
    color = "white" if sidebar else "Ink"

    # Détecter si la majorité des lignes sont au format "Catégorie: items"
    category_lines = [l for l in lines if _CATEGORY_ITEM_RE.match(l.strip())]
    has_categories = len(category_lines) >= max(1, len(lines) // 2)

    if has_categories:
        parts = []
        if sidebar:
            parts.append(f"\\color{{{color}}}")
        for line in lines:
            s = line.strip()
            s = re.sub(r'^[-•*·▪▸►]\s?', '', s)
            m = _CATEGORY_ITEM_RE.match(s)
            if m:
                key   = _esc(m.group(1).strip())
                value = _esc(m.group(2).strip())
                if sidebar:
                    parts.append(f"{{\\bfseries {key}:}} {value}\\par\\vspace{{1pt}}")
                else:
                    parts.append(f"\\noindent{{\\bfseries\\color{{Brand}} {key}:}} {value}\\par\\vspace{{2pt}}")
            elif s:
                parts.append(f"{_esc(s)}\\par\\vspace{{2pt}}")
        return "\n".join(parts)
    else:
        return _render_itemize(lines, color=color)


def _render_languages(lines: list[str], sidebar: bool = True) -> str:
    """
    Rend les langues — gère tous les formats courants :
      - Une langue par ligne : "English: Native" / "Anglais (C1)" / "English – Advanced"
      - Toutes sur une ligne séparées par | ou , : "English (fluent) | French (native)"
      - Préfixe "Langues:" : "Langues: Français (natif), Anglais (courant)"
    """
    color = "white" if sidebar else "Ink"
    parts = []
    if sidebar:
        parts.append(f"\\color{{{color}}}")

    # Éclater les lignes multi-langues (séparées par | ou ,  ou ;)
    expanded: list[str] = []
    for raw in lines:
        s = re.sub(r'^[-•*·▪▸►]\s?', '', raw.strip())
        # Retirer préfixe "Langues:" / "Languages:"
        s = re.sub(r'^(langues?|languages?)\s*:\s*', '', s, flags=re.IGNORECASE)
        # Éclater sur | ou  ; (mais pas la virgule seule — "spoken and written, German" confond)
        if '|' in s or ';' in s:
            for part in re.split(r'\s*[|;]\s*', s):
                if part.strip():
                    expanded.append(part.strip())
        else:
            expanded.append(s)

    # Pattern : "Langue: Niveau" ou "Langue – Niveau" ou "Langue (Niveau)"
    _LANG_RE = re.compile(
        r'^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\-]{0,28}?)'  # Langue (commence par lettre)
        r'\s*[:\-–(]\s*'                             # Séparateur
        r'([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9\s\+\-/,]{0,39})'  # Niveau
        r'\)?$',
        re.IGNORECASE,
    )

    for s in expanded:
        if not s:
            continue
        m = _LANG_RE.match(s)
        if m:
            lang  = _esc(m.group(1).strip())
            level = _esc(m.group(2).strip())
            if sidebar:
                parts.append(f"{{\\bfseries {lang}:}} {level}\\par\\vspace{{2pt}}")
            else:
                parts.append(
                    f"\\noindent{{\\bfseries\\color{{Brand}} {lang}}} "
                    f"\\hfill{{\\small\\color{{Ink}} {level}}}\\par\\vspace{{2pt}}"
                )
        else:
            parts.append(f"{_esc(s)}\\par\\vspace{{2pt}}")

    return "\n".join(parts)


def _render_paragraph(lines: list[str]) -> str:
    """
    Texte courant : joint les lignes en un seul bloc de texte fluide.
    Deux lignes vides consécutives = séparateur de paragraphe.
    """
    # Joindre toutes les lignes non vides en un seul texte fluide
    # (les lignes ont déjà été recollées par _rejoin_lines)
    parts: list[str] = []
    current_block: list[str] = []

    for line in lines:
        s = line.strip()
        if not s:
            if current_block:
                parts.append(" ".join(current_block))
                current_block = []
        else:
            current_block.append(_esc(s))

    if current_block:
        parts.append(" ".join(current_block))

    return "\n\n".join(parts) if parts else ""


_ALL_BULLETS_RE = re.compile(r'^[-•*·▪▸►➢→✓✔✦]\s?')

def _render_mixed(lines: list[str]) -> str:
    """
    Rend un bloc de lignes qui peut mélanger texte courant et bullets.
    Préserve l'ordre exact des lignes extraites du CV.
    Les lignes texte sont regroupées en paragraphes fluides.
    Les lignes bullets sont regroupées en listes.
    """
    parts: list[str] = []
    text_buf: list[str] = []
    bullet_buf: list[str] = []

    def flush_text():
        if text_buf:
            parts.append(_render_paragraph(text_buf))
            text_buf.clear()

    def flush_bullets():
        if bullet_buf:
            parts.append(_render_itemize(bullet_buf))
            bullet_buf.clear()

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if _ALL_BULLETS_RE.match(s):
            flush_text()
            bullet_buf.append(s)
        else:
            flush_bullets()
            text_buf.append(s)

    flush_text()
    flush_bullets()
    return "\n".join(parts)


def _render_experience_lines(lines: list[str]) -> str:
    if not lines:
        return ""
    blocks = _parse_experience_blocks(lines)
    parts = []
    for i, b in enumerate(blocks):
        # Nettoyer les tirets/espaces parasites en début de champ
        raw_title   = re.sub(r'^[\s\-–•·▪▸►➢→]+', '', b.get("title",   "")).strip()
        raw_company = re.sub(r'^[\s\-–•·▪▸►➢→]+', '', b.get("company", "")).strip()
        raw_period  = b.get("period", "").strip()
        title   = _esc(raw_title)
        company = _esc(raw_company)
        period  = _esc(raw_period)
        bullets = [bl for bl in b.get("bullets", []) if bl.strip()]

        if title or period or company:
            # Séparateur entre blocs (sauf le premier)
            if i > 0:
                parts.append("\\vspace{6pt}")
            parts.append("\\begin{samepage}")
            parts.append(f"\\role{{{title}}}{{{company}}}{{{period}}}")
            if bullets:
                items = "\n".join(
                    f"\\item {_esc(bl)}" for bl in bullets
                )
                if items:
                    parts.append(
                        f"\\begin{{itemize}}\n{items}\n\\end{{itemize}}"
                    )
            parts.append("\\end{samepage}")
        elif bullets:
            if i > 0:
                parts.append("\\vspace{4pt}")
            items = "\n".join(
                f"\\item {_esc(bl)}" for bl in bullets if bl.strip()
            )
            if items:
                parts.append(
                    f"\\begin{{itemize}}\n{items}\n\\end{{itemize}}"
                )
    return "\n".join(parts)


# ── Construction de la colonne gauche ──────────────────────────────────────────
def _build_left_column(groups: dict[str, list[str]]) -> str:
    parts: list[str] = []

    for group in LEFT_GROUPS_ORDER:
        lines = groups.get(group, [])
        if not lines:
            continue

        title = GROUP_DISPLAY_TITLE[group]
        # Les titres GROUP_DISPLAY_TITLE contiennent déjà le LaTeX voulu (ex: \&)
        # → pas d'échappement supplémentaire
        parts.append(f"\\mainhead{{{title}}}")

        if group == "resume":
            # Détecter bullets (y compris ➢ → et autres flèches)
            _BULLET_RE = re.compile(r'^[-•*·▪▸►➢→✓✔✦]\s?')
            text_lines   = [l for l in lines if not _BULLET_RE.match(l.strip())]
            bullet_lines = [l for l in lines if _BULLET_RE.match(l.strip())]
            if text_lines:
                parts.append(_render_paragraph(text_lines))
            if bullet_lines:
                # Nettoyer les flèches/bullets avant rendu
                cleaned = [re.sub(r'^[-•*·▪▸►➢→✓✔✦]\s?', '', l.strip()) for l in bullet_lines]
                parts.append(_render_itemizea(cleaned))

        elif group == "experience":
            parts.append(_render_experience_lines(lines))

        elif group in ("projects", "certifications"):
            has_dates = any(_DATE_RE.search(l) for l in lines)
            # N'utiliser _parse_experience_blocks que si vraiment structuré
            # (dates + titres de postes, pas juste une liste de certifs avec dates)
            all_bullets = all(_ALL_BULLETS_RE.match(l.strip()) for l in lines if l.strip())
            # Vérifier qu'il y a au moins une ligne non-bullet non-date → vrai bloc
            non_bullet_non_date = [
                l for l in lines
                if l.strip()
                and not _ALL_BULLETS_RE.match(l.strip())
                and not _PERIOD_RE.fullmatch(l.strip())
                and not _DATE_RE.fullmatch(l.strip())
                and len(l.strip().split()) >= 2
            ]
            if has_dates and non_bullet_non_date and not all_bullets:
                parts.append(_render_experience_lines(lines))
            else:
                parts.append(_render_mixed(lines))

        elif group == "skills":
            parts.append(_render_skills(lines, sidebar=False))

        elif group == "languages":
            parts.append(_render_languages(lines, sidebar=False))

        elif group == "soft_skills":
            parts.append(_render_itemizea(lines))

        else:
            parts.append(_render_mixed(lines))

        parts.append("\\vspace{6pt}\n")

    return "\n".join(parts)


# ── Construction de la barre latérale ─────────────────────────────────────────
def _build_right_sidebar(groups: dict[str, list[str]]) -> str:
    parts: list[str] = []

    for group in RIGHT_GROUPS_ORDER:
        lines = groups.get(group, [])
        if not lines:
            continue

        title = GROUP_DISPLAY_TITLE[group]
        # Pas d'échappement sur les titres (ils contiennent déjà du LaTeX valide)
        parts.append(f"\\sidehead{{{title}}}")

        if group == "education":
            # La formation a souvent des blocs structurés (diplôme / école / date)
            has_dates = any(_DATE_RE.search(l) for l in lines)
            if has_dates:
                # Rendu structuré comme les expériences (adapté colonne blanche)
                blocks = _parse_experience_blocks(lines)
                for i, b in enumerate(blocks):
                    t = _esc(b.get("title", "").strip())
                    c = _esc(b.get("company", "").strip())
                    p = _esc(b.get("period", "").strip())
                    buls = b.get("bullets", [])
                    if t or c or p:
                        if i > 0:
                            parts.append("\\vspace{5pt}")
                        if t:
                            parts.append(f"{{\\bfseries\\color{{white}} {t}}}\\par")
                        if c:
                            parts.append(f"{{\\itshape\\color{{white}} {c}}}\\par")
                        if p:
                            parts.append(f"{{\\small\\color{{white}} {p}}}\\par")
                    if buls:
                        items = "\n".join(f"\\item {_esc(bl)}" for bl in buls if bl.strip())
                        if items:
                            parts.append(
                                f"\\begin{{itemize}}\n\\color{{white}}\n{items}\n\\end{{itemize}}"
                            )
            else:
                parts.append(_render_itemize(lines, color="white"))
        elif group == "skills":
            parts.append(_render_skills(lines, sidebar=True))
        elif group == "languages":
            parts.append(_render_languages(lines, sidebar=True))
        elif group == "soft_skills":
            parts.append(_render_itemize(lines, color="white"))
        else:
            parts.append(_render_itemize(lines, color="white"))

        parts.append("\\vspace{4mm}\n")

    return "\n".join(parts)


# ── Génération du .tex complet ────────────────────────────────────────────────
def _render_tex(structured_data: dict) -> str:
    candidate_id = structured_data.get("candidate_id", "CANDIDAT_INCONNU")
    raw_sections: list[dict] = structured_data.get("sections", [])
    final_text: str = structured_data.get("final_anonymized_text", "")

    # 1. Re-segmenter les headers cachés dans les lines
    sections = _resegment(raw_sections)

    # 2. Détecter le titre de poste
    job_title = _detect_job_title(sections, final_text)

    # 3. Regrouper par groupe canonique
    groups = _group_sections(sections)

    # 4. Construire les colonnes
    left_col  = _build_left_column(groups)
    right_col = _build_right_sidebar(groups)

    tex = r"""\documentclass[10pt]{article}

\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[sfdefault]{carlito}
\usepackage[light]{montserrat}
\usepackage{xcolor}
\usepackage[none]{hyphenat}
\sloppy
\usepackage{tikz}
\usetikzlibrary{calc}
\usepackage{enumitem}
\usepackage{ragged2e}
\usepackage{hyperref}
\usepackage{microtype}
\usepackage[a4paper]{geometry}
\usepackage{eso-pic}
\usepackage{paracol}
\usepackage{graphicx}
\usepackage{fancyhdr}
\usepackage{changepage}

\definecolor{Sidebar}{HTML}{19395E}
\definecolor{Brand}{HTML}{2a2454}
\definecolor{Accent}{HTML}{0F9ED5}
\definecolor{Ink}{HTML}{232323}
\color{Ink}

\hypersetup{colorlinks=true,linkcolor=Brand,urlcolor=Accent}

\newlength{\RightBar}
\setlength{\RightBar}{70mm}
\newlength{\Gutter}
\setlength{\Gutter}{5mm}
\setlength{\columnsep}{\Gutter}

\newlength{\SidebarPadL}
\setlength{\SidebarPadL}{4mm}
\newlength{\SidebarPadR}
\setlength{\SidebarPadR}{4mm}

\newlength{\FooterReserve}
\setlength{\FooterReserve}{20mm}
\newlength{\TopClearance}
\setlength{\TopClearance}{22mm}

\geometry{
  left=14mm,
  right=1mm,
  top=\dimexpr14mm+\TopClearance\relax,
  bottom=\FooterReserve,
  includefoot
}

\setlength{\footskip}{12mm}
\setlength{\parindent}{0pt}
\setlength{\parskip}{2pt}

\setlist[itemize]{leftmargin=*,labelindent=0pt,labelsep=2.2mm,align=parleft,itemsep=1pt,topsep=2pt,label=\textbullet}

\newlength{\TitlePad}
\setlength{\TitlePad}{10mm}

\newcommand{\jobtitle}[1]{%
  \begingroup
    \parbox[t]{\dimexpr\textwidth-\RightBar-\Gutter-\TitlePad\relax}{%
      \RaggedRight
      \let\oldslash\slash
      \renewcommand{\slash}{\oldslash\penalty0\hspace{0pt}}%
      \emergencystretch=1em
      {\titlefont\Large\bfseries\color{Brand} #1}%
    }%
  \par
  \endgroup
}

\newlist{itemizea}{itemize}{1}
\setlist[itemizea]{leftmargin=0pt,labelindent=0pt,labelsep=0pt,itemsep=2pt,topsep=2pt,label={} }

\newcommand{\mainhead}[1]{%
  \noindent{\bfseries\color{Accent}\MakeUppercase{#1}}\par\vspace{-7pt}
  \noindent\color{Brand}\rule{\linewidth}{0.8pt}\par\vspace{2pt}\color{Ink}
}

\newcommand{\sidehead}[1]{%
  {\bfseries\MakeUppercase{#1}}\par\vspace{-7pt}
  \color{white}\rule{\linewidth}{0.5pt}\par\vspace{2pt}\color{white}
}

\newcommand{\rolesize}{\fontsize{11.5}{13}\selectfont}

\newcommand{\role}[3]{%
  \vspace{4pt}%
  \noindent\textbf{\color{Brand}\rolesize #1}\par\vspace{-4pt}%
  \noindent{\itshape\color{Brand} #2}%
  \ifx\relax#3\relax\else\hfill{\bfseries\itshape\color{Brand} #3}\fi\par\vspace{2pt}%
}

\newcommand{\TopPuzzle}{%
  \AddToShipoutPictureBG{%
    \begin{tikzpicture}[remember picture,overlay]
      \node (puzbg) [anchor=north east, inner sep=0pt] at
        ([xshift=-\RightBar+25.71mm,yshift=-7mm]current page.north east)
        {\includegraphics[width=44mm]{assets/puzzle1.png}};
    \end{tikzpicture}%
  }%
  \AddToShipoutPictureFG{%
    \begin{tikzpicture}[remember picture,overlay]
      \node (puz) [anchor=north east, inner sep=0pt, opacity=0] at
        ([xshift=-\RightBar+25.71mm,yshift=-9mm]current page.north east)
        {\includegraphics[width=44mm]{assets/puzzle1.png}};
    \end{tikzpicture}%
  }%
}

\fancypagestyle{cvfooter}{%
  \fancyhf{}
  \fancyfoot[L]{}
  \renewcommand{\headrulewidth}{0pt}
  \renewcommand{\footrulewidth}{0pt}
}

\newlength{\LeftMargin}
\setlength{\LeftMargin}{14mm}

\newcommand{\LeftMainFooter}{%
  \AddToShipoutPictureFG{%
    \begin{tikzpicture}[remember picture,overlay]
      \node[anchor=south west, inner sep=0pt] at
        ([xshift=\LeftMargin,yshift=8mm]current page.south west)
        {\makebox[\dimexpr\textwidth-\RightBar-\Gutter\relax][c]{%
            \raisebox{-7pt}{\includegraphics[height=10mm]{assets/OIM_logo.png}}\hspace{0mm}%
            {\small\bfseries\color{Accent}\mbox{Qualité, Intégrité, Fiabilité}}%
        }};
    \end{tikzpicture}%
  }%
}

\newcommand{\RightSidebarFooter}{%
  \AddToShipoutPictureFG{%
    \begin{tikzpicture}[remember picture,overlay]
      \node[anchor=south, inner sep=0pt] at
        ($ (current page.south east)!0.5!([xshift=-\RightBar]current page.south east)+ (0mm, 8mm) $)
        {\begin{minipage}[t]{\dimexpr\RightBar-2\SidebarPadL\relax}
           \centering
           {\scriptsize\color{white!92}\textbf{OIM France SAS}}\\[-1pt]
           {\scriptsize\color{white!85}RCS Saint Nazaire 948 296 983}\\[-1pt]
           {\scriptsize\color{white!80}12, allée des Alizés, 44380 Pornichet, France}
         \end{minipage}};
    \end{tikzpicture}%
  }%
}

\AddToShipoutPictureBG{%
  \begin{tikzpicture}[remember picture,overlay]
    \fill[Sidebar] ([xshift=-\RightBar]current page.north east)
      rectangle (current page.south east);
  \end{tikzpicture}%
}

\begin{document}
\pagestyle{cvfooter}
\TopPuzzle
\vspace*{-\TopClearance}
\LeftMainFooter
\RightSidebarFooter

\setcolumnwidth{\dimexpr\textwidth-\RightBar-\Gutter\relax,\RightBar}

\begin{paracol}{2}
\begin{leftcolumn}

\newcommand{\titlefont}{\fontfamily{Montserrat-LF}\selectfont}

""" + (f"\\jobtitle{{{_esc(job_title)}}}\n\\vspace{{2pt}}\n" if job_title else "") + r"""
\noindent{\small\color{Brand}\bfseries """ + _esc(candidate_id) + r"""}

\vspace{3pt}

\par{\small\color{Brand}\itshape
Présenté par OIM, votre partenaire de confiance spécialisé en services dans l'inspection qualité industrielle.
Nous mettons à votre disposition des profils hautement qualifiés pour vous aider.}

\vspace{2pt}

\end{leftcolumn}
\end{paracol}

\vspace{6pt}

\begin{paracol}{2}
\RaggedRight

""" + left_col + r"""

\switchcolumn

\begin{adjustwidth}{\SidebarPadL}{\SidebarPadR}
\raggedright\color{white}

""" + right_col + r"""

\end{adjustwidth}
\end{paracol}

\end{document}
"""
    return tex


# ── Compilation pdflatex ──────────────────────────────────────────────────────
def build_cv_pdf(structured_data: dict, output_path: str) -> str:
    """
    Génère le PDF CV en compilant le template LaTeX rempli.

    Args:
        structured_data : dict issu du JSON structuré
        output_path     : chemin de destination du PDF final

    Returns:
        Le chemin absolu du PDF généré
    """
    tex_content = _render_tex(structured_data)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Copier les assets
        assets_src = TEMPLATES_DIR / "assets"
        if assets_src.exists():
            shutil.copytree(assets_src, tmp / "assets")

        # Écrire le .tex
        tex_file = tmp / "cv_output.tex"
        tex_file.write_text(tex_content, encoding="utf-8")

        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory", str(tmp),
            str(tex_file),
        ]

        # 2 passes (tikz / paracol)
        for _ in range(2):
            result = subprocess.run(cmd, cwd=str(tmp), capture_output=True)

        pdf_generated = tmp / "cv_output.pdf"
        if not pdf_generated.exists():
            log_path = tmp / "cv_output.log"
            log = log_path.read_text(encoding="latin-1", errors="replace") if log_path.exists() else ""
            stdout = result.stdout.decode("latin-1", errors="replace") if result.stdout else ""
            combined = log or stdout
            errors = [l for l in combined.split("\n") if l.startswith("!") or "Error" in l]
            raise RuntimeError(
                f"pdflatex a échoué (code {result.returncode}).\n"
                + "\n".join(errors[:20])
            )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf_generated, output)

    return output_path
