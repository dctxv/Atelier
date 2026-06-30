/* ====== Documents surface — upload, ingest status, RAG ====== */
const { useState, useEffect, useRef, useCallback } = React;

/* ── Status pill colours ── */
const STATUS_STYLE = {
  queued:     { bg: 'var(--surface-2, #f0ebe4)', color: 'var(--text-3)' },
  extracting: { bg: 'var(--accent-bg)', color: 'var(--accent-tx)' },
  embedding:  { bg: 'var(--accent-bg)', color: 'var(--accent-tx)' },
  ready:      { bg: '#d4edda', color: '#155724' },
  failed:     { bg: '#f8d7da', color: '#721c24' },
};

function StatusPill({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.queued;
  const label = {
    queued:     'Queued',
    extracting: 'Extracting…',
    embedding:  'Embedding…',
    ready:      'Ready',
    failed:     'Failed',
  }[status] || status;
  const isActive = status === 'extracting' || status === 'embedding';
  return (
    <span style={{
      fontFamily: 'var(--font-m)', fontSize: 10, letterSpacing: '.06em',
      textTransform: 'uppercase', padding: '3px 9px', borderRadius: 20,
      background: s.bg, color: s.color, display: 'inline-flex', alignItems: 'center', gap: 5,
    }}>
      {isActive && <Pulse size={5}/>}
      {label}
    </span>
  );
}

/* ── Format bytes ── */
function fmtBytes(n) {
  if (!n) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/* ── Drop zone ── */
function DropZone({ onFiles }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handle = useCallback((files) => {
    const arr = Array.from(files).filter(f => {
      const ext = f.name.split('.').pop().toLowerCase();
      return ['pdf', 'txt', 'md', 'docx'].includes(ext);
    });
    if (arr.length) onFiles(arr);
  }, [onFiles]);

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); handle(e.dataTransfer.files); }}
      onClick={() => inputRef.current?.click()}
      style={{
        border: `2px dashed ${dragging ? 'var(--accent)' : 'var(--border-2)'}`,
        borderRadius: 12, padding: '32px 24px', textAlign: 'center', cursor: 'pointer',
        background: dragging ? 'var(--accent-bg)' : 'var(--surface)',
        transition: 'all var(--t)', userSelect: 'none',
      }}
    >
      <input ref={inputRef} type="file" multiple accept=".pdf,.txt,.md,.docx"
        style={{ display: 'none' }}
        onChange={e => { handle(e.target.files); e.target.value = ''; }}
      />
      <Ico n="attach" size={22} color="var(--text-3)"/>
      <div style={{ marginTop: 10, fontFamily: 'var(--font-b)', fontSize: 14,
        fontStyle: 'italic', color: 'var(--text-2)' }}>
        Drop files here or click to browse
      </div>
      <div style={{ marginTop: 5, fontFamily: 'var(--font-m)', fontSize: 11,
        color: 'var(--text-3)', letterSpacing: '.04em' }}>
        PDF · TXT · MD · DOCX · max 25 MB
      </div>
    </div>
  );
}

/* ── Single document row ── */
function DocRow({ doc, onDelete }) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 12,
      padding: '14px 0', borderBottom: '1px solid var(--border)',
    }}>
      {/* File icon */}
      <div style={{ width: 36, height: 36, borderRadius: 8, flexShrink: 0,
        background: 'var(--surface)', border: '1px solid var(--border)',
        display: 'grid', placeItems: 'center', marginTop: 2 }}>
        <Ico n="notes" size={16} color="var(--text-3)"/>
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: 'var(--font-b)', fontSize: 14, fontStyle: 'italic',
            color: 'var(--text)', wordBreak: 'break-all' }}>
            {doc.filename}
          </span>
          <StatusPill status={doc.status}/>
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 4, flexWrap: 'wrap' }}>
          {doc.byte_size > 0 && (
            <span style={{ fontFamily: 'var(--font-m)', fontSize: 11, color: 'var(--text-3)' }}>
              {fmtBytes(doc.byte_size)}
            </span>
          )}
          {doc.chunk_count > 0 && (
            <span style={{ fontFamily: 'var(--font-m)', fontSize: 11, color: 'var(--text-3)' }}>
              {doc.chunk_count} chunk{doc.chunk_count !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        {doc.abstract && (
          <div style={{ marginTop: 6, fontFamily: 'var(--font-s, var(--font-b))', fontSize: 12.5,
            color: 'var(--text-2)', lineHeight: 1.55, fontStyle: 'italic' }}>
            {doc.abstract}
          </div>
        )}
        {doc.status === 'failed' && doc.error && (
          <div style={{ marginTop: 5, fontFamily: 'var(--font-m)', fontSize: 11,
            color: '#a94442', background: '#f8d7da', borderRadius: 6,
            padding: '4px 10px', display: 'inline-block' }}>
            {doc.error}
          </div>
        )}
      </div>

      {/* Delete */}
      <div style={{ flexShrink: 0 }}>
        {confirming ? (
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => onDelete(doc.id)} style={{
              fontFamily: 'var(--font-m)', fontSize: 11, padding: '4px 10px',
              borderRadius: 6, background: '#dc3545', color: '#fff', cursor: 'pointer',
            }}>Delete</button>
            <button onClick={() => setConfirming(false)} style={{
              fontFamily: 'var(--font-m)', fontSize: 11, padding: '4px 10px',
              borderRadius: 6, border: '1px solid var(--border-2)', cursor: 'pointer',
              color: 'var(--text-3)',
            }}>Cancel</button>
          </div>
        ) : (
          <button onClick={() => setConfirming(true)} title="Delete document"
            style={{ width: 30, height: 30, borderRadius: 7, display: 'grid',
              placeItems: 'center', border: '1px solid var(--border-2)',
              color: 'var(--text-3)', cursor: 'pointer' }}>
            <Ico n="trash" size={13} color="currentColor"/>
          </button>
        )}
      </div>
    </div>
  );
}

/* ── Usage summary mini-table ── */
function UsageTable({ rows }) {
  if (!rows || rows.length === 0) return (
    <div style={{ fontFamily: 'var(--font-m)', fontSize: 12, color: 'var(--text-3)',
      padding: '16px 0', textAlign: 'center' }}>
      No usage recorded yet
    </div>
  );

  // Aggregate by model
  const byModel = {};
  rows.forEach(r => {
    if (!byModel[r.model]) byModel[r.model] = { input: 0, output: 0, cost: 0 };
    byModel[r.model].input  += r.input_tokens  || 0;
    byModel[r.model].output += r.output_tokens || 0;
    byModel[r.model].cost   += r.est_cost_usd  || 0;
  });

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse',
        fontFamily: 'var(--font-m)', fontSize: 12 }}>
        <thead>
          <tr>
            {['Model', 'Input tokens', 'Output tokens', 'Est. cost'].map(h => (
              <th key={h} style={{ textAlign: 'left', padding: '6px 12px 6px 0',
                borderBottom: '1px solid var(--border)', color: 'var(--text-3)',
                fontWeight: 400, letterSpacing: '.06em', textTransform: 'uppercase',
                fontSize: 10 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.entries(byModel).map(([model, d]) => (
            <tr key={model}>
              <td style={{ padding: '7px 12px 7px 0', color: 'var(--text)',
                wordBreak: 'break-all', maxWidth: 200 }}>{model}</td>
              <td style={{ padding: '7px 12px 7px 0', color: 'var(--text-2)' }}>
                {d.input.toLocaleString()}</td>
              <td style={{ padding: '7px 12px 7px 0', color: 'var(--text-2)' }}>
                {d.output.toLocaleString()}</td>
              <td style={{ padding: '7px 12px 7px 0', color: 'var(--text-2)' }}>
                {d.cost > 0 ? `$${d.cost.toFixed(5)}` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Main surface ── */
function DocumentsSurface() {
  const [docs, setDocs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState(null);
  const [tab, setTab] = useState('documents');
  const [usage, setUsage] = useState(null);
  const [search, setSearch] = useState('');
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/documents');
      const d = await r.json();
      setDocs(d.documents || []);
    } catch { /* silent */ }
  }, []);

  const loadUsage = useCallback(async () => {
    try {
      const r = await fetch('/api/documents/usage/summary');
      const d = await r.json();
      setUsage(d.usage || []);
    } catch { /* silent */ }
  }, []);

  // Poll every 3 s while any document is still processing
  useEffect(() => {
    load();
    pollRef.current = setInterval(() => {
      if (docs.some(d => ['queued', 'extracting', 'embedding'].includes(d.status))) {
        load();
      }
    }, 3000);
    return () => clearInterval(pollRef.current);
  }, [load, docs.length]);

  useEffect(() => {
    if (tab === 'usage' && usage === null) loadUsage();
  }, [tab, usage, loadUsage]);

  const handleFiles = async (files) => {
    setErr(null);
    setUploading(true);
    for (const f of files) {
      const form = new FormData();
      form.append('file', f);
      try {
        const r = await fetch('/api/files/upload', { method: 'POST', body: form });
        if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
      } catch (e) {
        setErr(e.message);
      }
    }
    setUploading(false);
    await load();
  };

  const handleDelete = async (docId) => {
    try {
      await fetch(`/api/documents/${docId}`, { method: 'DELETE' });
      await load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const activeCount = docs.filter(d => ['queued', 'extracting', 'embedding'].includes(d.status)).length;
  const readyCount  = docs.filter(d => d.status === 'ready').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Tab nav */}
      <TabNav
        tabs={[
          { id: 'documents', label: 'Documents', live: activeCount > 0 },
          { id: 'usage',     label: 'Usage & Spend' },
        ]}
        active={tab}
        onSelect={setTab}
      />

      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 56px', maxWidth: 860 }}>

        {tab === 'documents' && (
          <>
            {/* Upload zone */}
            <div style={{ marginBottom: 28 }}>
              <DropZone onFiles={handleFiles}/>
              {uploading && (
                <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 8,
                  fontFamily: 'var(--font-m)', fontSize: 12, color: 'var(--text-3)' }}>
                  <Pulse size={6}/> Uploading…
                </div>
              )}
              {err && (
                <div style={{ marginTop: 8, fontFamily: 'var(--font-m)', fontSize: 12,
                  color: '#a94442' }}>{err}</div>
              )}
            </div>

            {/* Stats strip + search */}
            {docs.length > 0 && (
              <>
                <div style={{ display: 'flex', gap: 24, marginBottom: 14,
                  fontFamily: 'var(--font-m)', fontSize: 11, color: 'var(--text-3)',
                  letterSpacing: '.06em', textTransform: 'uppercase' }}>
                  <span>{docs.length} document{docs.length !== 1 ? 's' : ''}</span>
                  {readyCount > 0 && <span>{readyCount} ready · searchable</span>}
                  {activeCount > 0 && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <Pulse size={5}/> {activeCount} processing
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8,
                  padding: '5px 12px', border: '1px solid var(--border-2)', borderRadius: 8,
                  background: 'var(--surface)', marginBottom: 18 }}>
                  <Ico n="search" size={12} color="var(--text-3)"/>
                  <input value={search} onChange={e => setSearch(e.target.value)}
                    placeholder="Filter by filename…"
                    style={{ fontFamily: 'var(--font-m)', fontSize: 12,
                      color: 'var(--text)', flex: 1 }}/>
                  {search && (
                    <button onClick={() => setSearch('')} style={{ cursor: 'pointer',
                      color: 'var(--text-3)', fontFamily: 'var(--font-m)', fontSize: 11 }}>✕</button>
                  )}
                </div>
              </>
            )}

            {/* Document list */}
            {docs.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '60px 0', opacity: .4 }}>
                <Ico n="notes" size={28} color="var(--text-3)"/>
                <div style={{ marginTop: 12, fontFamily: 'var(--font-b)', fontSize: 15,
                  fontStyle: 'italic', color: 'var(--text-2)' }}>
                  No documents yet
                </div>
                <div style={{ marginTop: 6, fontFamily: 'var(--font-m)', fontSize: 12,
                  color: 'var(--text-3)' }}>
                  Upload a PDF, Word doc, or text file above — it will be indexed and
                  searched alongside your memory in every chat.
                </div>
              </div>
            ) : (() => {
              const q = search.trim().toLowerCase();
              const filtered = q ? docs.filter(d => d.filename.toLowerCase().includes(q)) : docs;
              return filtered.length === 0 ? (
                <div style={{ fontFamily: 'var(--font-m)', fontSize: 12,
                  color: 'var(--text-3)', fontStyle: 'italic', padding: '20px 0' }}>
                  No documents match "{search}"
                </div>
              ) : (
                <div>
                  {filtered.map(doc => (
                    <DocRow key={doc.id} doc={doc} onDelete={handleDelete}/>
                  ))}
                </div>
              );
            })()}
          </>
        )}

        {tab === 'usage' && (
          <>
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontFamily: 'var(--font-b)', fontSize: 16, fontStyle: 'italic',
                color: 'var(--text)', marginBottom: 6 }}>
                Model usage & estimated spend
              </div>
              <div style={{ fontFamily: 'var(--font-m)', fontSize: 12, color: 'var(--text-3)',
                lineHeight: 1.6 }}>
                Tokens recorded from every LLM call (chat, extraction, research, document
                indexing). Cost estimates use prices from the model registry — treat them as
                order-of-magnitude hints, not a billing statement.
              </div>
            </div>
            {usage === null ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8,
                fontFamily: 'var(--font-m)', fontSize: 12, color: 'var(--text-3)' }}>
                <Pulse size={6}/> Loading…
              </div>
            ) : (
              <UsageTable rows={usage}/>
            )}
            <div style={{ marginTop: 16, textAlign: 'right' }}>
              <button onClick={loadUsage} style={{ fontFamily: 'var(--font-m)', fontSize: 11,
                padding: '5px 14px', borderRadius: 7, border: '1px solid var(--border-2)',
                color: 'var(--text-3)', cursor: 'pointer', letterSpacing: '.04em' }}>
                Refresh
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { DocumentsSurface, DropZone, DocRow });
