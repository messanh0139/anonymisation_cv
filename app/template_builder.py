"""
template_builder.py

Génère un PDF CV anonymisé et structuré à partir du JSON structuré.
Design propre, professionnel, adapté au recrutement.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette de couleurs ──────────────────────────────────────────────────────
COLOR_PRIMARY = colors.HexColor("#1A3A5C")    # bleu marine – titres sections
COLOR_ACCENT = colors.HexColor("#2E86AB")     # bleu clair   – entête
COLOR_LIGHT = colors.HexColor("#F5F7FA")      # fond bandeau candidat
COLOR_TEXT = colors.HexColor("#2C2C2C")       # texte courant
COLOR_MUTED = colors.HexColor("#6C757D")      # sous-texte grisé

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


# ── Styles ────────────────────────────────────────────────────────────────────
def _build_styles() -> dict:
    base = getSampleStyleSheet()

    styles = {
        "candidate_id": ParagraphStyle(
            "candidate_id",
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=colors.white,
            alignment=TA_CENTER,
            spaceAfter=2,
        ),
        "candidate_sub": ParagraphStyle(
            "candidate_sub",
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#CCDDEE"),
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "section_title": ParagraphStyle(
            "section_title",
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=COLOR_PRIMARY,
            spaceBefore=10,
            spaceAfter=3,
            leftIndent=0,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=9,
            textColor=COLOR_TEXT,
            leading=13,
            spaceAfter=1,
            leftIndent=4,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName="Helvetica",
            fontSize=9,
            textColor=COLOR_TEXT,
            leading=13,
            leftIndent=10,
            firstLineIndent=-6,
            spaceAfter=1,
            bulletText="•",
        ),
    }
    return styles


def _header_banner(candidate_id: str, source_file: str, styles: dict) -> list:
    """Bandeau supérieur avec identifiant candidat."""
    banner_data = [[
        Paragraph(candidate_id, styles["candidate_id"]),
    ]]
    sub_text = f"CV anonymisé  ·  Fichier source : {source_file}"
    banner_table = Table(
        [[Paragraph(candidate_id, styles["candidate_id"])]],
        colWidths=[PAGE_W - 2 * MARGIN],
    )
    banner_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))

    sub_table = Table(
        [[Paragraph(sub_text, styles["candidate_sub"])]],
        colWidths=[PAGE_W - 2 * MARGIN],
    )
    sub_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))

    return [banner_table, sub_table, Spacer(1, 8)]


def _section_block(title: str, lines: list[str], styles: dict) -> list:
    """Bloc section : titre + séparateur + lignes de contenu."""
    elements = []

    # Titre de section
    elements.append(Paragraph(title.upper(), styles["section_title"]))
    elements.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=COLOR_ACCENT,
            spaceAfter=4,
        )
    )

    # Lignes de contenu
    for line in lines:
        stripped = line.strip()
        if not stripped:
            elements.append(Spacer(1, 3))
            continue

        # Détecter si c'est une puce ou une ligne normale
        if stripped.startswith(("-", "•", "*", "·")):
            clean = stripped.lstrip("-•*· ").strip()
            elements.append(Paragraph(f"• {clean}", styles["bullet"]))
        else:
            elements.append(Paragraph(stripped, styles["body"]))

    elements.append(Spacer(1, 6))
    return elements


def build_cv_pdf(structured_data: dict, output_path: str) -> str:
    """
    Génère un PDF CV à partir du JSON structuré.

    Args:
        structured_data: dict issu du JSON cv_anonymiser_structurer
        output_path: chemin de destination du PDF

    Returns:
        Le chemin du fichier PDF généré
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    styles = _build_styles()
    candidate_id = structured_data.get("candidate_id", "CANDIDAT_INCONNU")
    source_file = structured_data.get("source_file_name", "")
    sections = structured_data.get("sections", [])

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"CV Anonymisé – {candidate_id}",
        author="Pipeline CV Anonymisé",
    )

    story = []

    # ── Bandeau identifiant ───────────────────────────────────────────────────
    story.extend(_header_banner(candidate_id, source_file, styles))

    # ── Contenu : sections structurées ───────────────────────────────────────
    if sections:
        for section in sections:
            title = section.get("theme", "")
            lines = section.get("lines", [])

            if not title or not lines:
                continue

            story.extend(_section_block(title, lines, styles))

    else:
        # Fallback : texte brut si pas de sections
        raw_text = structured_data.get("final_anonymized_text", "")
        if raw_text:
            story.append(Paragraph("CONTENU DU CV", styles["section_title"]))
            story.append(HRFlowable(width="100%", thickness=1, color=COLOR_ACCENT, spaceAfter=4))
            for line in raw_text.split("\n"):
                if line.strip():
                    story.append(Paragraph(line.strip(), styles["body"]))

    # ── Pied de page discret ──────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_MUTED))
    story.append(Spacer(1, 4))
    footer_style = ParagraphStyle(
        "footer",
        fontName="Helvetica-Oblique",
        fontSize=7,
        textColor=COLOR_MUTED,
        alignment=TA_CENTER,
    )
    story.append(Paragraph(
        "Document généré automatiquement · Données anonymisées RGPD · Confidentiel",
        footer_style,
    ))

    doc.build(story)
    return output_path
