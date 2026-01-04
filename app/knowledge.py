from pathlib import Path

def load_documents():
    base_dir = Path(__file__).resolve().parent
    company_data_dir = base_dir / "company_data"

    documents = []

    for file_path in company_data_dir.iterdir():
        if file_path.is_file():
            with open(file_path, "r", encoding="utf-8") as f:
                documents.append(f.read())

    return "\n".join(documents)
