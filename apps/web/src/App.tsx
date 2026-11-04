import { useCallback, useEffect, useState } from 'react';

/** EvidenceForge UI: evf_library / evf_source / evf_review / evf_export.
 * Tokens are kept in memory only (never localStorage). API base is relative. */
type Doc = { id: string; project_id: string; title: string; state: string; source_sha256: string; page_count: number | null };
type Field = { key: string; raw: string | null; value: string | null; currency: string | null; scale: string | null;
  period_end: string | null; missing_reason: string | null; review_state: string;
  evidence: { quote: string; element_id: string; region: { page_ordinal: number }; support: string }[] };
type Extraction = { id: string; revision: number; fields: Field[] };

const sha256 = async (b: ArrayBuffer) => {
  const d = await crypto.subtle.digest('SHA-256', b);
  return [...new Uint8Array(d)].map((x) => x.toString(16).padStart(2, '0')).join('');
};
const idem = () => crypto.randomUUID();

export default function App() {
  const [token, setToken] = useState('');
  const [projectId, setProjectId] = useState('');
  const [docs, setDocs] = useState<Doc[]>([]);
  const [ext, setExt] = useState<Extraction | null>(null);
  const [selected, setSelected] = useState<Field | null>(null);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const headers = useCallback((extra: Record<string, string> = {}) => ({
    Authorization: `Bearer ${token}`, 'X-Project-Id': projectId, ...extra }), [token, projectId]);
  const api = useCallback(async (path: string, init: RequestInit = {}) => {
    const r = await fetch(`/api/v1${path}`, { ...init, headers: { ...(init.headers as object), ...headers() } });
    if (!r.ok) throw new Error(`Request failed (${r.status}) — check role/project and retry.`);
    return r.status === 202 || r.headers.get('content-type')?.includes('json') ? r.json().catch(() => ({})) : r;
  }, [headers]);

  const loadDocs = useCallback(async () => {
    if (!projectId || !token) return;
    setDocs(await api(`/projects/${projectId}/evf/documents`));
  }, [api, projectId, token]);
  useEffect(() => { loadDocs().catch((e) => setMsg(String(e.message))); }, [loadDocs]);

  async function uploadBundled(file: File) {
    setBusy(true);
    try {
      const buf = await file.arrayBuffer(); const sha = await sha256(buf);
      const up = await api(`/projects/${projectId}/uploads`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem() },
        body: JSON.stringify({ filename: file.name, media_type: 'application/pdf', byte_size: buf.byteLength, sha256: sha, classification: 'synthetic' }) });
      await fetch(up.put_path, { method: 'PUT', headers: headers(), body: buf });
      const art = await api(`/uploads/${up.id}:finalize`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem() },
        body: JSON.stringify({ sha256: sha, byte_size: buf.byteLength }) });
      const doc = await api(`/projects/${projectId}/evf/documents`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem() },
        body: JSON.stringify({ artifact_id: art.id, title: file.name }) });
      const parse = await api(`/evf/documents/${doc.id}/parses`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem() },
        body: JSON.stringify({ profile: 'fixture/1', source_sha256: sha }) });
      setMsg('Parse queued — the worker processes it; only the bundled synthetic PDF digest is accepted by fixture/1.');
      const x = await api(`/projects/${projectId}/evf/extractions`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem() },
        body: JSON.stringify({ schema_version: 'annual-report-8/1', method: 'fixture', parse_id: parse.id }) })
        .catch(() => null);
      if (x) setExt(x);
      await loadDocs();
    } catch (e) { setMsg(String((e as Error).message)); } finally { setBusy(false); }
  }

  async function correct(field: Field) {
    if (!ext) return;
    const value = window.prompt(`Corrected value for ${field.key} (base units; leave blank to only set period)`, field.value ?? '');
    if (value === null) return;
    try {
      await api(`/evf/extractions/${ext.id}/reviews`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem(), 'If-Match': `"${ext.revision}"` },
        body: JSON.stringify({ base_revision: ext.revision, patches: [{ key: field.key, action: 'correct',
          value: value || null, reason: 'analyst correction via review UI', evidence: field.evidence }] }) });
      setExt(await api(`/evf/extractions/${ext.id}`));
      setMsg('Review appended as a new revision (append-only).');
    } catch (e) { setMsg(`${String((e as Error).message)} If stale, reload the extraction — edits are never overwritten.`); }
  }

  async function exportAs(format: 'json' | 'csv') {
    if (!ext) return;
    try {
      const x = await api(`/evf/extractions/${ext.id}/exports`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem() },
        body: JSON.stringify({ review_revision: ext.revision, format, allow_incomplete: true }) });
      setMsg(`Export ${format.toUpperCase()} created (artifact ${x.artifact_id}); incomplete=${x.incomplete}; warnings: ${x.warnings.join(', ') || 'none'}`);
    } catch (e) { setMsg(String((e as Error).message)); }
  }

  return (<main style={{ fontFamily: 'system-ui', maxWidth: 1100, margin: '2rem auto', padding: '0 1rem', color: '#17324D' }}>
    <h1>EvidenceForge</h1>
    <p role="note" style={{ background: '#FFF4E5', padding: '0.75rem', border: '1px solid #8A5800' }}>
      <strong>SYNTHETIC FIXTURE MODE (fixture/1)</strong> — geometry/quotes are authored test metadata, not Docling output.
      Provenance/support is not proof of financial correctness. Real parser (B09) is disabled.
    </p>
    <section aria-label="Session">
      <label>Access token (memory only) <input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" /></label>{' '}
      <label>Project ID <input value={projectId} onChange={(e) => setProjectId(e.target.value)} /></label>
    </section>
    <section aria-label="PDF library (/evf/documents)">
      <h2>PDF library</h2>
      <label>Upload bundled synthetic PDF <input type="file" accept="application/pdf" disabled={busy || !token || !projectId}
        onChange={(e) => e.target.files?.[0] && uploadBundled(e.target.files[0])} /></label>
      <ul>{docs.map((d) => (<li key={d.id}>{d.title} — state: {d.state} — sha256: <code>{d.source_sha256.slice(0, 12)}…</code></li>))}</ul>
      {docs.length === 0 && <p>No documents yet for this project.</p>}
    </section>
    {ext && (<section aria-label="Extraction review (/evf/extractions/:id)">
      <h2>Eight-field extraction review (revision {ext.revision})</h2>
      <table><thead><tr><th>Field</th><th>Value (base units)</th><th>Raw</th><th>State</th><th>Evidence</th><th>Action</th></tr></thead>
      <tbody>{ext.fields.map((f) => (<tr key={f.key} style={selected?.key === f.key ? { outline: '3px solid #087A83' } : {}}>
        <th scope="row">{f.key}</th><td>{f.value ?? `— missing: ${f.missing_reason}`}</td><td>{f.raw ?? ''}</td>
        <td>{f.review_state}</td>
        <td>{f.evidence.map((e, i) => (<button key={i} onClick={() => setSelected(f)}
          aria-label={`Show evidence for ${f.key}`}>p.{e.region.page_ordinal} “{e.quote}” ({e.support})</button>))}</td>
        <td><button onClick={() => correct(f)}>Correct…</button></td></tr>))}</tbody></table>
      {selected && (<div aria-live="polite"><h3>Selected evidence — {selected.key}</h3>
        <p>{selected.evidence.map((e) => `Element ${e.element_id}, page ${e.region.page_ordinal}: “${e.quote}” — ${e.support}`).join('; ') ||
          'No evidence linked; treat value as unsupported.'}</p>
        <p>Accessible text fallback: quotes above are the text alternative to any visual highlight.</p></div>)}
      <h3>Export</h3>
      <button onClick={() => exportAs('json')}>Export JSON</button>{' '}
      <button onClick={() => exportAs('csv')}>Export CSV</button>
      <p>Incomplete exports carry explicit field-missing warnings; spreadsheet-formula cells are neutralized server-side.</p>
    </section>)}
    {msg && <p role="status" aria-live="polite">{msg}</p>}
  </main>);
}
