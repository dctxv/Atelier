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
  const saveTimerRef = useRef(null);

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
    if (dirty) saveActive();
    setActive(note.id);
    setEditTitle(note.title || '');
    setEditContent(note.body || '');
    setDirty(false);
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
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
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

            {/* document */}
            <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>
              <div style={{ maxWidth:680, margin:'0 auto', padding:'40px 56px 60px' }}>
                {/* title */}
                <input
                  value={editTitle}
                  onChange={e=>handleTitleChange(e.target.value)}
                  onBlur={saveActive}
                  placeholder="Title"
                  style={{
                    width:'100%', fontFamily:'var(--font-d)', fontSize:36, fontWeight:500,
                    color:'var(--text)', lineHeight:1.1, letterSpacing:'.01em', marginBottom:24,
                    display:'block',
                  }}
                />
                {/* body */}
                <textarea
                  value={editContent}
                  onChange={e=>handleContentChange(e.target.value)}
                  onBlur={saveActive}
                  placeholder="Begin writing…"
                  style={{
                    width:'100%', fontFamily:'var(--font-b)', fontSize:15.5, lineHeight:1.82,
                    color:'var(--text)', resize:'none', minHeight:400,
                    display:'block',
                  }}
                  rows={20}
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

window.V2Notes = { NotesSurface };
