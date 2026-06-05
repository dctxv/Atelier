/* ====== v2 Research surface — live backend ====== */
const { useState, useEffect } = React;

function StatusMark({ status }) {
  if (status === 'running') return <Pulse size={7}/>;
  if (status === 'done')    return <span style={{ width:7, height:7, borderRadius:'50%', background:'var(--accent)', opacity:.5, display:'inline-block', flexShrink:0 }}/>;
  return <span style={{ width:7, height:7, borderRadius:'50%', border:'1.5px solid var(--text-3)', display:'inline-block', flexShrink:0 }}/>;
}

function ResearchSurface() {
  const [library, setLibrary]   = useState([]);
  const [active, setActive]     = useState(null);
  const [detail, setDetail]     = useState(null);
  const [loading, setLoading]   = useState(false);
  const [querying, setQuerying] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]       = useState('');

  useEffect(() => { loadLibrary(); }, []);

  function loadLibrary() {
    fetch('/api/research')
      .then(r => r.ok ? r.json() : { research:[] })
      .then(d => {
        const items = d.research || [];
        setLibrary(items);
        if (items.length > 0 && !active) selectItem(items[0].id);
      })
      .catch(() => {});
  }

  function selectItem(id) {
    setActive(id);
    setDetail(null);
    setLoading(true);
    fetch(`/api/research/${id}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { setDetail(d ? (d.research || d) : null); setLoading(false); })
      .catch(() => setLoading(false));
  }

  async function handleStart() {
    const q = querying.trim();
    if (!q || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const resp = await fetch('/api/research/start', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ query:q }),
      });
      if (!resp.ok) {
        const d = await resp.json().catch(() => ({}));
        setError(d.detail || 'Could not start research');
      } else {
        const d = await resp.json();
        setQuerying('');
        // Add placeholder to library
        const placeholder = { id:d.session_id, query:q, status:'running', source_count:0, started_at:Date.now()/1000 };
        setLibrary(prev => [placeholder, ...prev]);
        setActive(d.session_id);
        setDetail(null);
        // Poll for completion
        pollResearch(d.session_id);
      }
    } catch(e) { setError('Request failed'); }
    setSubmitting(false);
  }

  function pollResearch(sid) {
    const interval = setInterval(() => {
      fetch(`/api/research/${sid}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          const s = data ? (data.research || data) : null;
          if (!s) { clearInterval(interval); return; }
          if (s.status === 'done' || s.status === 'error') {
            clearInterval(interval);
            setLibrary(prev => prev.map(it => it.id === sid ? { ...it, status:s.status } : it));
            if (s.status === 'done') selectItem(sid);
          } else {
            setLibrary(prev => prev.map(it => it.id === sid ? { ...it, status:'running' } : it));
          }
        })
        .catch(() => clearInterval(interval));
    }, 3000);
  }

  function fmtTime(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined,{month:'short',day:'numeric'});
  }

  /* Parse detail content */
  const doc = detail || {};
  const docTitle = doc.query || '';
  const rawReport = (doc.raw_report || doc.result || '').trim();
  const sources = doc.sources || [];

  // Split report into lede + body
  let docLede = '', docBody = rawReport;
  if (rawReport) {
    const dbl = rawReport.indexOf('\n\n');
    if (dbl > 0) {
      docLede = rawReport.slice(0, dbl).trim();
      docBody  = rawReport.slice(dbl+2).trim();
      if (docLede.length > 300) {
        const sent = docLede.search(/[.!?]\s/);
        if (sent > 0) {
          docBody = docLede.slice(sent+2).trim() + (docBody ? '\n\n'+docBody : '');
          docLede = docLede.slice(0,sent+1).trim();
        }
      }
    } else {
      docLede = rawReport.slice(0,180).trim();
      docBody = rawReport.slice(180).trim();
    }
  }

  const docBodyParts = docBody ? docBody.split('\n\n') : [];

  return (
    <div style={{ display:'flex', height:'100%', overflow:'hidden' }} className="surface-enter">

      {/* ── Library panel ── */}
      <div style={{ width:220, flexShrink:0, background:'var(--panel-bg)',
        borderRight:'1px solid var(--border)', display:'flex', flexDirection:'column' }}>
        {/* header + new research input */}
        <div style={{ padding:'14px 16px 12px', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
          <SectionLabel style={{ marginBottom:10 }}>Research</SectionLabel>
          <div style={{ display:'flex', gap:6 }}>
            <input
              value={querying}
              onChange={e=>setQuerying(e.target.value)}
              onKeyDown={e=>e.key==='Enter'&&handleStart()}
              placeholder="New query…"
              style={{ flex:1, fontFamily:'var(--font-m)', fontSize:11, color:'var(--text)',
                padding:'5px 8px', border:'1px solid var(--border-2)', borderRadius:6,
                background:'var(--thread-bg)' }}
            />
            <button onClick={handleStart} disabled={submitting}
              style={{ width:28, height:28, borderRadius:6, background:'var(--accent-bg)',
                border:'1px solid var(--accent-bd)', display:'grid', placeItems:'center', flexShrink:0 }}>
              <Ico n="send" size={11} color="var(--accent-tx)"/>
            </button>
          </div>
          {error && <p style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)',
            marginTop:6, fontStyle:'italic' }}>{error}</p>}
        </div>

        {/* list */}
        <div className="scroll" style={{ flex:1 }}>
          {library.length === 0 && (
            <div style={{ padding:'24px 16px', textAlign:'center' }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>
                No research yet
              </span>
            </div>
          )}
          {library.map((item, i) => {
            const on = item.id === active;
            return (
              <button key={item.id} onClick={() => selectItem(item.id)} style={{
                width:'100%', textAlign:'left', padding:'11px 14px',
                background: on ? 'var(--accent-bg)' : 'transparent',
                borderLeft:`2px solid ${on ? 'var(--accent)' : 'transparent'}`,
                borderBottom:'1px solid var(--border)',
                cursor:'pointer', transition:'background var(--t)', display:'block',
              }}>
                <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:6, marginBottom:4 }}>
                  <span style={{ fontFamily:'var(--font-b)', fontSize:12.5, fontStyle:'italic',
                    color: on ? 'var(--text)' : 'var(--text-q)', lineHeight:1.3,
                    display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical', overflow:'hidden' }}>
                    {item.query}
                  </span>
                  <StatusMark status={item.status}/>
                </div>
                <div style={{ display:'flex', gap:8 }}>
                  <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}>{fmtTime(item.completed_at||item.started_at)}</span>
                  {item.source_count > 0 && <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}>{item.source_count} src</span>}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Document ── */}
      <div className="scroll" style={{ flex:1, padding:'40px 0', background:'var(--thread-bg)' }}>
        {loading && (
          <div style={{ maxWidth:680, margin:'0 auto', padding:'0 56px' }}>
            {[80,65,90,70,85].map((w,i) => (
              <div key={i} className="shimmer" style={{ height:12, width:`${w}%`, marginBottom:12, borderRadius:3 }}/>
            ))}
          </div>
        )}
        {!loading && !detail && library.length > 0 && (
          <EmptyState icon="search" title="Select a report" subtitle="or run a new query"/>
        )}
        {!loading && !detail && library.length === 0 && (
          <EmptyState icon="search" title="Deep Research" subtitle="enter a query above to start"/>
        )}
        {!loading && detail && (
          <div style={{ maxWidth:680, margin:'0 auto', padding:'0 56px' }}>
            {/* doc header */}
            <div style={{ marginBottom:32 }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
                letterSpacing:'.14em', textTransform:'uppercase', display:'block', marginBottom:10 }}>
                Deep Research · {fmtTime(detail.completed_at||detail.started_at)}
              </span>
              <h1 style={{ fontFamily:'var(--font-d)', fontSize:36, fontWeight:500,
                color:'var(--text)', lineHeight:1.1, letterSpacing:'.01em' }}>{docTitle}</h1>
              {detail.stats && (
                <div style={{ display:'flex', gap:14, marginTop:10 }}>
                  {detail.stats.Duration && <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>{detail.stats.Duration}</span>}
                  {detail.stats.Rounds && <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>·  {detail.stats.Rounds} rounds</span>}
                  {sources.length > 0 && <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>·  {sources.length} sources</span>}
                </div>
              )}
            </div>

            {/* content */}
            {rawReport ? (
              <div style={{ display:'flex', gap:20 }}>
                <div style={{ width:1.5, background:'var(--bar)', borderRadius:1, flexShrink:0 }}/>
                <div>
                  {docLede && (
                    <p style={{ fontFamily:'var(--font-d)', fontSize:20, fontStyle:'italic',
                      lineHeight:1.7, color:'var(--text)', marginBottom:18 }}>{docLede}</p>
                  )}
                  {docBodyParts.map((para, i) => (
                    <p key={i} style={{ fontFamily:'var(--font-b)', fontSize:15.5, lineHeight:1.85,
                      color:'var(--text)', marginBottom:14 }}>{para}</p>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{ display:'flex', alignItems:'center', gap:12, padding:'24px 0' }}>
                <Pulse size={8}/>
                <span style={{ fontFamily:'var(--font-m)', fontSize:13, color:'var(--text-3)' }}>
                  Research in progress…
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Sources ── */}
      {detail && sources.length > 0 && (
        <div style={{ width:220, flexShrink:0, background:'var(--panel-bg)',
          borderLeft:'1px solid var(--border)', display:'flex', flexDirection:'column' }}>
          <div style={{ height:48, display:'flex', alignItems:'center', justifyContent:'space-between',
            padding:'0 16px', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
            <SectionLabel>Sources</SectionLabel>
            <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--accent-tx)' }}>{sources.length}</span>
          </div>
          <div className="scroll" style={{ flex:1, padding:'14px 14px' }}>
            {sources.map((s, i) => (
              <div key={i}>
                <div style={{ display:'flex', gap:10, alignItems:'flex-start', paddingBottom:12 }}>
                  <span style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--accent-tx)',
                    flexShrink:0, marginTop:2 }}>{i+1}</span>
                  <div>
                    {s.url ? (
                      <a href={s.url} target="_blank" rel="noopener noreferrer"
                        style={{ fontFamily:'var(--font-b)', fontSize:12, color:'var(--text-q)',
                          lineHeight:1.45, display:'block', textDecoration:'none',
                          display:'-webkit-box', WebkitLineClamp:3, WebkitBoxOrient:'vertical', overflow:'hidden' }}>
                        {s.title || s.url}
                      </a>
                    ) : (
                      <span style={{ fontFamily:'var(--font-b)', fontSize:12, color:'var(--text-q)',
                        lineHeight:1.45, display:'block' }}>{s.title || 'Source'}</span>
                    )}
                    {s.type && <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
                      letterSpacing:'.06em', textTransform:'uppercase' }}>{s.type}</span>}
                  </div>
                </div>
                {i < sources.length-1 && <Rule style={{ marginBottom:12 }}/>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

window.V2Research = { ResearchSurface };
