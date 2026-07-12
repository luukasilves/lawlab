function getConfig() {
  const config = window.LAWLAB_CONFIG || {};
  if (!config.SUPABASE_URL || !config.SUPABASE_ANON_KEY) {
    throw new Error('LAWLAB_CONFIG is missing Supabase settings');
  }
  return config;
}

function buildUrl(path) {
  const { SUPABASE_URL } = getConfig();
  return `${SUPABASE_URL.replace(/\/$/, '')}${path}`;
}

async function parseResponse(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch (error) {
    if (response.ok) {
      throw error;
    }
    return text;
  }
}

export async function api(path, { method = 'GET', body, minimal = false, headers = {} } = {}) {
  const { SUPABASE_ANON_KEY } = getConfig();
  const requestHeaders = {
    apikey: SUPABASE_ANON_KEY,
    Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
    ...headers
  };

  const options = {
    method,
    headers: requestHeaders
  };

  if (body !== undefined) {
    requestHeaders['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }

  const response = await window.fetch(buildUrl(path), options);
  const parsed = minimal && response.ok ? null : await parseResponse(response);

  if (!response.ok) {
    const error = new Error(`Request failed with status ${response.status}`);
    error.status = response.status;
    error.body = parsed;
    throw error;
  }

  return parsed;
}

export function fetchBillIndex() {
  return api('/rest/v1/bill_index?select=*&order=doc_fetched_at.desc.nullslast');
}

export function fetchLatestIngest() {
  return api('/rest/v1/pipeline_runs?kind=eq.ingest&ok=eq.true&select=finished_at,stats&order=finished_at.desc&limit=1');
}

// PostgREST always returns arrays; singular fetchers unwrap the first row.
async function first(promise) {
  const rows = await promise;
  return Array.isArray(rows) ? (rows[0] ?? null) : rows;
}

export function fetchBill(billId) {
  return first(api(
    `/rest/v1/bills?id=eq.${encodeURIComponent(billId)}` +
    `&select=*,bill_documents(id,document_type,version,fetched_at,text_length,extraction_method)`
  ));
}

export function fetchHistory(billId) {
  return api(`/rest/v1/analysis_history?bill_id=eq.${encodeURIComponent(billId)}&select=*&order=created_at.desc`);
}

export function fetchAnalysisWithFindings(analysisId) {
  return first(api(`/rest/v1/analyses?id=eq.${encodeURIComponent(analysisId)}&select=*,findings(*)`));
}

export function fetchParsedText(documentId) {
  return first(api(`/rest/v1/bill_documents?id=eq.${encodeURIComponent(documentId)}&select=parsed_text`));
}

export function fetchSamplesMeta(analysisId) {
  return api(`/rest/v1/analysis_samples?analysis_id=eq.${encodeURIComponent(analysisId)}&select=id,analysis_id,pass_id,sample_idx,temperature,returned_count,grounded_count,dropped_ungrounded,reused,duration_ms,input_tokens,output_tokens,cost_usd,created_at`);
}

export function fetchSampleRaw(sampleId) {
  return first(api(`/rest/v1/analysis_samples?id=eq.${encodeURIComponent(sampleId)}&select=raw_output,parsed`));
}

export function postFeedback(findingId, verdict) {
  return api('/rest/v1/feedback', {
    method: 'POST',
    body: { finding_id: findingId, verdict },
    minimal: true,
    headers: { Prefer: 'return=minimal' }
  });
}
