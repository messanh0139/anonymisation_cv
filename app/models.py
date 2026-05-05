from dataclasses import dataclass, field
from typing import List


@dataclass
class CVInput:
    file_path: str
    file_name: str
    drive_file_id: str = ""
    source_version: str = ""
    source_email: str = ""
    subject: str = ""
    received: str = ""


@dataclass
class CandidateRegistryEntry:
    candidate_id: str
    drive_file_id: str
    source_version: str
    full_name: str
    original_file_name: str
    source_email: str = ""
    subject: str = ""
    received: str = ""


@dataclass
class CVResult:
    candidate_id: str
    original_file_name: str
    detected_name: str
    anonymized_text: str
    removed_fields: List[str] = field(default_factory=list)
    source_email: str = ""
    subject: str = ""
    received: str = ""
    ocr_used: str = "native"        # "native" | "ocr"
    extraction_score_native: float = 0.0   # score 0–100 méthode native
    extraction_score_ocr: float    = 0.0   # score 0–100 méthode OCR
    detected_language: str = "en"          # code ISO 639-1 : "fr", "en", etc.


@dataclass
class CVSection:
    theme: str
    lines: List[str] = field(default_factory=list)


@dataclass
class StructuredCV:
    candidate_id: str
    final_anonymized_text: str
    sections: List[CVSection] = field(default_factory=list)