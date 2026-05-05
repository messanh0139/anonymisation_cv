from fastapi import FastAPI
from app.drive_processor import process_drive_pdfs
from app.pdf_pipeline import process_structured_to_pdf

app = FastAPI(
    title="CV Pipeline API",
    version="1.0.0",
    description="API de traitement automatique de CV depuis Google Drive",
)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@app.post("/process")
def process() -> dict:
    """Étape 1 : Extrait, anonymise et structure les CV depuis cv_entrants."""
    return process_drive_pdfs()


@app.post("/generate-pdfs")
def generate_pdfs() -> dict:
    """Étape 2 : Génère les PDF anonymisés et les dépose dans cv_traiter."""
    return process_structured_to_pdf()


@app.post("/run-all")
def run_all() -> dict:
    """Enchaîne les deux étapes : extraction/anonymisation puis génération PDF."""
    step1 = process_drive_pdfs()
    step2 = process_structured_to_pdf()
    return {
        "status": "ok",
        "step1_process": step1,
        "step2_generate_pdfs": step2,
    }