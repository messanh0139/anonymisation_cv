from typing import Tuple

from app.extractor import extract_text_from_pdf_detailed
from app.anonymizer import identify_candidate, anonymize_text_with_candidate_id
from app.models import CVInput, CVResult, CandidateRegistryEntry
from app.lang_detector import detect_language


def process_cv(cv_input: CVInput) -> Tuple[CVResult, CandidateRegistryEntry]:
    extracted_text, extraction_method, score_native, score_ocr = extract_text_from_pdf_detailed(cv_input.file_path)

    # Détection automatique de la langue
    lang = detect_language(extracted_text)

    identity = identify_candidate(
        text=extracted_text,
        file_name=cv_input.file_name,
    )

    registry_entry = CandidateRegistryEntry(
        candidate_id=identity["candidate_id"],
        drive_file_id=cv_input.drive_file_id,
        source_version=cv_input.source_version,
        full_name=identity["detected_name"],
        original_file_name=cv_input.file_name,
        source_email=cv_input.source_email,
        subject=cv_input.subject,
        received=cv_input.received,
    )

    anonymized = anonymize_text_with_candidate_id(
        text=identity["normalized_text"],
        detected_name=identity["detected_name"],
        candidate_id=identity["candidate_id"],
        spacy_persons=identity.get("spacy_persons"),
    )

    result = CVResult(
        candidate_id=anonymized["candidate_id"],
        original_file_name=cv_input.file_name,
        detected_name=anonymized["detected_name"],
        anonymized_text=anonymized["anonymized_text"],
        removed_fields=anonymized["removed_fields"],
        source_email=cv_input.source_email,
        subject=cv_input.subject,
        received=cv_input.received,
        ocr_used=extraction_method,
        extraction_score_native=round(score_native, 1),
        extraction_score_ocr=round(score_ocr, 1),
        detected_language=lang,
    )

    return result, registry_entry