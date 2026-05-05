import csv
import json
from dataclasses import asdict
from pathlib import Path

from app.drive_client import (
    download_file,
    find_file_in_folder_by_name,
    get_drive_service,
    list_files_in_folder,
    upload_or_update_file,
)
from app.finalizer import build_final_anonymized_text
from app.models import CVInput, CandidateRegistryEntry
from app.pipeline import process_cv
from app.structurer import build_structured_cv
from app.config_loader import CFG

# ── IDs Google Drive — lus depuis config.yaml (section "drive") ──────────────
_drive = CFG.get("drive", {})
INPUT_FOLDER_ID           = _drive.get("input_folder_id",           "")
TECHNICAL_JSON_FOLDER_ID  = _drive.get("technical_json_folder_id",  "")
STRUCTURED_JSON_FOLDER_ID = _drive.get("structured_json_folder_id", "")
REGISTRY_FOLDER_ID        = _drive.get("registry_folder_id",        "")
PROCESSED_FOLDER_ID       = _drive.get("processed_folder_id",       "")

TEMP_DIR = Path("temp")
OUTPUT_DIR = Path("output")
REGISTRY_LOCAL_PATH = OUTPUT_DIR / "candidate_registry.csv"
ERRORS_LOCAL_PATH = OUTPUT_DIR / "errors.csv"


def ensure_dirs() -> None:
    TEMP_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def append_error_local(file_name: str, error_message: str) -> None:
    file_exists = ERRORS_LOCAL_PATH.exists()

    with ERRORS_LOCAL_PATH.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow(["file_name", "error_message"])

        writer.writerow([file_name, error_message])


def sync_registry_from_drive(service) -> None:
    """
    Télécharge toujours la dernière version du registre depuis Drive.
    """
    from googleapiclient.errors import HttpError

    remote_file = find_file_in_folder_by_name(
        service,
        REGISTRY_FOLDER_ID,
        "candidate_registry.csv",
    )

    if REGISTRY_LOCAL_PATH.exists():
        REGISTRY_LOCAL_PATH.unlink(missing_ok=True)

    if remote_file:
        try:
            download_file(service, remote_file["id"], str(REGISTRY_LOCAL_PATH))
        except HttpError as e:
            if e.resp.status == 404:
                pass  # Fichier supprimé entre-temps → on repart de zéro
            else:
                raise


def load_registry_entries() -> list[dict]:
    """
    Charge le registre CSV local.
    """
    if not REGISTRY_LOCAL_PATH.exists():
        return []

    entries = []

    with REGISTRY_LOCAL_PATH.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            entries.append({
                "candidate_id": (row.get("candidate_id") or "").strip(),
                "drive_file_id": (row.get("drive_file_id") or "").strip(),
                "source_version": (row.get("source_version") or "").strip(),
                "full_name": (row.get("full_name") or "").strip(),
                "original_file_name": (row.get("original_file_name") or "").strip(),
                "source_email": (row.get("source_email") or "").strip(),
                "subject": (row.get("subject") or "").strip(),
                "received": (row.get("received") or "").strip(),
            })

    return entries


def unique_processing_key(entry: dict) -> str:
    """
    Clé d'unicité stricte :
    drive_file_id + source_version
    """
    drive_file_id = entry.get("drive_file_id", "").strip()
    source_version = entry.get("source_version", "").strip()

    if drive_file_id and source_version:
        return f"{drive_file_id}::{source_version}"

    original_file_name = entry.get("original_file_name", "").strip().lower()
    return f"fallback::{original_file_name}"


def normalize_registry_entries(entries: list[dict]) -> list[dict]:
    """
    Déduplique le registre.
    """
    unique_entries = []
    seen_keys = set()

    for entry in entries:
        key = unique_processing_key(entry)

        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique_entries.append(entry)

    return unique_entries


def write_registry_entries(entries: list[dict]) -> None:
    """
    Réécrit le registre local proprement.
    """
    with REGISTRY_LOCAL_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        writer.writerow([
            "candidate_id",
            "drive_file_id",
            "source_version",
            "full_name",
            "original_file_name",
            "source_email",
            "subject",
            "received",
        ])

        for entry in entries:
            writer.writerow([
                entry.get("candidate_id", ""),
                entry.get("drive_file_id", ""),
                entry.get("source_version", ""),
                entry.get("full_name", ""),
                entry.get("original_file_name", ""),
                entry.get("source_email", ""),
                entry.get("subject", ""),
                entry.get("received", ""),
            ])


def build_processed_index(entries: list[dict]) -> dict[str, dict]:
    """
    Index anti-doublon basé sur drive_file_id + source_version.
    """
    return {
        unique_processing_key(entry): entry
        for entry in entries
    }


def append_registry_entry(entries: list[dict], entry: CandidateRegistryEntry) -> list[dict]:
    """
    Ajoute une entrée si elle n'existe pas déjà.
    """
    new_entry = {
        "candidate_id": entry.candidate_id,
        "drive_file_id": entry.drive_file_id,
        "source_version": entry.source_version,
        "full_name": entry.full_name,
        "original_file_name": entry.original_file_name,
        "source_email": entry.source_email,
        "subject": entry.subject,
        "received": entry.received,
    }

    existing_keys = {unique_processing_key(e) for e in entries}
    new_key = unique_processing_key(new_entry)

    if new_key in existing_keys:
        return entries

    entries.append(new_entry)
    return entries


def upload_registry_to_drive(service) -> None:
    """
    Met à jour le registre CSV sur Drive.
    """
    if REGISTRY_LOCAL_PATH.exists():
        upload_or_update_file(
            service=service,
            file_path=str(REGISTRY_LOCAL_PATH),
            file_name="candidate_registry.csv",
            folder_id=REGISTRY_FOLDER_ID,
            mime_type="text/csv",
        )


def build_output_payloads(result) -> tuple[dict, dict]:
    """
    Construit le JSON technique et le JSON structuré.
    """
    final_text = build_final_anonymized_text(
        text=result.anonymized_text,
        candidate_id=result.candidate_id,
    )

    structured_cv = build_structured_cv(
        final_text=final_text,
        candidate_id=result.candidate_id,
    )

    technical_output = {
        "candidate_id": result.candidate_id,
        "source_file_name": result.original_file_name,
        "detected_name": result.detected_name,
        "removed_fields": result.removed_fields,
        "anonymized_text": result.anonymized_text,
        "final_anonymized_text": final_text,
        "source_email": result.source_email,
        "subject": result.subject,
        "received": result.received,
        "ocr_used": result.ocr_used,
        "extraction_score_native": result.extraction_score_native,
        "extraction_score_ocr": result.extraction_score_ocr,
    }

    structured_output = asdict(structured_cv)
    structured_output["source_file_name"] = result.original_file_name
    structured_output["ocr_used"] = result.ocr_used
    structured_output["extraction_score_native"] = result.extraction_score_native
    structured_output["extraction_score_ocr"] = result.extraction_score_ocr

    return technical_output, structured_output


def save_local_json(file_path: Path, payload: dict) -> None:
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cleanup_local_files(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            path.unlink(missing_ok=True)


def process_drive_pdfs() -> dict:
    """
    Traite les CV présents sur Drive et ne retraite que les nouveaux
    ou les fichiers modifiés.
    """
    ensure_dirs()
    service = get_drive_service()

    # 1. Sync registre depuis Drive
    sync_registry_from_drive(service)

    # 2. Charger et nettoyer le registre
    registry_entries = load_registry_entries()
    registry_entries = normalize_registry_entries(registry_entries)
    write_registry_entries(registry_entries)
    upload_registry_to_drive(service)

    processed_index = build_processed_index(registry_entries)

    # 3. Lire les PDF dans CV_Entrants
    files = list_files_in_folder(service, INPUT_FOLDER_ID)
    pdf_files = [file_info for file_info in files if file_info["name"].lower().endswith(".pdf")]

    if not pdf_files:
        return {
            "status": "ok",
            "message": "Aucun fichier PDF trouvé dans CV_Entrants.",
            "success_count": 0,
            "skipped_count": 0,
            "error_count": 0,
        }

    success_count = 0
    skipped_count = 0
    error_count = 0

    for file_info in pdf_files:
        file_id = file_info["id"]
        file_name = file_info["name"]
        source_version = file_info.get("md5Checksum") or file_info.get("modifiedTime") or ""

        local_pdf_path = TEMP_DIR / file_name
        technical_json_path = OUTPUT_DIR / "technical.json"
        structured_json_path = OUTPUT_DIR / "structured.json"

        try:
            processing_key = f"{file_id}::{source_version}" if source_version else f"fallback::{file_name.lower()}"

            # Anti-doublon + détection de modification
            if processing_key in processed_index:
                skipped_count += 1
                continue

            download_file(service, file_id, str(local_pdf_path))

            cv_input = CVInput(
                file_path=str(local_pdf_path),
                file_name=file_name,
                drive_file_id=file_id,
                source_version=source_version,
            )

            result, registry_entry = process_cv(cv_input)

            technical_output, structured_output = build_output_payloads(result)

            technical_json_path = OUTPUT_DIR / f"{result.candidate_id}.json"
            structured_json_path = OUTPUT_DIR / f"{result.candidate_id}_structured.json"

            save_local_json(technical_json_path, technical_output)
            save_local_json(structured_json_path, structured_output)

            upload_or_update_file(
                service=service,
                file_path=str(technical_json_path),
                file_name=technical_json_path.name,
                folder_id=TECHNICAL_JSON_FOLDER_ID,
                mime_type="application/json",
            )

            upload_or_update_file(
                service=service,
                file_path=str(structured_json_path),
                file_name=structured_json_path.name,
                folder_id=STRUCTURED_JSON_FOLDER_ID,
                mime_type="application/json",
            )

            registry_entries = append_registry_entry(registry_entries, registry_entry)
            registry_entries = normalize_registry_entries(registry_entries)
            write_registry_entries(registry_entries)
            upload_registry_to_drive(service)

            processed_index = build_processed_index(registry_entries)

            success_count += 1

        except Exception as exc:
            append_error_local(file_name, str(exc))
            error_count += 1

        finally:
            cleanup_local_files(local_pdf_path, technical_json_path, structured_json_path)

    # ── Nettoyage final : aucun fichier ne doit rester en local ──────────────
    # Upload errors.csv sur Drive si des erreurs ont eu lieu
    if ERRORS_LOCAL_PATH.exists():
        upload_or_update_file(
            service=service,
            file_path=str(ERRORS_LOCAL_PATH),
            file_name=ERRORS_LOCAL_PATH.name,
            folder_id=REGISTRY_FOLDER_ID,
            mime_type="text/csv",
        )
    # Le registre et les erreurs sont déjà sur Drive → on purge le local
    cleanup_local_files(REGISTRY_LOCAL_PATH, ERRORS_LOCAL_PATH)
    # Cache embeddings sentence-transformers → inutile de le garder entre runs
    embeddings_cache = TEMP_DIR / "embeddings_cache.pkl"
    cleanup_local_files(embeddings_cache)

    return {
        "status": "ok",
        "message": "Traitement terminé",
        "success_count": success_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
    }