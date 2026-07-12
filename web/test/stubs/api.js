export async function fetchBillIndex() {
  return window.__LAWLAB_INDEX_FIXTURE__ || [];
}

export async function fetchLatestIngest() {
  return window.__LAWLAB_INGEST_FIXTURE__ || [];
}
