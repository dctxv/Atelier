/* ====== v2 Notes surface — live backend ====== */
const { useState, useEffect, useRef } = React;

function NotesSurface() {
  const [notes, setNotes]       = useState([]);
  const [active, setActive]     = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [dirty, setDirty]       = useState(false);
  const [saving, setSaving]     = useState(false);
  const [loading, setLoading]   = useState(true);
  const [filterQuery, setFilterQuery] = useState('');
  const [mode, setMode]         = useState('edit');     // 'edit' | 'preview'
  const [sel, setSel]           = useState(null);       // { start, end } of textarea selection
  const [cowriting, setCowriting] = useState(false);    // a cowrite stream is in flight
  const saveTimerRef = useRef(null);
  const textareaRef  = useRef(null);
  const cowriteAbort = useRef(null);

  useEffect(() => {
    fetch('/api/notes')
      .then(r => r.ok ? r.json() : { notes:[] })
      .then(d => {
        const ns = d.notes || [];
        setNotes(ns);
        setLoading(false);
        if (ns.length > 0) openNote(ns[0]);
      })
      .catch(() => setLoading(false));
  }, []);

  function openNote(note) {
    if (cowriting && cowriteAbort.current) cowriteAbort.current.abort();
    if (dirty) saveActive();
    setActive(note.id);
    setEditTitle(note.title || '');
    setEditContent(note.body || '');
    setDirty(false);
    setSel(null);
    setMode('edit');
  }

  function handleTitleChange(v) {
    setEditTitle(v);
    setDirty(true);
    scheduleSave();
  }

  function handleContentChange(v) {
    setEditContent(v);
    setDirty(true);
    scheduleSave();
  }

  // Track the live textarea selection so an action can act on it even after
  // the textarea loses focus (clicking a toolbar button blurs it).
  function handleSelect(e) {
    const ta = e.target;
    if (ta.selectionStart !== ta.selectionEnd) {
      setSel({ start: ta.selectionStart, end: ta.selectionEnd });
    } else {
      setSel(null);
    }
  }

  // Persist an explicit body (used by cowrite completion to avoid stale-closure
  // saves fighting the autosave debounce).
  async function persistBody(noteId, title, body) {
    try {
      await fetch(`/api/notes/${noteId}`, {
        method:'PUT',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ title, body }),
      });
      setNotes(prev => prev.map(n => n.id===noteId
        ? {...n, title, body, updated_at:new Date().toISOString()}
        : n));
    } catch(_) {}
  }

  // ── Co-writer: stream an AI transformation into the note body ──
  async function runCowrite(action) {
    if (cowriting || !sel || !active) return;
    const base = editContent;
    const selected = base.slice(sel.start, sel.end).trim();
    if (!selected) return;

    // 'continue' appends after the selection; 'rewrite'/'tighten' replace it.
    const insertStart = action === 'continue' ? sel.end : sel.start;
    const insertEnd   = sel.end;
    const before = base.slice(0, insertStart);
    const after  = base.slice(insertEnd);

    // Cancel any pending debounced save; the stream owns the body now.
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);

    const controller = new AbortController();
    cowriteAbort.current = controller;
    setCowriting(true);
    setMode('edit');

    let acc = '';
    const noteId = active;
    try {
      const resp = await fetch('/api/notes/cowrite', {
        method:'POST', signal:controller.signal,
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ action, text: base.slice(sel.start, sel.end) }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let streaming = true;
      while (streaming) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream:true });
        const lines = buf.split('\n');
        buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') { streaming = false; break; }
          try {
            const evt = JSON.parse(raw);
            if (evt.error) { streaming = false; break; }
            const delta = evt.choices?.[0]?.delta?.content;
            if (delta) {
              acc += delta;
              setEditContent(before + acc + after);
            }
          } catch(_) {}
        }
      }
    } catch(e) {
      // AbortError is expected on Stop — partial text is kept.
    } finally {
      setSel(null);
      setCowriting(false);
      cowriteAbort.current = null;
      if (acc) {
        // Tokens arrived — the streamed body is authoritative; persist it.
        const finalBody = before + acc + after;
        setEditContent(finalBody);
        setDirty(false);
        persistBody(noteId, editTitle, finalBody);
      }
      // No tokens (immediate error / abort before first delta): leave the
      // body and dirty flag exactly as they were before the cowrite.
    }
  }

  function stopCowrite() {
    if (cowriteAbort.current) cowriteAbort.current.abort();
  }

  function scheduleSave() {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => saveActive(), 1500);
  }

  async function saveActive() {
    if (!active || !dirty) return;
    setSaving(true);
    try {
      await fetch(`/api/notes/${active}`, {
        method:'PUT',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ title:editTitle, body:editContent }),
      });
      setNotes(prev => prev.map(n => n.id===active
        ? {...n, title:editTitle, body:editContent, updated_at:new Date().toISOString()}
        : n));
      setDirty(false);
    } catch(_) {}
    setSaving(false);
  }

  async function handleNewNote() {
    try {
      const resp = await fetch('/api/notes', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ title:'Untitled', body:'', note_type:'note' }),
      });
      if (!resp.ok) return;
      const n = await resp.json();
      setNotes(prev => [n, ...prev]);
      openNote(n);
    } catch(_) {}
  }

  async function handleDeleteNote(id) {
    try {
      await fetch(`/api/notes/${id}`, { method:'DELETE' });
      setNotes(prev => prev.filter(n => n.id !== id));
      if (active === id) {
        setActive(null);
        setEditTitle('');
        setEditContent('');
        setDirty(false);
      }
    } catch(_) {}
  }

  async function handleTogglePin(id) {
    const note = notes.find(n=>n.id===id);
    if (!note) return;
    try {
      await fetch(`/api/notes/${id}/pin`, { method:'POST' });
      setNotes(prev => prev.map(n => n.id===id ? {...n,pinned:!n.pinned} : n));
    } catch(_) {}
  }

  function relTime(iso) {
    if (!iso) return '';
    const diff = (Date.now() - new Date(iso)) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
    const d = new Date(iso);
    return d.toLocaleDateString(undefined,{month:'short',day:'numeric'});
  }

  const visibleNotes = notes.filter(n => {
    if (!filterQuery) return true;
    const q = filterQuery.toLowerCase();
    return (n.title||'').toLowerCase().includes(q) || (n.body||'').toLowerCase().includes(q);
  });

  // Sort: pinned first, then by updated_at
  const sortedNotes = [...visibleNotes].sort((a,b) => {
    if (a.pinned && !b.pinned) return -1;
    if (!a.pinned && b.pinned) return 1;
    return new Date(b.updated_at||0) - new Date(a.updated_at||0);
  });

  const activeNote = notes.find(n=>n.id===active);

  return (
    <div style={{ display:'flex', height:'100%', overflow:'hidden' }} className="surface-enter">

      {/* ── Note list ── */}
      <div style={{ width:240, flexShrink:0, background:'var(--panel-bg)',
        borderRight:'1px solid var(--border)', display:'flex', flexDirection:'column' }}>
        {/* header */}
        <div style={{ height:48, display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'0 16px', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
          <SectionLabel>Notes</SectionLabel>
          <button onClick={handleNewNote} style={{ width:24, height:24, borderRadius:6, display:'grid', placeItems:'center',
            background:'var(--accent-bg)', border:'1px solid var(--accent-bd)', cursor:'pointer' }}>
            <Ico n="plus" size={12} color="var(--accent-tx)"/>
          </button>
        </div>
        {/* search */}
        <div style={{ padding:'10px 12px', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 10px',
            border:'1px solid var(--border-2)', borderRadius:7, background:'var(--thread-bg)' }}>
            <Ico n="search" size={12} color="var(--text-3)"/>
            <input value={filterQuery} onChange={e=>setFilterQuery(e.target.value)}
              placeholder="Filter…"
              style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text)', flex:1 }}/>
          </div>
        </div>
        {/* list */}
        <div className="scroll" style={{ flex:1 }}>
          {loading && [1,2,3].map(i => (
            <div key={i} style={{ padding:'14px 16px', borderBottom:'1px solid var(--border)' }}>
              <div className="shimmer" style={{ height:10, width:'70%', marginBottom:8, borderRadius:3 }}/>
              <div className="shimmer" style={{ height:8, width:'90%', borderRadius:3 }}/>
            </div>
          ))}
          {!loading && sortedNotes.length === 0 && (
            <div style={{ padding:'20px 16px', textAlign:'center' }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>No notes yet</span>
            </div>
          )}
          {sortedNotes.map(n => {
            const on = n.id === active;
            return (
              <button key={n.id} onClick={() => openNote(n)} style={{
                width:'100%', textAlign:'left', padding:'12px 16px',
                background: on ? 'var(--accent-bg)' : 'transparent',
                borderLeft:`2px solid ${on ? 'var(--accent)' : 'transparent'}`,
                borderBottom:'1px solid var(--border)',
                cursor:'pointer', transition:'background var(--t)', display:'block',
              }}>
                <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:4 }}>
                  {n.pinned && <Ico n="pin" size={10} color="var(--accent-tx)"/>}
                  <span style={{ fontFamily:'var(--font-b)', fontSize:13.5, fontStyle:'italic',
                    color: on ? 'var(--text)' : 'var(--text-q)', flex:1, lineHeight:1.25,
                    overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{n.title || 'Untitled'}</span>
                  <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)', flexShrink:0 }}>{relTime(n.updated_at)}</span>
                </div>
                <p style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)',
                  lineHeight:1.45, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>
                  {(n.body||'').slice(0,80) || 'Empty note'}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Editor ── */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', position:'relative' }}>
        {!active ? (
          <EmptyState icon="notes" title="Notes" subtitle="select or create a note"/>
        ) : (
          <>
            {/* toolbar */}
            <div style={{ height:44, display:'flex', alignItems:'center', gap:6,
              padding:'0 32px', borderBottom:'1px solid var(--border)', flexShrink:0,
              justifyContent:'space-between' }}>
              <div style={{ display:'flex', gap:4 }}>
                {activeNote?.pinned !== undefined && (
                  <button onClick={() => handleTogglePin(active)} style={{
                    fontFamily:'var(--font-m)', fontSize:11, color: activeNote?.pinned ? 'var(--accent-tx)' : 'var(--text-3)',
                    padding:'3px 8px', borderRadius:5,
                    border:`1px solid ${activeNote?.pinned ? 'var(--accent-bd)' : 'transparent'}`,
                    background: activeNote?.pinned ? 'var(--accent-bg)' : 'none', cursor:'pointer',
                  }}>pin</button>
                )}
              </div>
              <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                {/* Edit / Preview toggle */}
                <div style={{ display:'flex', border:'1px solid var(--border-2)', borderRadius:6, overflow:'hidden' }}>
                  {['edit','preview'].map(m => (
                    <button key={m} onClick={() => setMode(m)} style={{
                      fontFamily:'var(--font-m)', fontSize:10, padding:'3px 9px',
                      color: mode===m ? 'var(--accent-tx)' : 'var(--text-3)',
                      background: mode===m ? 'var(--accent-bg)' : 'transparent',
                      cursor:'pointer', letterSpacing:'.03em',
                    }}>{m}</button>
                  ))}
                </div>
                {saving && <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>saving…</span>}
                {dirty && !saving && <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>unsaved</span>}
                {!dirty && !saving && <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>saved</span>}
                <button onClick={() => handleDeleteNote(active)} style={{
                  width:24, height:24, borderRadius:5, display:'grid', placeItems:'center',
                  color:'var(--text-3)', border:'1px solid transparent',
                }}>
                  <Ico n="trash" size={12} color="currentColor"/>
                </button>
              </div>
            </div>

            {/* ── Co-writer floating toolbar ── */}
            {mode==='edit' && (sel || cowriting) && (
              <div style={{
                position:'absolute', top:56, left:'50%', transform:'translateX(-50%)',
                zIndex:5, display:'flex', alignItems:'center', gap:4,
                padding:'4px 5px', background:'var(--panel-bg)',
                border:'1px solid var(--border-2)', borderRadius:8,
              }}>
                {cowriting ? (
                  <button onClick={stopCowrite} style={{
                    fontFamily:'var(--font-m)', fontSize:11, color:'var(--accent-tx)',
                    padding:'4px 12px', borderRadius:5, cursor:'pointer',
                    background:'var(--accent-bg)', border:'1px solid var(--accent-bd)',
                    display:'flex', alignItems:'center', gap:6,
                  }}>
                    <span style={{ width:7, height:7, borderRadius:1, background:'var(--accent-tx)', display:'inline-block' }}/>
                    Stop
                  </button>
                ) : (
                  [['continue','Continue'],['rewrite','Rewrite'],['tighten','Tighten']].map(([act,label]) => (
                    <button key={act} onClick={() => runCowrite(act)} style={{
                      fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-q)',
                      padding:'4px 11px', borderRadius:5, cursor:'pointer',
                      background:'transparent', border:'1px solid transparent',
                      transition:'background var(--t), color var(--t)',
                    }}
                    onMouseEnter={e=>{ e.currentTarget.style.background='var(--accent-bg)'; e.currentTarget.style.color='var(--accent-tx)'; }}
                    onMouseLeave={e=>{ e.currentTarget.style.background='transparent'; e.currentTarget.style.color='var(--text-q)'; }}
                    >{label}</button>
                  ))
                )}
              </div>
            )}

            {/* document */}
            <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>
              <div style={{ maxWidth:680, margin:'0 auto', padding:'40px 56px 60px' }}>
                {/* title */}
                <input
                  value={editTitle}
                  onChange={e=>handleTitleChange(e.target.value)}
                  onBlur={saveActive}
                  placeholder="Title"
                  readOnly={cowriting}
                  style={{
                    width:'100%', fontFamily:'var(--font-d)', fontSize:36, fontWeight:500,
                    color:'var(--text)', lineHeight:1.1, letterSpacing:'.01em', marginBottom:24,
                    display:'block',
                  }}
                />
                {/* body — edit or rendered preview */}
                {mode==='preview' ? (
                  <div style={{ minHeight:400 }}>
                    {(parseBlocks(editContent || '')).map((b,i) =>
                      renderBlock(b, i, false, 15.5, 1.82, false))}
                    {!editContent.trim() && (
                      <span style={{ fontFamily:'var(--font-b)', fontSize:15.5, fontStyle:'italic',
                        color:'var(--text-3)' }}>Nothing to preview yet.</span>
                    )}
                  </div>
                ) : (
                  <textarea
                    ref={textareaRef}
                    value={editContent}
                    onChange={e=>handleContentChange(e.target.value)}
                    onSelect={handleSelect}
                    onBlur={saveActive}
                    placeholder="Begin writing…"
                    readOnly={cowriting}
                    style={{
                      width:'100%', fontFamily:'var(--font-b)', fontSize:15.5, lineHeight:1.82,
                      color:'var(--text)', resize:'none', minHeight:400,
                      display:'block', opacity: cowriting ? 0.7 : 1,
                    }}
                    rows={20}
                  />
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

window.V2Notes = { NotesSurface };
