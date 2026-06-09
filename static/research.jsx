/* ====== v2 Research surface — Tavily-style launcher + live streaming ======
 *
 * Rendering is driven by DB truth: sections, claims and sources are persisted
 * incrementally by workers/research.py, so navigating away and back (or a hard
 * reload) re-fetches the current state instead of relying on ephemeral stream
 * state. The SSE stream drives the live phase label and triggers a re-fetch as
 * each section finalizes.
 *
 * Layout: a full-page centered launcher (query + depth + examples) owns the
 * surface; past reports live in a collapsible "Recents" drawer. Selecting or
 * starting one swaps in the report view (prose/claims + sources rail).
 */
const { useState, useEffect, useRef } = React;

/* Stance → visual treatment for claim cards. */
const STANCE = {
  supported:     { tx:'#4F7A3F', bg:'rgba(79,122,63,.12)',  line:'rgba(79,122,63,.45)',  label:'Supported' },
  disputed:      { tx:'#B5562E', bg:'rgba(181,86,46,.14)',  line:'rgba(181,86,46,.5)',   label:'Disputed' },
  single_source: { tx:'var(--accent-tx)', bg:'var(--accent-bg)', line:'rgba(138,90,52,.4)', label:'Single source' },
  unverified:    { tx:'var(--text-3)', bg:'transparent',     line:'transparent',          label:'Unverified' },
};

function StatusMark({ status }) {
  if (status === 'running') return <Pulse size={7}/>;
  if (status === 'done')    return <span style={{ width:7, height:7, borderRadius:'50%', background:'var(--accent)', opacity:.5, display:'inline-block', flexShrink:0 }}/>;
  return <span style={{ width:7, height:7, borderRadius:'50%', border:'1.5px solid var(--text-3)', display:'inline-block', flexShrink:0 }}/>;
}

/* ── Claim primitives ── */
function StanceChip({ stance }) {
  const s = STANCE[stance] || STANCE.unverified;
  return (
    <span style={{ fontFamily:'var(--font-m)', fontSize:8.5, letterSpacing:'.08em',
      textTransform:'uppercase', color:s.tx, background:s.bg, borderRadius:4,
      padding:'2px 6px', border: s.bg==='transparent' ? '1px solid var(--border-2)' : 'none',
      flexShrink:0 }}>
      {s.label}
    </span>
  );
}

function ConfidenceBar({ value, stance }) {
  const s = STANCE[stance] || STANCE.unverified;
  const pct = Math.round((value || 0) * 100);
  return (
    <div style={{ display:'flex', alignItems:'center', gap:7 }}>
      <div style={{ width:80, height:3, background:'var(--bar)', borderRadius:2, overflow:'hidden' }}>
        <div style={{ width:`${pct}%`, height:'100%',
          background: s.tx === 'var(--text-3)' ? 'var(--text-3)' : s.tx, borderRadius:2 }}/>
      </div>
      <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)' }}>{pct}%</span>
    </div>
  );
}

/* Inline citation markers — link to the numbered source. */
function Cite({ citations }) {
  const seen = new Set();
  const cites = (citations || []).filter(c => {
    const k = c.source_idx ?? c.url;
    if (seen.has(k)) return false; seen.add(k); return true;
  });
  if (!cites.length) return null;
  return (
    <sup style={{ marginLeft:3, whiteSpace:'nowrap' }}>
      {cites.map((c, i) => {
        const refute  = c.polarity === 'refutes';
        const neutral = c.polarity === 'neutral';
        return (
          <a key={i} href={c.url} target="_blank" rel="noopener noreferrer"
            title={refute ? 'Refuting source'
              : neutral ? 'Cited, but the check found it does not directly support this claim'
              : 'Supporting source'}
            style={{ fontFamily:'var(--font-m)', fontSize:9, padding:'0 1px', textDecoration:'none',
              color: refute ? '#B5562E' : neutral ? 'var(--text-3)' : 'var(--accent-tx)',
              borderBottom: neutral ? '1px dotted var(--text-3)' : 'none' }}>
            [{c.source_idx || '•'}]
          </a>
        );
      })}
    </sup>
  );
}

/* Read view: claim rendered inline as prose with a stance underline; verification
 * (stance + confidence + sources) reveals on hover. */
function ClaimSpan({ claim }) {
  const [hover, setHover] = useState(false);
  const s = STANCE[claim.stance] || STANCE.unverified;
  const { used, aside } = splitCites(claim);
  return (
    <span style={{ position:'relative',
        borderBottom:`1.5px solid ${hover ? s.tx : s.line}`,
        background: hover ? s.bg : 'transparent', borderRadius:1,
        transition:'background var(--t), border-color var(--t)' }}
      onMouseEnter={()=>setHover(true)} onMouseLeave={()=>setHover(false)}>
      {claim.text}<Cite citations={used}/>
      {hover && (
        <span style={{ position:'absolute', bottom:'100%', left:0, marginBottom:7, zIndex:30,
          background:'var(--panel-bg)', border:'1px solid var(--border-2)', borderRadius:8,
          padding:'8px 11px', boxShadow:'0 8px 28px rgba(0,0,0,.16)', whiteSpace:'nowrap',
          display:'flex', gap:12, alignItems:'center' }}>
          <StanceChip stance={claim.stance}/>
          <ConfidenceBar value={claim.confidence} stance={claim.stance}/>
          {aside.length > 0 && <AsideCite citations={aside}/>}
        </span>
      )}
    </span>
  );
}

/* Sources the writer cited but the verifier judged too weakly related to count
 * as evidence — shown, never hidden. */
function AsideCite({ citations }) {
  const seen = new Set();
  const cs = (citations || []).filter(c => {
    const k = c.source_idx ?? c.url;
    if (seen.has(k)) return false; seen.add(k); return true;
  });
  if (!cs.length) return null;
  return (
    <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}
      title="The writer cited these, but the check found them too weakly related to count as evidence.">
      <span style={{ opacity:.8 }}>set aside</span>
      {cs.map((c, i) => (
        <a key={i} href={c.url} target="_blank" rel="noopener noreferrer"
          style={{ color:'var(--text-3)', textDecoration:'none', marginLeft:3 }}>
          [{c.source_idx || '•'}]
        </a>
      ))}
    </span>
  );
}

function splitCites(claim) {
  const cites = claim.citations || [];
  return {
    used:  cites.filter(c => c.polarity !== 'set_aside'),
    aside: cites.filter(c => c.polarity === 'set_aside'),
  };
}

function ClaimCard({ claim }) {
  const s = STANCE[claim.stance] || STANCE.unverified;
  const { used, aside } = splitCites(claim);
  return (
    <div style={{ display:'flex', gap:28, alignItems:'flex-start', padding:'13px 0',
      borderBottom:'1px solid var(--rule)' }}>
      {/* claim text flows on the left */}
      <div style={{ flex:1, minWidth:0,
        borderLeft:`2px solid ${s.bg === 'transparent' ? 'var(--border-2)' : s.tx}`,
        paddingLeft:14, opacity: claim.stance === 'unverified' ? .72 : 1 }}>
        <p style={{ fontFamily:'var(--font-b)', fontSize:15.5, lineHeight:1.72,
          color:'var(--text)', margin:0 }}>
          {claim.text}<Cite citations={used}/>
        </p>
        {aside.length > 0 && (
          <div style={{ marginTop:6 }}><AsideCite citations={aside}/></div>
        )}
        {used.length === 0 && aside.length === 0 && (
          <div style={{ marginTop:6, fontFamily:'var(--font-m)', fontSize:9.5,
            color:'var(--text-3)', fontStyle:'italic' }}>
            no source cited
          </div>
        )}
      </div>
      {/* verification rail uses the empty right gutter */}
      <div style={{ width:128, flexShrink:0, display:'flex', flexDirection:'column',
        gap:7, alignItems:'flex-start', paddingTop:2 }}>
        <StanceChip stance={claim.stance}/>
        <ConfidenceBar value={claim.confidence} stance={claim.stance}/>
      </div>
    </div>
  );
}

/* ── Central launcher (Tavily-style) ── */
function ResearchLauncher({ query, setQuery, depth, setDepth, onStart, submitting, error }) {
  const DEPTHS = [['light','Light'], ['medium','Medium'], ['intense','Intense']];
  const HINT = {
    light:   'One quick pass, fewer sources — fastest.',
    medium:  'Balanced depth and breadth.',
    intense: 'More rounds and sources, deeper verification — slowest.',
  };
  const EXAMPLES = [
    'State of solid-state batteries in 2026',
    'Compare the top open-source LLMs',
    'How FSRS spaced-repetition scheduling works',
  ];
  function onKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onStart(); } }
  const canStart = !submitting && query.trim();
  return (
    <div className="scroll" style={{ flex:1, display:'flex', flexDirection:'column',
      alignItems:'center', justifyContent:'center', padding:'48px 32px' }}>
      <div style={{ width:'100%', maxWidth:680 }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'center', gap:10, marginBottom:22 }}>
          <Ico n="search" size={18} color="var(--accent-tx)"/>
          <span style={{ fontFamily:'var(--font-d)', fontSize:30, fontWeight:500, color:'var(--text)' }}>
            Deep Research
          </span>
        </div>

        <div style={{ background:'var(--surface)', border:'1px solid var(--border-2)', borderRadius:14,
          padding:'18px 20px 16px', boxShadow:'0 8px 32px rgba(0,0,0,.10)' }}>
          <textarea autoFocus value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={onKey}
            placeholder="What do you want to research?" rows={3}
            style={{ width:'100%', resize:'none', fontFamily:'var(--font-b)', fontSize:16,
              lineHeight:1.6, color:'var(--text)', background:'transparent' }}/>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
            marginTop:12, paddingTop:12, borderTop:'1px solid var(--border)' }}>
            <div style={{ display:'flex', alignItems:'center', gap:10 }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, letterSpacing:'.1em',
                textTransform:'uppercase', color:'var(--text-3)' }}>Depth</span>
              <Segmented value={depth} onChange={setDepth} options={DEPTHS}/>
            </div>
            <button onClick={onStart} disabled={!canStart} style={{
              display:'flex', alignItems:'center', gap:7, padding:'9px 20px', borderRadius:10,
              border:'1px solid var(--accent-bd)', background:'var(--send-bg)', color:'var(--send-fg)',
              fontFamily:'var(--font-b)', fontSize:13.5, fontStyle:'italic',
              cursor: canStart ? 'pointer' : 'default', opacity: canStart ? 1 : .6 }}>
              {submitting ? 'Starting…' : 'Start'}
              <Ico n="send" size={12} color="var(--send-fg)"/>
            </button>
          </div>
        </div>

        <div style={{ marginTop:10, fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)',
          fontStyle:'italic', textAlign:'center' }}>
          {HINT[depth]}
        </div>

        {error && (
          <div style={{ marginTop:12, textAlign:'center', fontFamily:'var(--font-m)', fontSize:12, color:'#a94442' }}>
            {error}
          </div>
        )}

        <div style={{ marginTop:28, display:'flex', flexDirection:'column', alignItems:'center', gap:10 }}>
          <span style={{ fontFamily:'var(--font-m)', fontSize:9, letterSpacing:'.12em',
            textTransform:'uppercase', color:'var(--text-3)' }}>Try an example</span>
          <div style={{ display:'flex', flexWrap:'wrap', gap:8, justifyContent:'center' }}>
            {EXAMPLES.map(ex => (
              <button key={ex} onClick={()=>setQuery(ex)} style={{
                fontFamily:'var(--font-b)', fontSize:12.5, fontStyle:'italic', color:'var(--text-q)',
                padding:'6px 14px', borderRadius:20, border:'1px solid var(--border-2)',
                background:'transparent', cursor:'pointer' }}>
                {ex}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Recents drawer (collapsible library) ── */
function RecentsDrawer({ library, active, onSelect, onDelete, onClose, fmtTime }) {
  return (
    <>
      <div onClick={onClose} style={{ position:'absolute', inset:0, background:'rgba(0,0,0,.28)', zIndex:40 }}/>
      <div style={{ position:'absolute', top:0, left:0, bottom:0, width:300, background:'var(--panel-bg)',
        borderRight:'1px solid var(--border)', zIndex:41, display:'flex', flexDirection:'column',
        boxShadow:'8px 0 32px rgba(0,0,0,.18)' }}>
        <div style={{ height:48, flexShrink:0, display:'flex', alignItems:'center',
          justifyContent:'space-between', padding:'0 12px 0 16px', borderBottom:'1px solid var(--border)' }}>
          <SectionLabel>Recents</SectionLabel>
          <button onClick={onClose} title="Close" style={{ width:24, height:24, borderRadius:6,
            display:'grid', placeItems:'center', color:'var(--text-3)', cursor:'pointer' }}>
            <Ico n="close" size={12} color="currentColor"/>
          </button>
        </div>
        <div className="scroll" style={{ flex:1 }}>
          {library.length === 0 && (
            <div style={{ padding:'24px 16px', textAlign:'center' }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>No research yet</span>
            </div>
          )}
          {library.map(item => {
            const on = item.id === active;
            return (
              <div key={item.id} style={{ position:'relative', borderBottom:'1px solid var(--border)',
                background: on ? 'var(--accent-bg)' : 'transparent',
                borderLeft:`2px solid ${on ? 'var(--accent)' : 'transparent'}` }}>
                <button onClick={() => onSelect(item.id)} style={{ width:'100%', textAlign:'left',
                  padding:'11px 14px', cursor:'pointer', display:'block' }}>
                  <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:6, marginBottom:4 }}>
                    <span style={{ fontFamily:'var(--font-b)', fontSize:12.5, fontStyle:'italic',
                      color: on ? 'var(--text)' : 'var(--text-q)', lineHeight:1.3,
                      display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical', overflow:'hidden' }}>
                      {item.query}
                    </span>
                    <StatusMark status={item.status}/>
                  </div>
                  <div style={{ display:'flex', gap:8 }}>
                    <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}>
                      {fmtTime(item.completed_at || item.started_at)}
                    </span>
                    {item.source_count > 0 && (
                      <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}>
                        {item.source_count} src
                      </span>
                    )}
                  </div>
                </button>
                <button onClick={() => onDelete(item.id)} title="Delete report" style={{
                  position:'absolute', bottom:9, right:10, width:20, height:20, borderRadius:6,
                  display:'grid', placeItems:'center', color:'var(--text-3)', cursor:'pointer',
                  background:'transparent' }}>
                  <Ico n="trash" size={11} color="currentColor"/>
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

function ResearchSurface() {
  const [library, setLibrary]     = useState([]);
  const [active, setActive]       = useState(null);
  const [detail, setDetail]       = useState(null);
  const [loading, setLoading]     = useState(false);
  const [querying, setQuerying]   = useState('');
  const [depth, setDepth]         = useState('medium');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]         = useState('');
  const [streamPhase, setStreamPhase] = useState('');
  const [view, setView]           = useState('read');  // 'read' (prose) | 'claims' (cards)
  const [composing, setComposing] = useState(true);    // true → show the launcher
  const [drawerOpen, setDrawerOpen] = useState(false);
  const streamReaders = useRef({});  // keyed by research_id
  const activeRef     = useRef(null);
  useEffect(() => { activeRef.current = active; }, [active]);

  useEffect(() => {
    loadLibrary();
    return () => {  // cancel any open SSE readers on unmount
      Object.values(streamReaders.current).forEach(r => {
        try { r && r.cancel && r.cancel(); } catch {}
      });
      streamReaders.current = {};
    };
  }, []);

  function loadLibrary() {
    fetch('/api/research')
      .then(r => r.ok ? r.json() : { research:[] })
      .then(d => setLibrary(d.research || []))
      .catch(() => {});
  }

  /* Re-fetch the full (possibly partial) report from the DB. */
  function refreshDetail(sid) {
    return fetch(`/api/research/${sid}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const item = d ? (d.research || d) : null;
        if (item && activeRef.current === sid) setDetail(item);
        return item;
      })
      .catch(() => null);
  }

  function selectItem(id) {
    setComposing(false);
    setDrawerOpen(false);
    setActive(id);
    activeRef.current = id;
    setDetail(null);
    setLoading(true);
    setStreamPhase('');
    fetch(`/api/research/${id}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const item = d ? (d.research || d) : null;
        setDetail(item);
        setLoading(false);
        if (item && item.status === 'running' && !streamReaders.current[id]) {
          streamResearch(id);
        }
      })
      .catch(() => setLoading(false));
  }

  async function streamResearch(sid) {
    if (streamReaders.current[sid]) return;  // already streaming
    streamReaders.current[sid] = true;

    try {
      const resp = await fetch(`/api/research/${sid}/stream`);
      if (!resp.ok || !resp.body) { delete streamReaders.current[sid]; pollResearch(sid); return; }

      const reader = resp.body.getReader();
      streamReaders.current[sid] = reader;
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const ev = JSON.parse(raw);
            handleProgressEvent(ev, sid);
            if (ev.phase === 'done' || ev.phase === 'error') {
              delete streamReaders.current[sid];
              return;
            }
          } catch {}
        }
      }
    } catch {
      delete streamReaders.current[sid];
      pollResearch(sid);  // network failure — fall back to polling
    }
  }

  function handleProgressEvent(ev, sid) {
    if (activeRef.current !== sid && ev.phase !== 'done' && ev.phase !== 'error') return;
    switch (ev.phase) {
      case 'planning':
        setStreamPhase('Planning…');
        break;
      case 'round':
        setStreamPhase(`Round ${ev.round}: exploring ${(ev.sub_questions||[]).length} questions…`);
        break;
      case 'sources_found':
        // Honest counts: distinct sources vs. raw passages examined.
        setStreamPhase(
          ev.passages != null
            ? `${ev.count} sources · ${ev.passages} passages examined…`
            : `${ev.count} sources gathered…`);
        break;
      case 'synthesizing':
        setStreamPhase('Synthesizing claims…');
        break;
      case 'claim_verified':
        setStreamPhase('Verifying claims against sources…');
        break;
      case 'section_ready':
        setStreamPhase('Writing…');
        refreshDetail(sid);          // pull the newly-persisted section + claims
        break;
      case 'done':
        delete streamReaders.current[sid];
        setLibrary(prev => prev.map(it => it.id === sid ? { ...it, status:'done' } : it));
        if (activeRef.current === sid) { setStreamPhase(''); refreshDetail(sid); }
        break;
      case 'error':
        delete streamReaders.current[sid];
        setLibrary(prev => prev.map(it => it.id === sid ? { ...it, status:'error' } : it));
        if (activeRef.current === sid) setStreamPhase('');
        break;
      case 'heartbeat':
        break;
    }
  }

  function pollResearch(sid) {
    const interval = setInterval(() => {
      fetch(`/api/research/${sid}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          const s = data ? (data.research || data) : null;
          if (!s) { clearInterval(interval); return; }
          if (activeRef.current === sid) setDetail(s);
          if (s.status === 'done' || s.status === 'error') {
            clearInterval(interval);
            setLibrary(prev => prev.map(it => it.id === sid ? { ...it, status:s.status } : it));
          }
        })
        .catch(() => clearInterval(interval));
    }, 3000);
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
        body:JSON.stringify({ query:q, depth }),
      });
      if (!resp.ok) {
        const d = await resp.json().catch(() => ({}));
        setError(d.detail || 'Could not start research');
      } else {
        const d = await resp.json();
        setQuerying('');
        const placeholder = { id:d.session_id, query:q, status:'running', source_count:0, started_at:Date.now()/1000 };
        setLibrary(prev => [placeholder, ...prev]);
        setActive(d.session_id);
        activeRef.current = d.session_id;
        setDetail({ ...placeholder, sections:[], sources:[], claims:[] });
        setStreamPhase('Starting…');
        setComposing(false);
        setDrawerOpen(false);
        streamResearch(d.session_id);
      }
    } catch { setError('Request failed'); }
    setSubmitting(false);
  }

  async function deleteResearch(id) {
    try { await fetch(`/api/research/${id}`, { method:'DELETE' }); } catch {}
    try {
      const reader = streamReaders.current[id];
      if (reader && reader.cancel) reader.cancel();
    } catch {}
    delete streamReaders.current[id];
    setLibrary(prev => prev.filter(it => it.id !== id));
    if (activeRef.current === id) {
      setActive(null); activeRef.current = null;
      setDetail(null); setComposing(true);
    }
  }

  function newResearch() {
    setComposing(true);
    setDrawerOpen(false);
    setQuerying('');
    setError('');
  }

  function fmtTime(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined,{month:'short',day:'numeric'});
  }

  /* ── Derived view state (report view) ── */
  const doc = detail || {};
  const docTitle = doc.query || '';
  const sources = doc.sources || [];
  const claims  = doc.claims || [];
  const sectionsArr = doc.sections || [];
  const contradictions = doc.contradictions || [];
  const isRunning = doc.status === 'running';
  const stats = doc.stats;

  const claimsBySection = {};
  claims.forEach(c => {
    const k = c.section_idx == null ? 0 : c.section_idx;
    (claimsBySection[k] = claimsBySection[k] || []).push(c);
  });
  const hasClaims = claims.length > 0;

  const rawReport = (doc.raw_report || doc.result || '').trim();
  const proseParts = !hasClaims && rawReport ? rawReport.split('\n\n') : [];

  const pill = (on) => ({
    display:'flex', alignItems:'center', gap:6, padding:'5px 12px', borderRadius:9,
    border:`1px solid ${on ? 'var(--accent-bd)' : 'var(--border-2)'}`,
    background: on ? 'var(--accent-bg)' : 'transparent', cursor:'pointer',
    transition:'all var(--t)',
  });

  return (
    <div className="surface-enter" style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>

      {/* ── Top bar ── */}
      <div style={{ height:48, flexShrink:0, background:'var(--nav-bg)',
        borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center',
        justifyContent:'space-between', padding:'0 16px' }}>
        <button onClick={() => setDrawerOpen(o => !o)} style={pill(drawerOpen)}>
          <Ico n="book" size={13} color={drawerOpen ? 'var(--accent-tx)' : 'var(--text-3)'}/>
          <span style={{ fontFamily:'var(--font-m)', fontSize:10.5,
            color: drawerOpen ? 'var(--accent-tx)' : 'var(--text-3)', letterSpacing:'.03em' }}>Recents</span>
          {library.length > 0 && (
            <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)' }}>{library.length}</span>
          )}
        </button>
        {!composing && (
          <button onClick={newResearch} style={pill(false)}>
            <Ico n="plus" size={12} color="var(--text-3)"/>
            <span style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)', letterSpacing:'.03em' }}>
              New research
            </span>
          </button>
        )}
      </div>

      {/* ── Content ── */}
      <div style={{ flex:1, minHeight:0, position:'relative', display:'flex', overflow:'hidden' }}>

        {drawerOpen && (
          <RecentsDrawer
            library={library} active={active}
            onSelect={selectItem} onDelete={deleteResearch}
            onClose={() => setDrawerOpen(false)} fmtTime={fmtTime}
          />
        )}

        {composing ? (
          <ResearchLauncher
            query={querying} setQuery={setQuerying}
            depth={depth} setDepth={setDepth}
            onStart={handleStart} submitting={submitting} error={error}
          />
        ) : (
          <>
            {/* ── Document ── */}
            <div className="scroll" style={{ flex:1, padding:'40px 0', background:'var(--thread-bg)' }}>
              {loading && (
                <div style={{ maxWidth:880, margin:'0 auto', padding:'0 64px' }}>
                  {[80,65,90,70,85].map((w,i) => (
                    <div key={i} className="shimmer" style={{ height:12, width:`${w}%`, marginBottom:12, borderRadius:3 }}/>
                  ))}
                </div>
              )}
              {!loading && !detail && (
                <EmptyState icon="search" title="Nothing to show"
                  subtitle="pick a report from Recents, or start a new one"/>
              )}
              {!loading && detail && (
                <div style={{ maxWidth:880, margin:'0 auto', padding:'0 64px' }}>
                  {/* header */}
                  <div style={{ marginBottom:28 }}>
                    <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
                      letterSpacing:'.14em', textTransform:'uppercase', display:'block', marginBottom:10 }}>
                      Deep Research · {fmtTime(doc.completed_at||doc.started_at)}
                    </span>
                    <h1 style={{ fontFamily:'var(--font-d)', fontSize:36, fontWeight:500,
                      color:'var(--text)', lineHeight:1.1, letterSpacing:'.01em' }}>{docTitle}</h1>
                    {stats && (
                      <div style={{ display:'flex', gap:14, marginTop:10, flexWrap:'wrap' }}>
                        {stats.Duration && <StatPill>{stats.Duration}</StatPill>}
                        {stats.Rounds   && <StatPill>{stats.Rounds} rounds</StatPill>}
                        {stats.Claims   && <StatPill>{stats.Claims} claims</StatPill>}
                        {stats.Cited != null && stats.Examined != null
                          ? <StatPill>{stats.Cited} cited of {stats.Examined} examined</StatPill>
                          : sources.length > 0 && <StatPill>{sources.length} sources</StatPill>}
                      </div>
                    )}
                  </div>

                  {/* running phase indicator */}
                  {isRunning && streamPhase && (
                    <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:20 }}>
                      <Pulse size={7}/>
                      <span style={{ fontFamily:'var(--font-m)', fontSize:11,
                        color:'var(--text-3)', fontStyle:'italic' }}>{streamPhase}</span>
                    </div>
                  )}

                  {/* summary lede */}
                  {doc.summary && (
                    <p style={{ fontFamily:'var(--font-d)', fontSize:20, fontStyle:'italic',
                      lineHeight:1.7, color:'var(--text)', marginBottom:22 }}>{doc.summary}</p>
                  )}

                  {/* contradiction banner */}
                  {contradictions.length > 0 && (
                    <div style={{ border:'1px solid rgba(181,86,46,.28)', background:'rgba(181,86,46,.06)',
                      borderRadius:8, padding:'14px 16px', marginBottom:24 }}>
                      <div style={{ display:'flex', alignItems:'center', gap:7, marginBottom:8 }}>
                        <span style={{ width:7, height:7, borderRadius:'50%', background:'#B5562E',
                          display:'inline-block', flexShrink:0 }}/>
                        <span style={{ fontFamily:'var(--font-m)', fontSize:10, letterSpacing:'.1em',
                          textTransform:'uppercase', color:'#B5562E' }}>
                          {contradictions.length} contradiction{contradictions.length>1?'s':''} — sources disagree
                        </span>
                      </div>
                      {contradictions.map((c, i) => (
                        <p key={i} style={{ fontFamily:'var(--font-b)', fontSize:13, lineHeight:1.6,
                          color:'var(--text-q)', margin:'4px 0 0' }}>
                          {c.text}<Cite citations={c.citations}/>
                        </p>
                      ))}
                    </div>
                  )}

                  {/* body: claim cards / prose toggle (preferred) or legacy prose */}
                  {hasClaims ? (
                    <div>
                      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:18 }}>
                        <Segmented value={view} onChange={setView}
                          options={[['read','Read'],['claims','Claims']]}/>
                      </div>

                      {view === 'claims' ? (
                        /* ── Claims view: one verified card per atomic claim ── */
                        <div>
                          {sectionsArr.map((sec, i) => {
                            const secClaims = claimsBySection[i] || [];
                            return (
                              <div key={i} style={{ marginBottom:28 }}>
                                {sec.title && (
                                  <h3 style={{ fontFamily:'var(--font-d)', fontSize:18, fontStyle:'italic',
                                    color:'var(--text)', fontWeight:400, lineHeight:1.2, marginBottom:12 }}>
                                    {sec.title}
                                  </h3>
                                )}
                                {secClaims.length > 0
                                  ? secClaims.map((c) => <ClaimCard key={c.id} claim={c}/>)
                                  : sec.content && (
                                    <p style={{ fontFamily:'var(--font-b)', fontSize:15, lineHeight:1.8,
                                      color:'var(--text-q)' }}>{sec.content}</p>
                                  )}
                              </div>
                            );
                          })}
                          {(claimsBySection[sectionsArr.length] || []).map((c) => (
                            <ClaimCard key={c.id} claim={c}/>
                          ))}
                        </div>
                      ) : (
                        /* ── Read view: claims flow as prose; verification on hover ── */
                        <div style={{ display:'flex', gap:20 }}>
                          <div style={{ width:1.5, background:'var(--bar)', borderRadius:1, flexShrink:0 }}/>
                          <div style={{ flex:1, minWidth:0 }}>
                            {sectionsArr.map((sec, i) => {
                              const secClaims = claimsBySection[i] || [];
                              return (
                                <div key={i} style={{ marginBottom:26 }}>
                                  {sec.title && (
                                    <h3 style={{ fontFamily:'var(--font-d)', fontSize:18, fontStyle:'italic',
                                      color:'var(--text)', fontWeight:400, lineHeight:1.2, marginBottom:10 }}>
                                      {sec.title}
                                    </h3>
                                  )}
                                  {secClaims.length > 0 ? (
                                    <p style={{ fontFamily:'var(--font-b)', fontSize:16, lineHeight:1.95,
                                      color:'var(--text)', margin:0 }}>
                                      {secClaims.map((c) => (
                                        <React.Fragment key={c.id}><ClaimSpan claim={c}/>{' '}</React.Fragment>
                                      ))}
                                    </p>
                                  ) : sec.content && (
                                    <p style={{ fontFamily:'var(--font-b)', fontSize:16, lineHeight:1.95,
                                      color:'var(--text-q)', margin:0 }}>{sec.content}</p>
                                  )}
                                </div>
                              );
                            })}
                            {(claimsBySection[sectionsArr.length] || []).length > 0 && (
                              <p style={{ fontFamily:'var(--font-b)', fontSize:16, lineHeight:1.95,
                                color:'var(--text)', margin:0 }}>
                                {(claimsBySection[sectionsArr.length] || []).map((c) => (
                                  <React.Fragment key={c.id}><ClaimSpan claim={c}/>{' '}</React.Fragment>
                                ))}
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : proseParts.length > 0 ? (
                    <div style={{ display:'flex', gap:20 }}>
                      <div style={{ width:1.5, background:'var(--bar)', borderRadius:1, flexShrink:0 }}/>
                      <div>
                        {proseParts.map((para, i) => (
                          <p key={i} style={{ fontFamily:'var(--font-b)', fontSize:15.5, lineHeight:1.85,
                            color:'var(--text)', marginBottom:14 }}>{para}</p>
                        ))}
                      </div>
                    </div>
                  ) : isRunning ? (
                    !streamPhase && (
                      <div style={{ display:'flex', alignItems:'center', gap:12, padding:'24px 0' }}>
                        <Pulse size={8}/>
                        <span style={{ fontFamily:'var(--font-m)', fontSize:13, color:'var(--text-3)' }}>
                          Research in progress…
                        </span>
                      </div>
                    )
                  ) : null}
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
                                lineHeight:1.45, display:'-webkit-box', WebkitLineClamp:3,
                                WebkitBoxOrient:'vertical', overflow:'hidden', textDecoration:'none' }}>
                              {s.title || s.url}
                            </a>
                          ) : (
                            <span style={{ fontFamily:'var(--font-b)', fontSize:12, color:'var(--text-q)',
                              lineHeight:1.45, display:'block' }}>{s.title || 'Source'}</span>
                          )}
                        </div>
                      </div>
                      {i < sources.length-1 && <Rule style={{ marginBottom:12 }}/>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function StatPill({ children }) {
  return <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>{children}</span>;
}

/* Small segmented control (Read | Claims, depth selector). */
function Segmented({ value, onChange, options }) {
  return (
    <div style={{ display:'inline-flex', background:'var(--panel-bg)',
      border:'1px solid var(--border-2)', borderRadius:7, padding:2, gap:2 }}>
      {options.map(([key, label]) => {
        const on = key === value;
        return (
          <button key={key} onClick={() => onChange(key)} style={{
            fontFamily:'var(--font-m)', fontSize:10, letterSpacing:'.04em',
            padding:'4px 11px', borderRadius:5, cursor:'pointer', border:'none',
            background: on ? 'var(--accent-bg)' : 'transparent',
            color: on ? 'var(--accent-tx)' : 'var(--text-3)',
            transition:'background var(--t), color var(--t)' }}>
            {label}
          </button>
        );
      })}
    </div>
  );
}

window.V2Research = { ResearchSurface };
