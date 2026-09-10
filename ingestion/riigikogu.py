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
from dataclasses import dataclass
import io
import os
import re
import shutil
import subprocess
import tempfile
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
MIN_TEXT_CHARS = 200
_TEXT_EXTS = ("docx", "doc", "pdf")
TEXT_STATUSES = ("ok", "no_files", "unsupported_format", "image_only_pdf",
                 "empty_text", "download_failed", "convert_failed")


class RiigikoguUnavailable(RuntimeError):
    def __init__(self, url: str, status: Optional[int], reason: str):
        super().__init__(f"{reason} for {url}")
        self.url = url
        self.status = status
        self.reason = reason


class DocConvertError(RuntimeError):
    pass


@dataclass
class Extraction:
    text: Optional[str]
    method: Optional[str]
    status: str
    formats: str
    memo: Optional[str] = None


def fetch_with_retry(url: str, max_retries: int = 4, base_delay: float = 10.0,
                     timeout: int = 60, transient_delay: float = 1.0
                     ) -> requests.Response:
    status = None
    reason = "unknown"
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=timeout)
        except requests.Timeout:
            status = None
            reason = "timeout"
            if attempt < max_retries - 1:
                time.sleep(transient_delay * (2 ** attempt))
                continue
            print(f"  fetch failed after {max_retries} attempts: {url} ({reason})")
            raise RiigikoguUnavailable(url, status, reason)
        except requests.ConnectionError:
            status = None
            reason = "connectionerror"
            if attempt < max_retries - 1:
                time.sleep(transient_delay * (2 ** attempt))
                continue
            print(f"  fetch failed after {max_retries} attempts: {url} ({reason})")
            raise RiigikoguUnavailable(url, status, reason)

        if resp.status_code == 429:
            status = resp.status_code
            reason = f"HTTP {resp.status_code}"
            if attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt)
                time.sleep(wait)
                continue
            print(f"  fetch failed after {max_retries} attempts: {url} ({reason})")
            raise RiigikoguUnavailable(url, status, reason)
        if 500 <= resp.status_code < 600:
            status = resp.status_code
            reason = f"HTTP {resp.status_code}"
            if attempt < max_retries - 1:
                time.sleep(transient_delay * (2 ** attempt))
                continue
            print(f"  fetch failed after {max_retries} attempts: {url} ({reason})")
            raise RiigikoguUnavailable(url, status, reason)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            if resp.status_code >= 500 and attempt < max_retries - 1:
                time.sleep(transient_delay * (2 ** attempt))
                continue
            raise
        return resp
    print(f"  fetch failed after {max_retries} attempts: {url} ({reason})")
    raise RiigikoguUnavailable(url, status, reason)


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
    return resp.json().get("texts", [])


def find_best_document(texts: List[Dict[str, Any]]
                       ) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Prefer the bill text (eelnõu/algtekst) as DOCX, DOC, else PDF.
    Returns (doc_type, download_url, formats_seen)."""
    urls: Dict[str, str] = {}
    formats_seen = set()
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
            if ext:
                formats_seen.add(ext)
            if ext in _TEXT_EXTS and ext not in urls:
                urls[ext] = href
    for ext in _TEXT_EXTS:
        if ext in urls:
            return ext, urls[ext], sorted(formats_seen)
    return None, None, sorted(formats_seen)


def _docx_text(data: bytes) -> str:
    if not HAS_DOCX:
        raise ImportError("python-docx not installed")
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(parts)


def extract_docx(url: str) -> str:
    resp = fetch_with_retry(url)
    return _docx_text(resp.content)


def _doc_to_docx(data: bytes) -> bytes:
    soffice = (os.getenv("LAWLAB_SOFFICE") or shutil.which("soffice")
               or shutil.which("libreoffice"))
    if not soffice:
        raise DocConvertError("LibreOffice binary not found")

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "input.doc")
        out = os.path.join(tmp, "input.docx")
        with open(src, "wb") as f:
            f.write(data)
        env = os.environ.copy()
        env["HOME"] = tmp
        cmd = [
            soffice, "--headless", "--norestore", "--nologo",
            f"-env:UserInstallation=file://{os.path.join(tmp, 'profile')}",
            "--convert-to", "docx", "--outdir", tmp, src,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, env=env, timeout=120)
        except subprocess.TimeoutExpired as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise DocConvertError(f"LibreOffice timed out: {stderr[-1000:]}")
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace")
            raise DocConvertError(
                f"LibreOffice failed rc={proc.returncode}: {stderr[-1000:]}")
        if not os.path.exists(out):
            stderr = proc.stderr.decode("utf-8", errors="replace")
            raise DocConvertError(f"LibreOffice produced no docx: {stderr[-1000:]}")
        with open(out, "rb") as f:
            return f.read()


def extract_doc(url: str) -> str:
    resp = fetch_with_retry(url)
    return _docx_text(_doc_to_docx(resp.content))


def extract_pdf(url: str) -> str:
    if not HAS_PDF:
        raise ImportError("PyMuPDF not installed")
    resp = fetch_with_retry(url)
    doc = fitz.open(stream=resp.content, filetype="pdf")
    parts = [p.get_text().strip() for p in doc if p.get_text().strip()]
    doc.close()
    return "\n\n".join(parts)


def split_off_memo(text: str) -> Tuple[str, Optional[str]]:
    section_matches = list(re.finditer(r"(?m)^§\s*\d+\.\s+.*$", text))
    if not section_matches:
        return text, None

    floor = section_matches[-1].end()
    speaker = re.search(r"(?m)^.*\bRiigikogu esimees\b.*$", text[floor:])
    if speaker:
        floor += speaker.end()

    memo = re.search(r"(?im)^[^\n]{0,150}\bseletuskiri\b[^\n]{0,40}$", text[floor:])
    if not memo:
        return text, None

    start = floor + memo.start()
    bill = text[:start].rstrip()
    if len(bill) < MIN_TEXT_CHARS:
        return text, None
    return bill, text[start:].strip()


def _empty_extraction(status: str, formats: str) -> Extraction:
    return Extraction(text=None, method=None, status=status, formats=formats)


def extract_bill_text(uuid: str) -> Extraction:
    """Return one classified extraction result for a draft's bill document."""
    try:
        texts = get_draft_texts(uuid)
    except RiigikoguUnavailable:
        return _empty_extraction("download_failed", "")
    time.sleep(DELAY)

    doc_type, url, formats_seen = find_best_document(texts)
    formats = ",".join(formats_seen)
    if not url:
        if formats_seen:
            return _empty_extraction("unsupported_format", formats)
        return _empty_extraction("no_files", formats)

    try:
        if doc_type == "docx":
            text = extract_docx(url)
            method = "docx"
        elif doc_type == "doc":
            text = extract_doc(url)
            method = "doc_via_libreoffice"
        else:
            text = extract_pdf(url)
            method = "pdf_text"
    except RiigikoguUnavailable:
        return _empty_extraction("download_failed", formats)
    except DocConvertError as exc:
        print(f"  doc conversion failed: {exc}")
        return _empty_extraction("convert_failed", formats)

    if len(text) < MIN_TEXT_CHARS:
        status = "image_only_pdf" if doc_type == "pdf" else "empty_text"
        return Extraction(text=None, method=method, status=status, formats=formats)

    bill, memo = split_off_memo(text)
    return Extraction(text=bill, method=method, status="ok", formats=formats, memo=memo)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
