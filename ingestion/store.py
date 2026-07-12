"""Supabase REST store. Reads use the anon key; writes REQUIRE the service-role
key (anon is read-only under RLS). No `supabase` package needed — plain REST."""

from __future__ import annotations
from typing import Optional, Dict, Any, List
import requests
import config


class SupabaseStore:
    def __init__(self):
        self.url = config.SUPABASE_URL
        self.anon = config.SUPABASE_ANON_KEY
        self.service = config.SUPABASE_SERVICE_KEY
        if not self.url or not self.anon:
            raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY not configured")

    def _h(self, write: bool = False, extra: Dict[str, str] = None) -> Dict[str, str]:
        key = self.service if write else self.anon
        if write and not self.service:
            raise RuntimeError("SUPABASE_SERVICE_KEY required for writes (anon is read-only)")
        h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if extra:
            h.update(extra)
        return h

    # ── reads ────────────────────────────────────────────────────────────
    def get_bill_by_number(self, mark: str) -> Optional[Dict[str, Any]]:
        r = requests.get(f"{self.url}/rest/v1/bills?bill_number=eq.{mark}&select=id,bill_number,title",
                         headers=self._h(), timeout=30)
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def latest_doc_hash(self, bill_id: str) -> Optional[str]:
        r = requests.get(f"{self.url}/rest/v1/bill_documents?bill_id=eq.{bill_id}"
                         f"&document_type=eq.eeln%C3%B5u&select=content_hash,version"
                         f"&order=version.desc&limit=1", headers=self._h(), timeout=30)
        r.raise_for_status()
        rows = r.json()
        return rows[0].get("content_hash") if rows else None

    # ── writes (service key) ──────────────────────────────────────────────
    def upsert_bill(self, mark: str, title: str, api_data: Dict[str, Any]) -> str:
        existing = self.get_bill_by_number(mark)
        if existing:
            return existing["id"]
        payload = {"bill_number": str(mark), "title": title, "api_data": api_data,
                   "status": api_data.get("activeDraftStatus")}
        r = requests.post(f"{self.url}/rest/v1/bills", headers=self._h(write=True,
                          extra={"Prefer": "return=representation"}), json=payload, timeout=30)
        r.raise_for_status()
        return r.json()[0]["id"]

    def insert_document(self, bill_id: str, text: str, method: str,
                        content_hash: str, version: int) -> bool:
        payload = {"bill_id": bill_id, "document_type": "eelnõu", "parsed_text": text,
                   "text_length": len(text), "extraction_method": method,
                   "content_hash": content_hash, "version": version}
        r = requests.post(f"{self.url}/rest/v1/bill_documents",
                          headers=self._h(write=True, extra={"Prefer": "return=minimal"}),
                          json=payload, timeout=30)
        return r.status_code in (200, 201)

    def has_analysis(self, cache_key: str) -> bool:
        r = requests.get(f"{self.url}/rest/v1/analyses?cache_key=eq.{cache_key}&select=id&limit=1",
                         headers=self._h(), timeout=30)
        r.raise_for_status()
        return bool(r.json())

    def insert_analysis(self, bill_document_id: str, result: Dict[str, Any]) -> str:
        payload = {"bill_document_id": bill_document_id, "cache_key": result["cache_key"],
                   "model": result["model"], "prompt_version": result["prompt_version"],
                   "checker_version": result["checker_version"], "config": result["config"]}
        r = requests.post(f"{self.url}/rest/v1/analyses", headers=self._h(write=True,
                          extra={"Prefer": "return=representation"}), json=payload, timeout=30)
        r.raise_for_status()
        return r.json()[0]["id"]

    def insert_findings(self, analysis_id: str, findings: List[Dict[str, Any]]) -> bool:
        if not findings:
            return True
        rows = [{"analysis_id": analysis_id, **{k: f.get(k) for k in (
            "source", "category", "severity", "confidence", "runs_found", "runs_total",
            "provision_id", "location", "evidence_quote", "char_start", "char_end",
            "title", "description", "reasoning", "suggestion", "honte_rule", "check_id")}}
            for f in findings]
        r = requests.post(f"{self.url}/rest/v1/findings",
                          headers=self._h(write=True, extra={"Prefer": "return=minimal"}),
                          json=rows, timeout=60)
        return r.status_code in (200, 201)

    def docs_needing_analysis(self, prompt_version: str) -> List[Dict[str, Any]]:
        """bill_documents (eelnõu) with no analysis at the current prompt_version."""
        r = requests.get(f"{self.url}/rest/v1/bill_documents?document_type=eq.eeln%C3%B5u"
                         f"&select=id,bill_id,parsed_text,content_hash", headers=self._h(), timeout=60)
        r.raise_for_status()
        return r.json()
