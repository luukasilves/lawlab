export async function fetchBill(billId) {
  window.__LAWLAB_LAST_BILL_ID__ = billId;
  return window.__LAWLAB_FIXTURE__?.bill;
}

export async function fetchHistory(billId) {
  window.__LAWLAB_LAST_HISTORY_BILL_ID__ = billId;
  return window.__LAWLAB_FIXTURE__?.history || [];
}

export async function fetchAnalysisWithFindings(analysisId) {
  window.__LAWLAB_LAST_ANALYSIS_ID__ = analysisId;
  const analyses = window.__LAWLAB_FIXTURE__?.analysesById || {};
  return analyses[analysisId] || window.__LAWLAB_FIXTURE__?.analysis;
}

export async function fetchParsedText(documentId) {
  window.__LAWLAB_LAST_DOCUMENT_ID__ = documentId;
  return window.__LAWLAB_FIXTURE__?.parsedText || { parsed_text: "" };
}

export async function fetchSamplesMeta(analysisId) {
  window.__LAWLAB_LAST_SAMPLES_ANALYSIS_ID__ = analysisId;
  const samplesByAnalysis = window.__LAWLAB_FIXTURE__?.samplesByAnalysis || {};
  return samplesByAnalysis[analysisId] || window.__LAWLAB_FIXTURE__?.samplesMeta || [];
}

export async function fetchSampleRaw(sampleId) {
  window.__LAWLAB_LAST_SAMPLE_ID__ = sampleId;
  return {
    raw_output: `raw output for ${sampleId}`,
    parsed: { sample_id: sampleId, ok: true }
  };
}

export async function postFeedback(findingId, verdict) {
  window.__postFeedbackCalls = window.__postFeedbackCalls || [];
  window.__postFeedbackCalls.push({ findingId, verdict });
  return { status: 201 };
}
