"""Riigikogu API client: list active draft bills and extract their text.

Consolidates the proven fetch/extract logic from the old one-off scripts
(find_best_document, extract_docx, extract_pdf, fetch_with_retry) into a clean,
reusable module with backoff for the API's aggressive 429 rate limiting.

Listing:  GET /api/volumes/drafts?lang=et  ->  _embedded.content[] with
          {uuid, mark (=bill number), title, draftTypeCode, proceedingStatus, ...}
Per bill: GET /api/volumes/drafts/{uuid}  ->  {texts:[{file:{fileExtension,
          fileTitle, _links:{download:{href}}}}]}
"""

from __future__ import annotations
import io
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple, Iterator

import requests
import config

try:
    import fitz                      # PyMuPDF
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

API = config.RIIGIKOGU_API
DELAY = config.RIIGIKOGU_API_DELAY


def fetch_with_retry(url: str, max_retries: int = 4, base_delay: float = 10.0,
                     timeout: int = 60, transient_delay: float = 1.0
                     ) -> Optional[requests.Response]:
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError):
            if attempt < max_retries - 1:
                time.sleep(transient_delay * (2 ** attempt))
                continue
            return None

        if resp.status_code == 429:
            if attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt)
                time.sleep(wait)
                continue
            return None
        if 500 <= resp.status_code < 600:
            if attempt < max_retries - 1:
                time.sleep(transient_delay * (2 ** attempt))
                continue
            return None
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            if resp.status_code >= 500 and attempt < max_retries - 1:
                time.sleep(transient_delay * (2 ** attempt))
                continue
            raise
        return resp
    return None


def _activity_date(draft: Dict[str, Any]) -> str:
    return (draft.get("activeDraftStatusDate") or draft.get("initiated") or "")[:10]


def _in_corpus_window(draft: Dict[str, Any], cutoff: str) -> bool:
    return _activity_date(draft) >= cutoff or draft.get("proceedingStatus") == "IN_PROCESS"


def _older_than_cutoff(draft: Dict[str, Any], cutoff: str) -> bool:
    date = _activity_date(draft)
    return bool(date) and date < cutoff


def list_drafts(only_bills: bool = True, only_active: bool = True,
                page: int = 0, size: int = 50) -> List[Dict[str, Any]]:
    """Return draft summaries. only_bills -> draftTypeCode SE (seaduseelnõu);
    only_active -> proceedingStatus IN_PROCESS."""
    url = f"{API}/volumes/drafts?lang=et&page={page}&size={size}"
    if only_bills:
        url += "&draftTypeCode=SE"
    resp = fetch_with_retry(url)
    if not resp:
        return []
    content = resp.json().get("_embedded", {}).get("content", [])
    out = []
    for d in content:
        if only_bills and d.get("draftTypeCode") != "SE":
            continue
        if only_active and d.get("proceedingStatus") != "IN_PROCESS":
            continue
        out.append(d)
    return out


def iterate_corpus(cutoff: str, page_size: int = 50,
                   max_pages: int = 20) -> Iterator[Dict[str, Any]]:
    """Yield SE drafts with activity since cutoff, plus any still in process."""
    for page in range(max_pages):
        drafts = list_drafts(only_bills=True, only_active=False,
                             page=page, size=page_size)
        if not drafts:
            return

        se_drafts = [d for d in drafts if d.get("draftTypeCode") == "SE"]
        for draft in se_drafts:
            if _in_corpus_window(draft, cutoff):
                yield draft

        if se_drafts and all(_older_than_cutoff(d, cutoff) for d in se_drafts):
            return
        if page < max_pages - 1:
            time.sleep(DELAY)


def get_draft_texts(uuid: str) -> List[Dict[str, Any]]:
    resp = fetch_with_retry(f"{API}/volumes/drafts/{uuid}")
    return resp.json().get("texts", []) if resp else []


def find_best_document(texts: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """Prefer the bill text (eelnõu/algtekst) as DOCX (clean), else PDF.
    Returns (doc_type, download_url)."""
    docx_url = pdf_url = None
    for entry in texts:
        f = entry.get("file", {})
        title = f.get("fileTitle", "").lower()
        ext = f.get("fileExtension", "").lower()
        href = f.get("_links", {}).get("download", {}).get("href")
        if not href:
            continue
        if "seletuskiri" in title and "eelnõu" not in title:   # skip explanatory memo
            continue
        if "eelnõu" in title or "algtekst" in title:
            if ext == "docx":
                docx_url = docx_url or href
            elif ext == "pdf":
                pdf_url = pdf_url or href
    if docx_url:
        return "docx", docx_url
    if pdf_url:
        return "pdf", pdf_url
    return None, None


def extract_docx(url: str) -> Optional[str]:
    if not HAS_DOCX:
        return None
    resp = fetch_with_retry(url)
    if not resp:
        return None
    doc = Document(io.BytesIO(resp.content))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(parts)


def extract_pdf(url: str) -> Optional[str]:
    if not HAS_PDF:
        return None
    resp = fetch_with_retry(url)
    if not resp:
        return None
    doc = fitz.open(stream=resp.content, filetype="pdf")
    parts = [p.get_text().strip() for p in doc if p.get_text().strip()]
    doc.close()
    text = "\n\n".join(parts)
    # Image-only PDFs yield ~no text. OCR (pytesseract) is a future enhancement;
    # for now we signal too-little-text so the caller can skip rather than store junk.
    if len(text) < 200:
        return None
    return text


def extract_bill_text(uuid: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (text, method) for a draft's bill document, or (None, None)."""
    texts = get_draft_texts(uuid)
    time.sleep(DELAY)
    doc_type, url = find_best_document(texts)
    if not url:
        return None, None
    if doc_type == "docx":
        return extract_docx(url), "docx"
    return extract_pdf(url), "pdf_text"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
