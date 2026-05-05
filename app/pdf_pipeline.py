"""
pdf_pipeline.py

Pipeline de génération de PDF anonymisés :
  1. Supprime les anciens PDFs dans cv_traiter
  2. Lit les JSON structurés depuis cv_anonymiser_structurer
  3. Valide + corrige chaque JSON
  4. Génère les PDFs en parallèle via pdflatex
  5. Upload les PDFs dans cv_traiter
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.drive_client import (
    download_file,
    get_drive_service,
    list_files_in_folder,
    upload_or_update_file,
)
from app.drive_processor import (
    PROCESSED_FOLDER_ID,
    STRUCTURED_JSON_FOLDER_ID,
    TEMP_DIR,
    OUTPUT_DIR,
    ensure_dirs,
)
from app.latex_builder import build_cv_pdf
from app.json_validator import validate_and_fix
from app.config_loader import CFG

logger = logging.getLogger(__name__)


def _delete_existing_pdfs(service) -> None:
    """Supprime tous les PDFs existants dans cv_traiter avant régénération."""
    files = list_files_in_folder(service, PROCESSED_FOLDER_ID)
    for f in files:
        if f["name"].lower().endswith(".pdf"):
            service.files().delete(fileId=f["id"]).execute()
            logger.info("[PDF] Supprimé : %s", f["name"])


def _process_one(service, file_info: dict) -> dict:
    """
    Traite un seul JSON → génère le PDF → upload.
    Retourne {"status": "ok"|"error", "file": ..., "error": ...}
    """
    json_name = file_info["name"]
    pdf_name  = json_name.replace("_structured.json", ".pdf")
    if not pdf_name.endswith(".pdf"):
        pdf_name = Path(json_name).stem + ".pdf"

    local_json_path = TEMP_DIR / json_name
    local_pdf_path  = OUTPUT_DIR / pdf_name

    try:
        # Télécharger le JSON
        download_file(service, file_info["id"], str(local_json_path))

        raw_bytes = local_json_path.read_bytes()
        structured_data = None
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                structured_data = json.loads(raw_bytes.decode(enc))
                break
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        if structured_data is None:
            raise ValueError(f"Impossible de décoder {json_name}")

        # Valider + corriger
        structured_data, warnings = validate_and_fix(structured_data)
        if warnings:
            logger.warning("[PDF] %s — avertissements : %s", pdf_name, warnings)

        # Générer le PDF
        build_cv_pdf(structured_data, str(local_pdf_path))

        # Upload
        upload_or_update_file(
            service=service,
            file_path=str(local_pdf_path),
            file_name=pdf_name,
            folder_id=PROCESSED_FOLDER_ID,
            mime_type="application/pdf",
        )
        logger.info("[PDF] ✓ %s", pdf_name)
        return {"status": "ok", "file": pdf_name}

    except Exception as exc:
        logger.error("[PDF] ✗ %s — %s", pdf_name, exc)
        return {"status": "error", "file": json_name, "error": str(exc)}

    finally:
        local_json_path.unlink(missing_ok=True)
        local_pdf_path.unlink(missing_ok=True)


def process_structured_to_pdf() -> dict:
    """
    Pour chaque JSON structuré dans cv_anonymiser_structurer :
      - Supprime les anciens PDFs dans cv_traiter
      - Télécharge le JSON, valide, génère le PDF
      - Upload dans cv_traiter (toujours remplacé)
    Traitement en parallèle selon config.yaml → pipeline.parallel_workers
    """
    ensure_dirs()
    service = get_drive_service()

    # 1. Lister les JSON structurés disponibles
    json_files = list_files_in_folder(service, STRUCTURED_JSON_FOLDER_ID)
    json_files = [
        f for f in json_files
        if f["name"].lower().endswith(".json") and "_structured" in f["name"].lower()
    ]

    if not json_files:
        return {
            "status": "ok",
            "message": "Aucun JSON structuré trouvé dans cv_anonymiser_structurer.",
            "success_count": 0,
            "skipped_count": 0,
            "error_count": 0,
        }

    # 2. Supprimer les anciens PDFs
    _delete_existing_pdfs(service)

    # 3. Traitement parallèle
    workers = CFG.get("pipeline", {}).get("parallel_workers", 3)
    results = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_process_one, service, fi): fi["name"]
            for fi in json_files
        }
        for future in as_completed(futures):
            results.append(future.result())

    success_count = sum(1 for r in results if r["status"] == "ok")
    error_count   = sum(1 for r in results if r["status"] == "error")
    errors        = [r for r in results if r["status"] == "error"]

    result = {
        "status": "ok",
        "message": "Génération PDF terminée",
        "success_count": success_count,
        "skipped_count": 0,
        "error_count": error_count,
    }
    if errors:
        result["errors"] = errors
    return result
