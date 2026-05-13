"""Synthesize a small corpus of PDFs for the RAG demo.

Produces N multi-page PDFs in data/source_pdfs/ from a tiny themed
fixture corpus (fake product manuals across a few departments). Each PDF
carries its own title, author, department, and revision date so the
metadata-driven retrieval demo (2d) has something concrete to filter on.

No third-party copyrighted material is used; all body text is generated
programmatically.
"""
from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

from faker import Faker
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
)

from config import SOURCE_PDF_DIR, DATA_DIR, load_settings  # noqa: F401

# Themed sections so the chunked text doesn't look like uniform Lorem
# Ipsum. Each PDF picks one department; sections drive section headings
# and the per-section body text the Faker fills in.
DEPARTMENTS = {
    "engineering": [
        "Architecture Overview",
        "Failure Modes",
        "Operational Runbook",
        "Performance Tuning",
        "Upgrade Procedure",
    ],
    "compliance": [
        "Scope and Definitions",
        "Audit Schedule",
        "Data Retention Policy",
        "Breach Response",
        "Exceptions Process",
    ],
    "support": [
        "Common Issues",
        "Triage Workflow",
        "Escalation Matrix",
        "Customer Communications",
        "Postmortem Template",
    ],
    "product": [
        "Release Highlights",
        "Known Limitations",
        "Roadmap",
        "Pricing Tiers",
        "Migration Guide",
    ],
}


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], spaceAfter=18, fontSize=20
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], spaceBefore=12, spaceAfter=8
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], leading=14, spaceAfter=8
        ),
    }


def _paragraph_text(fake: Faker, sentences: int) -> str:
    # Faker.paragraph() with variable_nb_sentences=False is deterministic
    # given the global seed set in main().
    return fake.paragraph(nb_sentences=sentences, variable_nb_sentences=False)


def _build_pdf(path: Path, fake: Faker, doc_id: str, title: str,
               author: str, department: str, revision: date) -> dict:
    styles = _styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=title,
        author=author,
        subject=f"{department.title()} reference document",
        keywords=f"demo,{department},rag,pdf",
    )
    story: list = [
        Paragraph(title, styles["title"]),
        Paragraph(
            f"Author: {author} &nbsp;&nbsp; Department: {department.title()} "
            f"&nbsp;&nbsp; Revision: {revision.isoformat()}",
            styles["body"],
        ),
        Spacer(1, 0.2 * inch),
    ]
    for section in DEPARTMENTS[department]:
        story.append(Paragraph(section, styles["h2"]))
        # 4-6 paragraphs per section, 5-8 sentences each, gives ~2 pages.
        for _ in range(random.randint(4, 6)):
            story.append(
                Paragraph(_paragraph_text(fake, random.randint(5, 8)),
                          styles["body"])
            )
        story.append(PageBreak())
    doc.build(story)
    return {
        "document_id": doc_id,
        "filename": path.name,
        "title": title,
        "author": author,
        "department": department,
        "revision": revision.isoformat(),
    }


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=settings.pdf_count)
    parser.add_argument("--seed", type=int, default=20260512)
    parser.add_argument("--out-dir", type=Path, default=SOURCE_PDF_DIR)
    args = parser.parse_args()

    random.seed(args.seed)
    fake = Faker()
    Faker.seed(args.seed)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = DATA_DIR / "pdf_manifest.jsonl"

    departments = list(DEPARTMENTS.keys())
    records = []
    for i in range(args.count):
        dept = departments[i % len(departments)]
        doc_id = uuid.UUID(int=random.getrandbits(128)).hex[:12]
        title = f"{dept.title()} Reference {i + 1:03d}: {fake.catch_phrase()}"
        author = fake.name()
        revision = date.today() - timedelta(days=random.randint(0, 365))
        filename = f"{dept}-{i + 1:03d}-{doc_id}.pdf"
        record = _build_pdf(
            args.out_dir / filename, fake, doc_id, title, author, dept, revision
        )
        records.append(record)
        print(f"  wrote {filename}")

    with manifest_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    print(f"Wrote {len(records)} PDFs to {args.out_dir}")
    print(f"Manifest at {manifest_path}")


if __name__ == "__main__":
    main()
