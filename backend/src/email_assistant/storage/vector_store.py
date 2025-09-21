from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Sequence

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from ..business.models import Email

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def email_to_text(email: Email) -> str:
    subject = email.subject or "(no subject)"
    sender = f"{email.from_name} <{email.from_email}>" if email.from_name else email.from_email
    to_part = ", ".join(email.to) if email.to else "(no recipients)"
    cc_part = ", ".join(email.cc) if email.cc else "(no cc)"
    lines = [
        f"Subject: {subject}",
        f"From: {sender}",
        f"To: {to_part}",
        f"Cc: {cc_part}",
        "Body:",
        email.body,
    ]
    return '\n'.join(lines)


def _build_snippet(email: Email, length: int = 240) -> str:
    body = (email.body or "").strip().replace("\r\n", " ").replace("\n", " ")
    if len(body) <= length:
        return body
    truncated = body[:length]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + "..."


class EmailVectorStore:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        self._index = faiss.IndexFlatIP(self.dimension)
        self._metadata: List[dict[str, Any]] = []
        self._mail_ids: set[str] = set()

    def clear(self) -> None:
        self._index = faiss.IndexFlatIP(self.dimension)
        self._metadata.clear()
        self._mail_ids.clear()

    def rebuild(self, emails: Sequence[Email]) -> None:
        self.clear()
        self.add_emails(emails)

    def add_emails(self, emails: Sequence[Email]) -> None:
        new_records: list[dict[str, Any]] = []
        texts: list[str] = []
        for email in emails:
            if email.mail_id in self._mail_ids:
                continue
            texts.append(email_to_text(email))
            new_records.append(
                {
                    "mail_id": email.mail_id,
                    "thread_id": email.thread_id,
                    "subject": email.subject,
                    "snippet": _build_snippet(email),
                }
            )

        if not texts:
            return

        embeddings = self.model.encode(
            texts,
            batch_size=64,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        if not isinstance(embeddings, np.ndarray):
            embeddings = np.asarray(embeddings, dtype=np.float32)
        embeddings = embeddings.astype(np.float32)
        self._index.add(embeddings)
        for record in new_records:
            self._metadata.append(record)
            self._mail_ids.add(record["mail_id"])

    def add_email(self, email: Email) -> None:
        self.add_emails([email])

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        normalized = query.strip()
        if not normalized or self._index.ntotal == 0:
            return []

        query_embedding = self.model.encode(
            [normalized],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)
        k = min(limit, self._index.ntotal)
        distances, indices = self._index.search(query_embedding, k)
        results: list[dict[str, Any]] = []
        for score, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            metadata = self._metadata[int(idx)].copy()
            metadata["score"] = float(score)
            results.append(metadata)
        return results

    def save(self, out_dir: str | Path) -> None:
        destination = Path(out_dir)
        destination.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(destination / "vectors.faiss"))
        payload = {
            "model_name": self.model_name,
            "records": self._metadata,
        }
        (destination / "meta.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, index_dir: str | Path, model_name: str | None = None) -> "EmailVectorStore":
        index_path = Path(index_dir)
        meta_path = index_path / "meta.json"
        vector_path = index_path / "vectors.faiss"
        if not meta_path.exists() or not vector_path.exists():
            raise FileNotFoundError(f"Missing index files in {index_path}")

        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        chosen_model = model_name or payload.get("model_name", DEFAULT_MODEL)

        store = cls(model_name=chosen_model)
        store._index = faiss.read_index(str(vector_path))
        store._metadata = payload.get("records", [])
        store._mail_ids = {record["mail_id"] for record in store._metadata if "mail_id" in record}
        return store
