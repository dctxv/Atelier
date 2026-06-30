/* ====== v2 Chat surface — Atelier backend ====== */
const { useState, useRef, useEffect } = React;

/* ── Session persistence (localStorage) ── */
function loadSessions() {
  try { return JSON.parse(localStorage.getItem('atl_sessions') || '[]'); } catch { return []; }
}
function saveSessions(sessions) {
  // Strip runtime-only fields — backend is the source of truth for messages.
  const stripped = sessions.map(({ messages, _loaded, _notFound, ...meta }) => meta);
  try { localStorage.setItem('atl_sessions', JSON.stringify(stripped.slice(0,50))); } catch {}
}

// localStorage key used to flag a session that was navigated away from mid-stream.
const _INTERRUPTED_KEY = 'atl_interrupted_session';

function newSession(model) {
  return { id: crypto.randomUUID(), name:'New chat', messages:[], model:model||null, createdAt:Date.now() };
}

/* ── Model picker dropdown ── */
function ModelPickerDropdown({ current, onSelect, onClose }) {
  const [models, setModels]   = useState([]);
  const [query,  setQuery]    = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState('');
  const ref = useRef(null);

  useEffect(() => {
    fetch('/api/models')
      .then(r => r.json())
      .then(d => { setModels(d.models||[]); if(d.error) setErr(d.error); })
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const fn = e => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener('mousedown', fn);
    return () => document.removeEventListener('mousedown', fn);
  }, []);

  const filtered = query ? models.filter(m => m.toLowerCase().includes(query.toLowerCase())) : models;

  return (
    <div ref={ref} style={{
      position:'absolute', bottom:'calc(100% + 8px)', left:0,
      width:320, background:'var(--surface)', border:'1px solid var(--border-2)',
      borderRadius:10, zIndex:100, overflow:'hidden',
      boxShadow:'0 8px 32px rgba(0,0,0,.2)',
    }}>
      <div style={{ padding:'9px 12px', borderBottom:'1px solid var(--border)', display:'flex', gap:8 }}>
        <Ico n="search" size={11} color="var(--text-3)"/>
        <input autoFocus value={query} onChange={e=>setQuery(e.target.value)}
          placeholder="Search models…"
          style={{ flex:1, fontFamily:'var(--font-m)', fontSize:12, color:'var(--text)' }}/>
      </div>
      <div style={{ maxHeight:260, overflowY:'auto' }}>
        {loading && <div style={{padding:'18px',textAlign:'center'}}><Pulse size={8}/></div>}
        {!loading && filtered.length===0 && (
          <div style={{padding:'14px 14px',fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',fontStyle:'italic'}}>
            {err || (models.length===0 ? 'No endpoint configured — use /setup' : 'No matches')}
          </div>
        )}
        {filtered.map((m,i) => {
          const on = m===current;
          return (
            <button key={i} onClick={() => onSelect(m)}
              style={{ width:'100%',textAlign:'left',padding:'9px 14px',
                display:'flex',justifyContent:'space-between',alignItems:'center',
                background:on?'var(--accent-bg)':'transparent',
                borderLeft:`2px solid ${on?'var(--accent)':'transparent'}`,
                cursor:'pointer',transition:'background var(--t)',
                borderBottom:'1px solid var(--border)',
              }}>
              <span style={{fontFamily:'var(--font-b)',fontSize:13,fontStyle:'italic',
                color:on?'var(--text)':'var(--text-q)',
                overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:180}}>{m}</span>
              <span style={{fontFamily:'var(--font-m)',fontSize:9,color:'var(--text-3)',
                overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:120,flexShrink:0}}>
                {m.includes('/')?m.split('/')[0]:''}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Command palette ── */
function CommandPalette({ commands, activeIndex, onHover, onRun }) {
  return (
    <div style={{
      position:'absolute', bottom:'calc(100% + 8px)', left:0,
      width:340, background:'var(--surface)', border:'1px solid var(--border-2)',
      borderRadius:10, zIndex:100, overflow:'hidden',
      boxShadow:'0 8px 32px rgba(0,0,0,.2)',
    }}>
      {commands.map((cmd, i) => {
        const active = i === activeIndex;
        return (
          <button key={cmd.id}
            onMouseEnter={() => onHover(i)}
            onClick={() => onRun(cmd)}
            style={{
              width:'100%', textAlign:'left',
              padding:'9px 14px',
              display:'flex', alignItems:'center', gap:8,
              background: active ? 'var(--accent-bg)' : 'transparent',
              borderLeft: `2px solid ${active ? 'var(--accent)' : 'transparent'}`,
              borderBottom: '1px solid var(--border)',
              cursor:'pointer', transition:'background var(--t)',
            }}>
            <Ico n={cmd.icon} size={13} color={active ? 'var(--accent-tx)' : 'var(--text-3)'}/>
            <span style={{
              fontFamily:'var(--font-b)', fontSize:13, fontStyle:'italic',
              color: active ? 'var(--text)' : 'var(--text-q)',
              flex:1,
            }}>{cmd.label}</span>
            {cmd.hint && (
              <span style={{fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)'}}>{cmd.hint}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* ── Move-conversation menu (opens above the composer button) ── */
function MoveMenu({ projectId, onMove, onClose }) {
  const [projects, setProjects] = useState(null);
  const ref = useRef(null);
  useEffect(() => {
    fetch('/api/projects').then(r=>r.json()).then(d=>setProjects(d.projects||[])).catch(()=>setProjects([]));
  }, []);
  useEffect(() => {
    const fn = e => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener('mousedown', fn);
    return () => document.removeEventListener('mousedown', fn);
  }, []);
  const others = (projects || []).filter(p => p.id !== projectId);
  const rowStyle = { width:'100%', textAlign:'left', display:'flex', alignItems:'center', gap:9,
    padding:'9px 14px', fontFamily:'var(--font-b)', fontSize:13, fontStyle:'italic',
    color:'var(--text-q)', cursor:'pointer', borderBottom:'1px solid var(--border)', background:'transparent' };
  return (
    <div ref={ref} style={{ position:'absolute', bottom:'calc(100% + 8px)', left:0, width:260,
      background:'var(--surface)', border:'1px solid var(--border-2)', borderRadius:10, zIndex:100,
      overflow:'hidden', boxShadow:'0 8px 32px rgba(0,0,0,.2)' }}>
      <div style={{ padding:'9px 12px', borderBottom:'1px solid var(--border)',
        fontFamily:'var(--font-m)', fontSize:9.5, letterSpacing:'.1em', textTransform:'uppercase',
        color:'var(--text-3)' }}>
        {projectId ? 'Move conversation' : 'Add to project'}
      </div>
      <div style={{ maxHeight:264, overflowY:'auto' }}>
        {projectId && (
          <button onClick={()=>onMove(null)} style={rowStyle}>
            <Ico n="chat" size={13} color="var(--text-3)"/>
            <span style={{flex:1}}>Move to main chat</span>
          </button>
        )}
        {projects === null && <div style={{padding:14, textAlign:'center'}}><Pulse size={7}/></div>}
        {projects && others.length === 0 && (
          <div style={{padding:'12px 14px', fontFamily:'var(--font-m)', fontSize:11,
            color:'var(--text-3)', fontStyle:'italic'}}>
            {projectId ? 'No other projects.' : 'No projects yet — create one in Projects.'}
          </div>
        )}
        {others.map(p => (
          <button key={p.id} onClick={()=>onMove(p.id)} style={rowStyle}>
            <Ico n="projects" size={13} color="var(--text-3)"/>
            <span style={{flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{p.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function DebugTrace({ data }) {
  if (!data) return null;
  const memories = Array.isArray(data.retrieved_memories) ? data.retrieved_memories : [];
  const docs = Array.isArray(data.retrieved_documents) ? data.retrieved_documents : [];
  const suppressed = Array.isArray(data.suppressed_memories) ? data.suppressed_memories : [];
  const created = Array.isArray(data.memory_atoms_created) ? data.memory_atoms_created : [];
  const derived = Array.isArray(data.derived_atoms_proposed) ? data.derived_atoms_proposed : [];
  const injected = data.injected_context || {};
  const blocks = Array.isArray(injected.blocks) ? injected.blocks : [];

  function itemText(item) {
    if (!item) return '';
    const label = item.filename || item.reason || item.predicate || item.modality || item.source_kind || item.type || 'item';
    const text = item.text || item.id || '';
    return `${label}: ${text}`;
  }
  function rowList(items) {
    if (!items.length) return <span style={{color:'var(--text-3)'}}>none</span>;
    return (
      <div style={{display:'grid',gap:3}}>
        {items.slice(0, 10).map((item, i) => (
          <div key={item.id || i} style={{
            overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',
            color:'var(--text-q)',
          }}>
            {itemText(item)}
          </div>
        ))}
        {items.length > 10 && <div style={{color:'var(--text-3)'}}>+{items.length - 10} more</div>}
      </div>
    );
  }
  function field(label, value) {
    return (
      <div style={{display:'grid',gridTemplateColumns:'140px minmax(0,1fr)',gap:10,alignItems:'start'}}>
        <div style={{color:'var(--text-3)'}}>{label}:</div>
        <div style={{minWidth:0}}>{value}</div>
      </div>
    );
  }

  return (
    <div style={{
      marginTop:12,marginBottom:12,padding:'10px 12px',
      border:'1px solid var(--border-2)',borderRadius:8,
      background:'var(--surface)',fontFamily:'var(--font-m)',fontSize:10.5,
      lineHeight:1.5,color:'var(--text-q)',
    }}>
      <div style={{
        display:'flex',alignItems:'center',justifyContent:'space-between',
        gap:10,marginBottom:8,paddingBottom:7,borderBottom:'1px solid var(--border)',
      }}>
        <span style={{
          fontFamily:'var(--font-m)',fontSize:10,letterSpacing:'.08em',
          textTransform:'uppercase',color:'var(--accent-tx)',
        }}>Debug trace</span>
        <span style={{color:'var(--text-3)'}}>context audit</span>
      </div>
      <div style={{display:'grid',gap:6}}>
        {field('Intent mode', <span>{data.intent_mode || 'unknown'}</span>)}
        {field('Retrieved memories', rowList(memories))}
        {field('Retrieved documents', rowList(docs))}
        {field('Suppressed memories', rowList(suppressed))}
        {field('Injected context', (
          <details open>
            <summary style={{cursor:'pointer',color:'var(--text-q)'}}>
              {blocks.length ? blocks.map(b => `${b.kind} ${b.tokens_estimate || 0}t`).join(', ') : 'none'}
              {injected.truncated ? ' (truncated)' : ''}
            </summary>
            <pre style={{
              margin:'6px 0 0',maxHeight:180,overflow:'auto',whiteSpace:'pre-wrap',
              fontFamily:'var(--font-m)',fontSize:10,color:'var(--text-3)',
              borderTop:'1px solid var(--border)',paddingTop:6,
            }}>{injected.text || 'none'}</pre>
          </details>
        ))}
        {field('Memory atoms created', rowList(created))}
        {field('Derived atoms proposed', rowList(derived))}
        {field('Review state', <span>{JSON.stringify(data.review_state || {})}</span>)}
        {field('Model used', <span>{JSON.stringify(data.model_used || {})}</span>)}
        {data.extraction_skipped && field('Extraction', <span>{data.extraction_skipped}</span>)}
      </div>
    </div>
  );
}

/* ── Burst-message renderer (Mirae / texting persona) ────────────────────────
   Text with " ||| " delimiters is rendered as a sequence of text bubbles —
   one per segment — rather than one monolithic AiBlock.  AiBlock is still
   used for every response that contains no delimiter (backward-compatible).   */
function BurstBlock({ text, model, isLast, streaming, timestamp }) {
  const [showTs, setShowTs] = React.useState(false);

  // Split on the canonical delimiter; filter out any empty segments from trim.
  const parts = (text || '').split(' ||| ');
  // While streaming the last segment is still being typed; everything before it
  // is a "sent" bubble.  When not streaming, all segments are complete.
  const doneParts = (streaming ? parts.slice(0, -1) : parts).filter(s => s.trim());
  const activePart = streaming ? parts[parts.length - 1] : null;

  const bubbleStyle = (i, total) => ({
    fontFamily: 'var(--font-b)',
    fontSize: 15.5,
    lineHeight: 1.68,
    color: 'var(--text)',
    padding: '9px 14px',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 16,
    // First bubble: square top-left corner to signal "start of turn"
    borderTopLeftRadius: i === 0 ? 4 : 16,
    alignSelf: 'flex-start',
    maxWidth: '92%',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  });

  return (
    <div className="fade-up" style={{ flexShrink: 0 }}>
      {/* colophon — shown once for the whole burst group */}
      <div
        onMouseEnter={() => setShowTs(true)}
        onMouseLeave={() => setShowTs(false)}
        style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}
      >
        <ModelBadge model={model}/>
        <span style={{ color:'var(--text-3)', fontSize:10 }}>—</span>
        <span style={{ fontFamily:'var(--font-d)', fontSize:12.5, fontStyle:'italic', color:'var(--text-3)' }}>
          Atelier
        </span>
        {timestamp && (
          <span style={{
            fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
            marginLeft:'auto', opacity: showTs ? 0.7 : 0,
            transition:'opacity 0.15s ease', letterSpacing:'.04em',
          }}>
            {timestamp}
          </span>
        )}
      </div>
      {/* vertical bar + bubble column */}
      <div style={{ display:'flex', gap:20 }}>
        <div style={{ width:1.5, background:'var(--bar)', borderRadius:1, flexShrink:0 }}/>
        <div style={{ flex:1, display:'flex', flexDirection:'column', gap:8 }}>
          {doneParts.map((burst, i) => (
            <div key={i} style={bubbleStyle(i, doneParts.length)}>
              {burst.trim()}
            </div>
          ))}
          {/* The in-progress (streaming) bubble */}
          {activePart !== null && (
            <div style={bubbleStyle(doneParts.length, doneParts.length + 1)}>
              {activePart}
              <span style={{
                display:'inline-block', width:2, height:14,
                background:'var(--accent)', animation:'writing 1.1s step-end infinite', marginLeft:2,
              }}/>
            </div>
          )}
          {isLast && !streaming && (
            <div style={{ display:'flex', gap:6, marginTop:6 }}>
              <button onClick={() => navigator.clipboard.writeText(text || '')}
                style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)',
                  padding:'2px 9px', border:'1px solid var(--border-2)', borderRadius:10,
                  cursor:'pointer', background:'transparent' }}>Copy</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ChatSurface({ onSetup, onSearchSetup, onWeatherSetup, onStockSetup, onToggleTheme, onOpenSettings, onNav, onPlay, activeProject, onExitProject, projectId, onMoved, openSessionId, onConsumeOpen }) {
  // projectId set → this chat is embedded inside a project: all session list/
  // create/seed calls are scoped to it, and the global localStorage cache is
  // left untouched (project chats live only in the backend).
  const [sessions,   setSessions]   = useState(() => projectId ? [] : loadSessions());
  const [activeId,   setActiveId]   = useState(() => { if (projectId) return null; const s=loadSessions(); return s.length?s[0].id:null; });
  const [bootKey,    setBootKey]    = useState(0); // increments when bootstrap finishes; triggers lazy-load re-check
  const [streaming,  setStreaming]   = useState(false);
  const [streamBuf,  setStreamBuf]  = useState('');
  const [streamSearch, setStreamSearch] = useState(null);
  const [streamClock,  setStreamClock]  = useState(null);
  const [streamCard,   setStreamCard]   = useState(null);  // NEW: local-answer card
  const [streamDocs,   setStreamDocs]   = useState(null);
  const [streamProv,   setStreamProv]   = useState(null);  // NEW: provenance chips
  const [streamDebug,  setStreamDebug]  = useState(null);
  const [streamStatus, setStreamStatus] = useState('thinking'); // NEW: 'thinking'|'searching'|'computing'|'recalling'|'streaming'
  const [streamSearchDegraded, setStreamSearchDegraded] = useState(false); // NEW
  const [suggestWeb,   setSuggestWeb]   = useState(false); // NEW: proactive freshness
  const [thinking,   setThinking]   = useState(false);
  const [composer,   setComposer]   = useState('');
  const [config,     setConfig]     = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [moveOpen,   setMoveOpen]   = useState(false);
  const [webSearch,  setWebSearch]  = useState(() => {
    try { return localStorage.getItem('atl_websearch') === '1'; } catch { return false; }
  });
  const [error,      setError]      = useState('');
  const [paletteIndex,     setPaletteIndex]     = useState(0);
  const [paletteDismissed, setPaletteDismissed] = useState(false);
  // Start true when localStorage has sessions so the first render shows "Loading…"
  // instead of flashing the empty state before the lazy-load effect fires.
  const [loadingMsgs,      setLoadingMsgs]      = useState(() => !projectId && loadSessions().length > 0);

  useEffect(() => { try { localStorage.setItem('atl_websearch', webSearch?'1':'0'); } catch {} }, [webSearch]);
  const threadRef   = useRef(null);
  const abortRef    = useRef(null);
  const composerRef = useRef(null);
  // Stable ref to activeId so the unmount cleanup can read the current value
  // without being listed as a dependency of the cleanup effect.
  const activeIdRef = useRef(null);
  // Tracks which session ID is currently being fetched to prevent duplicate in-flight fetches.
  const fetchingRef = useRef(null);

  /* Global keyboard shortcuts */
  useEffect(() => {
    function onKey(e) {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      if (e.key === 'k' || e.key === 'K') {
        e.preventDefault();
        setComposer('/');
        setPaletteDismissed(false);
        setPaletteIndex(0);
        setTimeout(() => composerRef.current?.focus(), 0);
      }
      if ((e.key === 'n' || e.key === 'N') && !streaming) {
        e.preventDefault();
        newSessionAction();
        setTimeout(() => composerRef.current?.focus(), 50);
      }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [streaming]);

  /* Keep ref in sync so cleanup can read it without stale-closure issues. */
  useEffect(() => { activeIdRef.current = activeId; }, [activeId]);

  /* Abort any in-flight stream on unmount and mark the session as interrupted so
     the re-hydration step can display the partial response with an indicator. */
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        const sid = activeIdRef.current;
        if (sid) { try { localStorage.setItem(_INTERRUPTED_KEY, sid); } catch {} }
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, []); // empty deps — cleanup runs exactly once, on unmount

  /* Load backend config (active model) */
  useEffect(() => {
    fetch('/api/config').then(r=>r.json()).then(setConfig).catch(()=>{});
  }, []);

  /* Bootstrap: load the authoritative session list (global, or project-scoped). */
  useEffect(() => { (async () => {
    // 1. One-time migration of any localStorage sessions into the backend.
    //    Global chat only — project chats never live in localStorage.
    if (!projectId) {
      try {
        if (!localStorage.getItem('atl_sessions_migrated')) {
          const existing = await fetch('/api/sessions').then(r=>r.json()).then(d=>d.sessions||[]);
          const local = loadSessions();
          if (existing.length === 0 && local.length > 0) {
            await fetch('/api/sessions/import', {
              method:'POST', headers:{'Content-Type':'application/json'},
              body:JSON.stringify({ sessions: local }),
            });
          }
          localStorage.setItem('atl_sessions_migrated', '1');
        }
      } catch {}
    }
    // 2. Load from backend (authoritative). Fall back to local cache on failure.
    const listUrl = projectId ? `/api/sessions?project_id=${encodeURIComponent(projectId)}` : '/api/sessions';
    let list = [];
    try {
      list = await fetch(listUrl).then(r=>r.json()).then(d=>d.sessions||[]);
    } catch { list = projectId ? [] : loadSessions(); }
    list = list.map(s => ({ ...s, messages: s.messages || [], _loaded: false }));
    // 3. Seed an empty session if there are none.
    if (list.length === 0) {
      try {
        const s = await fetch('/api/sessions', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({ name:'New chat', model: config?.active_model || null,
                                project_id: projectId || undefined }),
        }).then(r=>r.json()).then(d=>d.session);
        list = [{ ...s, messages: [], _loaded: true }];
      } catch {
        const s = newSession(config?.active_model||null); list = [{...s, _loaded:true}];
      }
    }
    // Merge: preserve messages for sessions the lazy-load already fetched.
    // Without this, the bootstrap's setSessions wipes out loaded messages,
    // causing a visible flash of the empty state before the second lazy-load fires.
    setSessions(prev => list.map(s => {
      const ex = prev.find(e => e.id === s.id);
      return (ex && ex._loaded) ? { ...s, messages: ex.messages, _loaded: true } : s;
    }));
    // Honor a requested session to open (e.g. after a move), else the newest.
    const initial = (openSessionId && list.find(s => s.id === openSessionId)) ? openSessionId : list[0].id;
    setActiveId(initial);
    if (openSessionId && onConsumeOpen) onConsumeOpen();
    // Signal that bootstrap is done so the lazy-load re-fires even if activeId didn't change.
    setBootKey(k => k + 1);
  })(); }, []);

  /* Re-hydrate messages from the backend whenever the active session changes or the
     bootstrap finishes.  The only guard is _loaded — we never skip the fetch because
     messages happen to be present in in-memory state (which may be stale). */
  useEffect(() => { (async () => {
    if (!activeId) return;
    if (fetchingRef.current === activeId) return; // fetch already in-flight for this session
    const s = sessions.find(x => x.id === activeId);
    if (!s || s._loaded) return;
    fetchingRef.current = activeId;
    setLoadingMsgs(true);
    try {
      const resp = await fetch(`/api/sessions/${activeId}`);
      if (!resp.ok) {
        // 404 → session was deleted; any other error → surface it
        setSessions(prev => prev.map(x => x.id===activeId
          ? { ...x, _loaded: true, _notFound: resp.status === 404, messages: [] } : x));
        if (resp.status !== 404) setError('Could not load conversation — check your connection.');
        return;
      }
      const data = await resp.json();
      let msgs = data?.session?.messages || [];
      // If the user navigated away while this session was streaming, the backend
      // persisted whatever tokens arrived.  Append the interrupted indicator so
      // the cut-off is obvious without losing any content.
      const interruptedId = (() => { try { return localStorage.getItem(_INTERRUPTED_KEY); } catch { return null; } })();
      if (interruptedId === activeId && msgs.length > 0 && msgs[msgs.length - 1].role === 'assistant') {
        msgs = [
          ...msgs.slice(0, -1),
          { ...msgs[msgs.length - 1], content: msgs[msgs.length - 1].content + '\n\n*— interrupted*' },
        ];
        try { localStorage.removeItem(_INTERRUPTED_KEY); } catch {}
      }
      setSessions(prev => prev.map(x => x.id===activeId
        ? { ...x, messages: msgs, _loaded: true, _notFound: false } : x));
    } catch {
      setSessions(prev => prev.map(x => x.id===activeId
        ? { ...x, _loaded: true, messages: [], _notFound: false } : x));
      setError('Could not load conversation — check your connection.');
    } finally {
      if (fetchingRef.current === activeId) fetchingRef.current = null;
      setLoadingMsgs(false);
    }
  })(); }, [activeId, bootKey]); // bootKey ensures re-run after bootstrap even if activeId is unchanged

  useEffect(() => { if (!projectId) saveSessions(sessions); }, [sessions]);

  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [activeId, sessions, streamBuf, streamDebug, composer]);

  const session = sessions.find(s=>s.id===activeId) || sessions[0] || null;

  function selectSession(id) { if (!streaming) setActiveId(id); }

  async function newSessionAction() {
    let s;
    try {
      s = await fetch('/api/sessions', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ name:'New chat', model: config?.active_model||null,
                              project_id: projectId || undefined }),
      }).then(r=>r.json()).then(d=>d.session);
    } catch { s = newSession(config?.active_model||null); }
    const entry = { ...s, messages: [], _loaded: true };
    setSessions(prev => [entry, ...prev]);
    setActiveId(entry.id);
  }

  /* Remove a session from THIS surface's local list and pick a new active one.
     Used by both delete and move (a moved chat leaves this scope). */
  function dropLocalSession(id) {
    setSessions(prev => {
      const next = prev.filter(s=>s.id!==id);
      if (next.length === 0) {
        // Project chats must stay backend-scoped, so create through the API.
        if (projectId) { setTimeout(() => newSessionAction(), 0); if (activeId===id) setActiveId(null); return []; }
        const s = newSession(config?.active_model||null); setActiveId(s.id); return [s];
      }
      if (activeId===id) setActiveId(next[0].id);
      return next;
    });
  }

  function deleteSession(id) {
    fetch(`/api/sessions/${id}`, { method:'DELETE' }).catch(()=>{});
    dropLocalSession(id);
  }

  /* Move the active conversation to a project (target = project id) or back to
     the main chat (target = null). It leaves this surface and the parent
     navigates to its new home. */
  async function moveTo(target) {
    const sid = activeId;
    if (!sid || streaming) return;
    setMoveOpen(false);
    try {
      await fetch(`/api/sessions/${sid}`, {
        method:'PATCH', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ project_id: target }),
      });
    } catch {}
    dropLocalSession(sid);
    if (onMoved) onMoved(sid, target);
  }

  async function handleModelSelect(model) {
    setPickerOpen(false);
    setConfig(prev => ({...prev, active_model:model}));
    await fetch('/api/config', { method:'PATCH', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({active_model:model}) }).catch(()=>{});
    setSessions(prev => prev.map(s => s.id===activeId ? {...s, model} : s));
    fetch(`/api/sessions/${activeId}`, { method:'PATCH', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ model }) }).catch(()=>{});
  }

  const COMMANDS = [
    { id:'new',     label:'New conversation',                   hint:'',               icon:'plus',   keywords:['new','chat','session'],                              run:() => newSessionAction() },
    { id:'model',   label:'Switch model',                       hint:'',               icon:'chat',   keywords:['model','switch','pick'],                             run:() => setPickerOpen(true) },
    { id:'web',     label:`Web search: ${webSearch?'on':'off'}`,hint:'toggle',         icon:'globe',  keywords:['web','search','toggle'],                             run:() => setWebSearch(v => !v) },
    { id:'theme',   label:'Toggle theme',                       hint:'',               icon: (document.documentElement.dataset.theme==='mono'?'sun':'moon'), keywords:['theme','dark','light','mono'], run:() => onToggleTheme && onToggleTheme() },
    { id:'setup',   label:'Set up model / endpoint',            hint:'/setup',         icon:'plus',   keywords:['setup','model','endpoint','api','connect'],          run:() => onSetup && onSetup() },
    { id:'search',  label:'Configure web search',               hint:'/setup search',  icon:'globe',  keywords:['setup','search','tavily','brave','provider'],        run:() => onSearchSetup && onSearchSetup() },
    { id:'weather', label:'Configure weather API',              hint:'/setup weather', icon:'globe',  keywords:['setup','weather','openweathermap'],                  run:() => onWeatherSetup && onWeatherSetup() },
    { id:'stock',   label:'Configure stock API',                hint:'/setup stock',   icon:'globe',  keywords:['setup','stock','finnhub','quote'],                   run:() => onStockSetup && onStockSetup() },
    { id:'settings', label:'Open settings',                       hint:'',               icon:'gear',   keywords:['settings','preferences','config','options'],         run:() => onOpenSettings && onOpenSettings() },
    { id:'setmodel', label:'Set main model',                      hint:'',               icon:'gear',   keywords:['model','main','primary','default'],                  run:() => onOpenSettings && onOpenSettings('models') },
    { id:'setfast',  label:'Set fast model',                      hint:'',               icon:'gear',   keywords:['fast','cheap','background','quick'],                 run:() => onOpenSettings && onOpenSettings('models') },
    { id:'persona',  label:'Set system prompt',                   hint:'',               icon:'gear',   keywords:['system','prompt','persona','personality'],           run:() => onOpenSettings && onOpenSettings('persona') },
    { id:'play',     label:'Play a game',                         hint:'/play',          icon:'play',   keywords:['play','game','games','2048','fun','break'],          run:() => onPlay && onPlay() },
  ];

  const paletteQuery = composer.startsWith('/') ? composer.slice(1).toLowerCase().trim() : null;
  const filteredCommands = paletteQuery === null ? [] :
    COMMANDS.filter(c => !paletteQuery ||
      c.label.toLowerCase().includes(paletteQuery) ||
      c.keywords.some(k => k.includes(paletteQuery)));
  const paletteOpen = paletteQuery !== null && !paletteDismissed && filteredCommands.length > 0;

  function runCommand(cmd) {
    setComposer('');
    setPaletteDismissed(false);
    setPaletteIndex(0);
    cmd.run();
  }

  async function handleSend() {
    const text = composer.trim();
    if (!text || streaming) return;

    const model = session?.model || config?.active_model;
    if (!model) { setError('No model selected — use /setup or pick one below.'); return; }

    setComposer(''); setError('');

    const userMsg = { role:'user', content:text };
    const updatedMsgs = [...(session?.messages||[]), userMsg];
    const sessionName = session?.name === 'New chat' ? text.slice(0,50) : session?.name;

    setSessions(prev => prev.map(s => s.id===activeId
      ? {...s, messages:updatedMsgs, name:sessionName} : s));

    if (session?.name === 'New chat') {
      fetch(`/api/sessions/${activeId}`, { method:'PATCH', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ name: text.slice(0,50) }) }).catch(()=>{});
    }

    setStreaming(true); setStreamBuf(''); setStreamSearch(null); setStreamClock(null); setStreamDocs(null);
    setStreamCard(null); setStreamStatus('thinking'); setStreamSearchDegraded(false); setSuggestWeb(false);
    setStreamProv(null); setStreamDebug(null);
    setThinking(true);

    const controller = new AbortController();
    abortRef.current = controller;
    let searchTrace = null;
    let clockData   = null;
    let cardData    = null;
    let provData    = null;
    let debugData   = null;

    try {
      const resp = await fetch('/api/chat/stream', {
        method:'POST', signal:controller.signal,
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ model, messages:updatedMsgs, web_search: webSearch, session_id: activeId, project_id: projectId || activeProject?.id || undefined }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf='', accumulated='';

      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        buf += decoder.decode(value, {stream:true});
        const lines = buf.split('\n');
        buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw==='[DONE]') break;
          try {
            const evt = JSON.parse(raw);

            // ── Typed event envelope (new) ────────────────────────────────
            if (evt.type) {
              switch (evt.type) {
                case 'clock':
                  clockData = evt.data; setStreamClock(clockData); setThinking(false); break;
                case 'card':
                  cardData = evt.data; setStreamCard(cardData); setThinking(false); break;
                case 'docs':
                  setStreamDocs(evt.data); break;
                case 'provenance':
                  provData = evt.data; setStreamProv(provData); break;
                case 'debug':
                  debugData = evt.data; setStreamDebug(debugData); setThinking(false); break;
                case 'search':
                  if (evt.data.degraded) {
                    setStreamSearchDegraded(true);
                  } else {
                    searchTrace = evt.data; setStreamSearch(searchTrace);
                  }
                  break;
                case 'status':
                  if (evt.data === 'suggest_web') {
                    setSuggestWeb(true);
                  } else if (evt.data === 'searching') {
                    setStreamStatus('searching'); setThinking(false);
                  } else if (evt.data === 'computing') {
                    setStreamStatus('computing'); setThinking(false);
                  } else if (evt.data === 'recalling') {
                    setStreamStatus('recalling'); setThinking(false);
                  } else if (evt.data === 'streaming') {
                    setStreamStatus('streaming'); setThinking(false);
                  } else if (evt.data === 'stalled') {
                    setStreamStatus('stalled');
                  } else if (evt.data === 'interrupted') {
                    setStreamStatus('interrupted');
                  }
                  break;
                case 'error':
                  const code = evt.data?.code || 'unknown';
                  const msgs_ = {
                    auth: 'Authentication failed — check your API key.',
                    provider_5xx: 'Provider error — the model service returned an error.',
                    stream_timeout: 'Stream timed out. The model may be overloaded.',
                    no_model: 'No model selected.',
                  };
                  setError(msgs_[code] || String(evt.data?.message || 'Stream failed.'));
                  break;
              }
              continue;
            }

            // ── Legacy event keys (backward compat) ───────────────────────
            if (evt.error) { setError(String(evt.error)); break; }
            if (evt.atelier_clock)  { clockData = evt.atelier_clock; setStreamClock(clockData); setThinking(false); continue; }
            if (evt.atelier_search) { searchTrace = evt.atelier_search; setStreamSearch(searchTrace); continue; }
            if (evt.atelier_docs)   { setStreamDocs(evt.atelier_docs); continue; }

            // ── Token delta ───────────────────────────────────────────────
            const delta = evt.choices?.[0]?.delta?.content;
            if (delta) { setThinking(false); accumulated+=delta; setStreamBuf(accumulated); }
          } catch(_) {}
        }
      }

      const aiMsg = { role:'assistant', content:accumulated, model, search:searchTrace,
                      clock:clockData, card:cardData, docs:streamDocs, prov:provData,
                      debug:debugData };
      setSessions(prev => prev.map(s => s.id===activeId
        ? {...s, messages:[...updatedMsgs, aiMsg]} : s));
      setStreamBuf(''); setStreamSearch(null); setStreamClock(null); setStreamDocs(null);
      setStreamCard(null); setStreamStatus('thinking'); setSuggestWeb(false); setThinking(false);
      setStreamProv(null); setStreamDebug(null);
    } catch(e) {
      if (e.name!=='AbortError') setError('Stream failed — check your model connection.');
    } finally {
      setStreaming(false); setThinking(false); setStreamClock(null); setStreamDebug(null); abortRef.current = null;
    }
  }

  function handleKeyDown(e) {
    if (paletteOpen) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setPaletteIndex(i => Math.min(i+1, filteredCommands.length-1)); return; }
      if (e.key === 'ArrowUp')   { e.preventDefault(); setPaletteIndex(i => Math.max(i-1, 0)); return; }
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runCommand(filteredCommands[paletteIndex]); return; }
      if (e.key === 'Escape')    { e.preventDefault(); setPaletteDismissed(true); return; }
    }
    if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  /* Build rendered message list */
  const msgs = session?.messages || [];
  const renderedMsgs = [];
  for (let i=0; i<msgs.length; i++) {
    const msg = msgs[i];
    if (msg.role==='user') {
      if (i>0 && msgs[i-1].role==='assistant') renderedMsgs.push({type:'divider',key:`d${i}`});
      renderedMsgs.push({type:'user',key:`u${i}`,text:msg.content});
    } else if (msg.role==='assistant') {
      renderedMsgs.push({type:'ai',key:`a${i}`,text:msg.content,model:msg.model,
        search:msg.search,clock:msg.clock,card:msg.card,docs:msg.docs,prov:msg.prov,
        debug:msg.debug,
        createdAt:msg.created_at,
        isLast:i===msgs.length-1&&!streaming});
    }
  }
  const activeModel = session?.model || config?.active_model || '';
  const modelShort = activeModel.split('/').pop().split(':')[0] || '';
  const noModel = !activeModel;
  const tabs = sessions.map(s => ({id:s.id, label:s.name||'Untitled'}));

  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%',overflow:'hidden'}} className="surface-enter">

      {/* Scrollable tab bar */}
      <ChatTabBar
        tabs={tabs}
        active={activeId}
        onSelect={selectSession}
        onDelete={deleteSession}
        onNew={newSessionAction}
      />

      {/* Thread */}
      <div ref={threadRef} className="scroll" style={{
        flex:1, background:'var(--thread-bg)', padding:'32px 0',
        display:'flex', flexDirection:'column', gap:28,
      }}>
        {(loadingMsgs || session && !session._loaded) && !streaming && (
          <div style={{maxWidth:'50%',width:'100%',margin:'0 auto',padding:'0 60px'}}>
            <p style={{fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',fontStyle:'italic'}}>
              Loading conversation…
            </p>
          </div>
        )}
        {session?._loaded && session._notFound && !streaming && (
          <EmptyState icon="chat" title="Conversation not found"
            subtitle="this conversation no longer exists — start a new one below"/>
        )}
        {(!session || (session._loaded && !session._notFound && msgs.length===0)) && !streaming && (
          <EmptyState icon="chat"
            title={noModel?'Welcome':'New conversation'}
            subtitle={noModel?'type /setup to add a model':'send a message to begin'}/>
        )}
        {renderedMsgs.map(item => {
          if (item.type==='divider') return (
            <div key={item.key} style={{maxWidth:'50%',width:'100%',margin:'0 auto',padding:'0 60px'}}>
              <TurnDots/>
            </div>
          );
          if (item.type==='user') return (
            <div key={item.key} style={{maxWidth:'50%',width:'100%',margin:'0 auto',padding:'0 60px'}}>
              <UserQuery text={item.text}/>
            </div>
          );
          if (item.type==='ai') {
            const card = item.card;
            const cardKind = card?.kind;
            const createdAt = item.createdAt;
            function fmtTime(ts) {
              if (!ts) return '';
              try {
                // ts is epoch seconds from backend
                const d = new Date(ts * 1000);
                return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
              } catch { return ''; }
            }
            function makeAskAbout(cardData_) {
              return () => {
                const payload = JSON.stringify(cardData_, null, 2);
                setComposer(`Tell me more about this: ${payload.slice(0,120)}`);
              };
            }
            return (
              <div key={item.key} style={{maxWidth:'50%',width:'100%',margin:'0 auto',padding:'0 60px'}}>
                {item.clock  && <ClockCard data={item.clock}/>}
                {cardKind==='math'    && <MathCard    data={card} onAskAbout={makeAskAbout(card)}/>}
                {cardKind==='unit'    && <UnitCard    data={card} onAskAbout={makeAskAbout(card)}/>}
                {cardKind==='stock'   && <StockCard   data={card} onAskAbout={makeAskAbout(card)}/>}
                {cardKind==='weather' && <WeatherCard data={card} onAskAbout={makeAskAbout(card)}/>}
                {card && !['math','unit','stock','weather'].includes(cardKind) && (
                  <LocalToolCard data={card} onAskAbout={makeAskAbout(card)}/>
                )}
                {item.search && <WebSearchTrace trace={item.search}/>}
                {item.prov && <ProvenanceChips prov={item.prov} onNav={onNav}/>}
                {item.text && (
                  item.text.includes(' ||| ')
                    ? <BurstBlock text={item.text} model={item.model} isLast={item.isLast} timestamp={fmtTime(createdAt)}/>
                    : <AiBlock    text={item.text} model={item.model} isLast={item.isLast} timestamp={fmtTime(createdAt)}/>
                )}
                {/* DebugTrace hidden */}
              </div>
            );
          }
          return null;
        })}
        {streaming && (
          <div style={{maxWidth:'50%',width:'100%',margin:'0 auto',padding:'0 60px'}}>
            {/* Suggest-web prompt */}
            {suggestWeb && (
              <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:12,
                padding:'8px 12px',borderRadius:8,border:'1px solid var(--border-2)',
                background:'var(--surface)',flexShrink:0}}>
                <Ico n="globe" size={12} color="var(--text-3)"/>
                <span style={{fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',flex:1}}>
                  This might need current info
                </span>
                <button onClick={()=>{ setSuggestWeb(false); setWebSearch(true); }}
                  style={{fontFamily:'var(--font-m)',fontSize:9.5,padding:'2px 10px',
                    borderRadius:8,border:'1px solid var(--accent-bd)',background:'var(--accent-bg)',
                    color:'var(--accent-tx)',cursor:'pointer'}}>Search the web</button>
              </div>
            )}
            {streamClock  && <ClockCard data={streamClock}/>}
            {/* Streaming local-answer cards */}
            {streamCard && streamCard.kind==='math'    && <MathCard    data={streamCard}/>}
            {streamCard && streamCard.kind==='unit'    && <UnitCard    data={streamCard}/>}
            {streamCard && streamCard.kind==='stock'   && <StockCard   data={streamCard}/>}
            {streamCard && streamCard.kind==='weather' && <WeatherCard data={streamCard}/>}
            {streamCard && !['math','unit','stock','weather'].includes(streamCard.kind) && (
              <LocalToolCard data={streamCard}/>
            )}
            {streamSearch && <WebSearchTrace trace={streamSearch} searching={streamStatus==='searching'}/> }
            {streamSearchDegraded && (
              <div style={{marginBottom:10,display:'flex',alignItems:'center',gap:8,
                padding:'7px 12px',borderRadius:8,border:'1px solid var(--border-2)',
                background:'var(--surface)',flexShrink:0,opacity:.7}}>
                <Ico n="globe" size={12} color="var(--text-3)"/>
                <span style={{fontFamily:'var(--font-m)',fontSize:10.5,color:'var(--text-3)',fontStyle:'italic'}}>
                  web search unavailable — answering from knowledge
                </span>
              </div>
            )}
            {streamProv && <ProvenanceChips prov={streamProv} onNav={onNav}/>}
            {streamDocs && streamDocs.length > 0 && !streamProv && (
              <div style={{marginBottom:12,display:'flex',flexWrap:'wrap',gap:6}}>
                {streamDocs.map(fn => (
                  <span key={fn} style={{fontFamily:'var(--font-m)',fontSize:10.5,
                    padding:'3px 10px',borderRadius:20,letterSpacing:'.03em',
                    background:'var(--surface)',border:'1px solid var(--border-2)',
                    color:'var(--text-3)'}}>
                    📄 {fn}
                  </span>
                ))}
              </div>
            )}
            {!streamBuf && !streamSearch && !streamCard && !streamClock && !streamDebug && (
              <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:18}}>
                <ModelBadge model={activeModel}/>
                <span style={{color:'var(--text-3)',fontSize:10}}>—</span>
                <span style={{fontFamily:'var(--font-d)',fontSize:12.5,fontStyle:'italic',color:'var(--text-3)'}}>
                  Atelier
                </span>
              </div>
            )}
            {/* Specific status lines — shown continuously until the first token */}
            {!streamBuf && !streamSearch && !streamCard && !streamClock && !streamDebug && (() => {
              const statusLabel = {
                thinking:   'Thinking…',
                searching:  'Searching the web…',
                computing:  'Computing…',
                recalling:  'Recalling…',
                stalled:    'Still working…',
              }[streamStatus] || 'Thinking…';
              return (
                <div style={{display:'flex',gap:20}}>
                  <div style={{width:1.5,background:'var(--bar)',borderRadius:1,flexShrink:0}}/>
                  <span style={{fontFamily:'var(--font-d)',fontSize:21,fontStyle:'italic',
                    color:'var(--text-3)',animation:'blink-thinking 1.1s ease-in-out infinite'}}>
                    {statusLabel}
                  </span>
                </div>
              );
            })()}
            {streamBuf && (
              streamBuf.includes(' ||| ')
                ? <BurstBlock text={streamBuf} model={activeModel} streaming={true}/>
                : <AiBlock    text={streamBuf} model={activeModel} streaming={true}/>
            )}
            {/* DebugTrace hidden */}
          </div>
        )}
        {error && (
          <div style={{maxWidth:'50%',width:'100%',margin:'0 auto',padding:'0 60px'}}>
            <p style={{fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',fontStyle:'italic'}}>{error}</p>
          </div>
        )}
      </div>

      {/* Composer */}
      <div style={{flexShrink:0,background:'var(--thread-bg)',borderTop:'1px solid var(--border-2)'}}>
        <div style={{maxWidth:'50%',width:'100%',margin:'0 auto',padding:'14px 60px 18px',position:'relative'}}>
          {paletteOpen && (
            <CommandPalette
              commands={filteredCommands}
              activeIndex={paletteIndex}
              onHover={setPaletteIndex}
              onRun={runCommand}
            />
          )}
          {/* Project scope chip */}
          {activeProject && (
            <div style={{ marginBottom:8, display:'flex', alignItems:'center', gap:6,
              padding:'3px 10px 3px 8px', borderRadius:8, background:'var(--accent-bg)',
              border:'1px solid var(--accent-bd)', width:'fit-content' }}>
              <Ico n="projects" size={10} color="var(--accent-tx)"/>
              <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--accent-tx)', letterSpacing:'.02em' }}>
                {activeProject.name}
              </span>
              <button onClick={onExitProject} title="Exit project" style={{
                width:14, height:14, borderRadius:'50%', display:'grid', placeItems:'center',
                color:'var(--text-3)', cursor:'pointer', marginLeft:2,
              }}>
                <Ico n="close" size={9} color="currentColor"/>
              </button>
            </div>
          )}
          <textarea className="ph" ref={composerRef}
            placeholder={noModel?'Type /setup to configure a model…':'Continue the conversation…'}
            rows={2} value={composer}
            onChange={e=>{ setComposer(e.target.value); setPaletteDismissed(false); setPaletteIndex(0); }}
            onKeyDown={handleKeyDown}
            disabled={streaming}
            style={{width:'100%',resize:'none',fontFamily:'var(--font-b)',fontSize:15,
              lineHeight:1.65,color:'var(--text)',opacity:streaming?0.5:1}}/>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',
            paddingTop:8,borderTop:'1px solid var(--border)'}}>

            {/* Left controls: model picker + web search toggle */}
            <div style={{display:'flex',alignItems:'center',gap:7}}>
              {/* Model pill — clickable picker */}
              <div style={{position:'relative'}}>
                <button onClick={() => setPickerOpen(o=>!o)} style={{
                  display:'flex',alignItems:'center',gap:5,padding:'3px 10px',
                  border:`1px solid ${pickerOpen?'var(--accent-bd)':'var(--border-2)'}`,
                  borderRadius:10,
                  background:pickerOpen?'var(--accent-bg)':'transparent',
                  cursor:'pointer',transition:'all var(--t)',
                }}>
                  <span style={{fontFamily:'var(--font-m)',fontSize:9.5,
                    color:noModel?'var(--text-3)':'var(--accent-tx)'}}>
                    {noModel?'◇ no model':`◆ ${modelShort}`}
                  </span>
                  <Ico n="chevron" size={9} color="var(--text-3)"
                    style={{transform:pickerOpen?'rotate(180deg)':'none',transition:'transform var(--t)'}}/>
                </button>
                {pickerOpen && (
                  <ModelPickerDropdown
                    current={activeModel}
                    onSelect={handleModelSelect}
                    onClose={()=>setPickerOpen(false)}
                  />
                )}
              </div>

              {/* Web search toggle */}
              <button onClick={()=>setWebSearch(v=>!v)}
                onDoubleClick={()=>onSearchSetup&&onSearchSetup()}
                title={webSearch?'Web search on — double-click to configure providers'
                                :'Web search off — double-click to configure providers'}
                style={{
                  display:'flex',alignItems:'center',gap:5,padding:'3px 10px',
                  border:`1px solid ${webSearch?'var(--accent-bd)':'var(--border-2)'}`,
                  borderRadius:10,
                  background:webSearch?'var(--accent-bg)':'transparent',
                  cursor:'pointer',transition:'all var(--t)',
                }}>
                <Ico n="globe" size={11} color={webSearch?'var(--accent-tx)':'var(--text-3)'}/>
                <span style={{fontFamily:'var(--font-m)',fontSize:9.5,
                  color:webSearch?'var(--accent-tx)':'var(--text-3)'}}>Web</span>
              </button>

              {/* Move conversation to / from a project */}
              <div style={{position:'relative'}}>
                <button onClick={()=>setMoveOpen(o=>!o)}
                  title={projectId?'Move this conversation to another project or the main chat'
                                  :'Add this conversation to a project'}
                  style={{
                    display:'flex',alignItems:'center',gap:5,padding:'3px 10px',
                    border:`1px solid ${moveOpen||projectId?'var(--accent-bd)':'var(--border-2)'}`,
                    borderRadius:10,
                    background:moveOpen||projectId?'var(--accent-bg)':'transparent',
                    cursor:'pointer',transition:'all var(--t)',
                  }}>
                  <Ico n="projects" size={11} color={projectId?'var(--accent-tx)':'var(--text-3)'}/>
                  <span style={{fontFamily:'var(--font-m)',fontSize:9.5,
                    color:projectId?'var(--accent-tx)':'var(--text-3)'}}>
                    {projectId?'Move':'Add to project'}
                  </span>
                </button>
                {moveOpen && (
                  <MoveMenu projectId={projectId}
                    onClose={()=>setMoveOpen(false)}
                    onMove={moveTo}/>
                )}
              </div>

            </div>

            {/* Send / Stop */}
            {streaming ? (
              <button onClick={()=>abortRef.current?.abort()} style={{
                width:30,height:30,borderRadius:15,background:'var(--accent-bg)',
                border:'1px solid var(--accent-bd)',display:'grid',placeItems:'center',cursor:'pointer'}}>
                <span style={{width:8,height:8,background:'var(--accent)',borderRadius:2,display:'block'}}/>
              </button>
            ) : (
              <button onClick={handleSend} style={{
                width:30,height:30,borderRadius:15,background:'var(--send-bg)',
                border:'1px solid var(--accent-bd)',display:'grid',placeItems:'center',cursor:'pointer'}}>
                <Ico n="send" size={12} color="var(--send-fg)"/>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

window.V2Chat = { ChatSurface };
