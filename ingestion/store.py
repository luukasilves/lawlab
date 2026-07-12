"""Supabase REST store. Reads use the anon key; writes REQUIRE the service-role
key (anon is read-only under RLS). No `supabase` package needed — plain REST."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from urllib.parse import quote

import requests
import config


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flt(value: Any) -> str:
    return quote(str(value), safe="")


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
        payload = {"title": title, "status": api_data.get("proceedingStatus"),
                   "api_data": api_data, "last_seen_at": _now_iso()}
        if existing:
            r = requests.patch(f"{self.url}/rest/v1/bills?id=eq.{_flt(existing['id'])}",
                               headers=self._h(write=True,
                                               extra={"Prefer": "return=minimal"}),
                               json=payload, timeout=30)
            r.raise_for_status()
            return existing["id"]
        payload["bill_number"] = str(mark)
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
        return r.status_code in (200, 201, 204)

    def next_version(self, bill_id: str) -> int:
        r = requests.get(f"{self.url}/rest/v1/bill_documents?bill_id=eq.{_flt(bill_id)}"
                         f"&select=version&order=version.desc,fetched_at.desc&limit=1",
                         headers=self._h(), timeout=30)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return 1
        return int(rows[0].get("version") or 0) + 1

    def has_analysis(self, cache_key: str) -> bool:
        r = requests.get(f"{self.url}/rest/v1/analyses?cache_key=eq.{cache_key}&select=id&limit=1",
                         headers=self._h(), timeout=30)
        r.raise_for_status()
        return bool(r.json())

    def get_parsed_text(self, doc_id: str) -> Optional[str]:
        r = requests.get(f"{self.url}/rest/v1/bill_documents?id=eq.{_flt(doc_id)}"
                         f"&select=parsed_text&limit=1", headers=self._h(), timeout=60)
        r.raise_for_status()
        rows = r.json()
        return rows[0].get("parsed_text") if rows else None

    def find_reusable_samples(self, llm_cache_key: str) -> Optional[List[Dict[str, Any]]]:
        r = requests.get(f"{self.url}/rest/v1/analyses?llm_cache_key=eq.{_flt(llm_cache_key)}"
                         f"&select=id&order=created_at.desc&limit=1",
                         headers=self._h(), timeout=30)
        r.raise_for_status()
        analyses = r.json()
        if not analyses:
            return None

        analysis_id = analyses[0]["id"]
        r = requests.get(f"{self.url}/rest/v1/analysis_samples?analysis_id=eq.{_flt(analysis_id)}"
                         f"&pass_id=eq.interpretive&select=*&order=sample_idx.asc",
                         headers=self._h(), timeout=60)
        r.raise_for_status()
        samples = r.json()
        return samples or None

    def insert_analysis(self, bill_document_id: str, result: Dict[str, Any]) -> str:
        usage = result.get("usage", {})
        payload = {"bill_document_id": bill_document_id}
        for key in ("cache_key", "llm_cache_key", "model", "provider", "prompt_version",
                    "checker_version", "engine", "config", "stats"):
            payload[key] = result.get(key)
        for key in ("duration_ms", "input_tokens", "output_tokens", "cost_usd"):
            payload[key] = result.get(key, usage.get(key))
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
            "title", "description", "reasoning", "suggestion", "honte_rule", "check_id",
            "skeptic_verdict", "skeptic_reasoning")}}
            for f in findings]
        r = requests.post(f"{self.url}/rest/v1/findings",
                          headers=self._h(write=True, extra={"Prefer": "return=minimal"}),
                          json=rows, timeout=60)
        return r.status_code in (200, 201, 204)

    def insert_samples(self, analysis_id: str, samples: List[Dict[str, Any]]) -> bool:
        if not samples:
            return True
        rows = [{**sample, "analysis_id": analysis_id} for sample in samples]
        r = requests.post(f"{self.url}/rest/v1/analysis_samples",
                          headers=self._h(write=True, extra={"Prefer": "return=minimal"}),
                          json=rows, timeout=60)
        return r.status_code in (200, 201, 204)

    def record_run(self, kind: str, started_at_iso: str, ok: bool,
                   stats: Dict[str, Any]) -> None:
        payload = {"kind": kind, "started_at": started_at_iso,
                   "finished_at": _now_iso(), "ok": ok, "stats": stats}
        r = requests.post(f"{self.url}/rest/v1/pipeline_runs",
                          headers=self._h(write=True, extra={"Prefer": "return=minimal"}),
                          json=payload, timeout=30)
        r.raise_for_status()

    def docs_needing_analysis(self) -> List[Dict[str, Any]]:
        """bill_documents (eelnõu) candidates without fetching parsed_text."""
        out: List[Dict[str, Any]] = []
        start = 0
        page_size = 1000
        while True:
            end = start + page_size - 1
            r = requests.get(f"{self.url}/rest/v1/bill_documents?document_type=eq.eeln%C3%B5u"
                             f"&select=id,bill_id,content_hash",
                             headers=self._h(extra={"Range": f"{start}-{end}"}),
                             timeout=60)
            r.raise_for_status()
            rows = r.json()
            out.extend(rows)
            if len(rows) < page_size:
                return out
            start += page_size
