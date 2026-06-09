/* ====== Projects surface — scoped AI workspaces ====== */
const { useState, useEffect, useRef, useCallback } = React;
const { ChatSurface } = window.V2Chat;

/* ── Relative time helper ── */
function relTime(ts) {
  if (!ts) return '';
  const diff = Date.now() / 1000 - ts;
  if (diff < 60)    return 'just now';
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

/* ── Project list (left rail) ── */
function ProjectList({ projects, activeId, creating, loading, onSelect, onNew }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      {/* Header */}
      <div style={{
        padding:'16px 16px 12px', borderBottom:'1px solid var(--border)',
        display:'flex', alignItems:'center', justifyContent:'space-between', flexShrink:0,
      }}>
        <span style={{ fontFamily:'var(--font-b)', fontSize:13.5, fontStyle:'italic', color:'var(--text)' }}>
          Projects
        </span>
        <button onClick={onNew} title="New project" style={{
          width:26, height:26, borderRadius:7, display:'grid', placeItems:'center',
          border:`1px solid ${creating ? 'var(--accent-bd)' : 'var(--border-2)'}`,
          background: creating ? 'var(--accent-bg)' : 'transparent',
          color: creating ? 'var(--accent-tx)' : 'var(--text-3)', cursor:'pointer',
        }}>
          <Ico n="plus" size={12} color="currentColor"/>
        </button>
      </div>

      {/* List body */}
      <div className="scroll" style={{ flex:1 }}>
        {loading && (
          <div style={{ padding:24, textAlign:'center' }}><Pulse size={7}/></div>
        )}
        {!loading && projects.length === 0 && (
          <div style={{ padding:'28px 14px', textAlign:'center', opacity:.45 }}>
            <div style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)' }}>
              No projects yet
            </div>
          </div>
        )}
        {projects.map(p => {
          const on = p.id === activeId && !creating;
          return (
            <button key={p.id} onClick={() => onSelect(p.id)} style={{
              width:'100%', textAlign:'left', display:'block', padding:'10px 14px',
              background: on ? 'var(--accent-bg)' : 'transparent',
              borderLeft: `2px solid ${on ? 'var(--accent)' : 'transparent'}`,
              borderBottom:'1px solid var(--border)', cursor:'pointer',
              transition:'background var(--t), border-color var(--t)',
            }}>
              <div style={{ fontFamily:'var(--font-b)', fontSize:13, fontStyle:'italic',
                color: on ? 'var(--text)' : 'var(--text-q)',
                overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                {p.name}
              </div>
              {p.description && (
                <div style={{ marginTop:2, fontFamily:'var(--font-b)', fontSize:11,
                  color:'var(--text-3)', lineHeight:1.4,
                  overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                  {p.description}
                </div>
              )}
              <div style={{ display:'flex', gap:8, marginTop:3,
                fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>
                <span>{p.file_count || 0} file{p.file_count !== 1 ? 's' : ''}</span>
                {p.updated_at && <>
                  <span>·</span>
                  <span>{relTime(p.updated_at)}</span>
                </>}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Project memory atom row ── */
function ProjectAtomRow({ atom, onPromote }) {
  return (
    <div style={{ display:'flex', alignItems:'flex-start', gap:12, padding:'10px 0',
      borderBottom:'1px solid var(--border)' }}>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontFamily:'var(--font-b)', fontSize:13.5, fontStyle:'italic',
          color:'var(--text)', lineHeight:1.5 }}>{atom.text}</div>
        <div style={{ display:'flex', gap:10, marginTop:3,
          fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>
          <span style={{ textTransform:'uppercase', letterSpacing:'.06em' }}>{atom.type || 'fact'}</span>
          {atom.salience != null && (
            <span>salience {typeof atom.salience === 'number' ? atom.salience.toFixed(1) : atom.salience}</span>
          )}
        </div>
      </div>
      <button onClick={() => onPromote(atom.id)} title="Promote to global memory" style={{
        flexShrink:0, fontFamily:'var(--font-m)', fontSize:9.5, padding:'3px 10px',
        borderRadius:6, border:'1px solid var(--border-2)', color:'var(--text-3)',
        cursor:'pointer', whiteSpace:'nowrap',
      }}>
        promote global ↑
      </button>
    </div>
  );
}

/* ── In-area create card (replaces the cramped rail input) ── */
function CreateProjectCard({ onCancel, onCreated }) {
  const [name, setName]                 = useState('');
  const [description, setDescription]   = useState('');
  const [instructions, setInstructions] = useState('');
  const [pending, setPending]           = useState([]);  // File[]
  const [busy, setBusy]                 = useState(false);
  const [err, setErr]                   = useState(null);
  const nameRef = useRef(null);
  useEffect(() => { setTimeout(() => nameRef.current?.focus(), 40); }, []);

  async function submit() {
    if (!name.trim()) { setErr('Give the project a name.'); return; }
    setBusy(true); setErr(null);
    try {
      const r = await fetch('/api/projects', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || undefined,
          instructions: instructions.trim() || undefined,
        }),
      });
      const d = await r.json();
      const proj = d.project;
      if (!proj) throw new Error('create failed');
      for (const f of pending) {
        const form = new FormData(); form.append('file', f);
        try { await fetch(`/api/projects/${proj.id}/documents/upload`, { method:'POST', body:form }); } catch {}
      }
      onCreated(proj, pending.length > 0);
    } catch {
      setErr('Could not create the project — try again.');
    } finally { setBusy(false); }
  }

  const labelStyle = { fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)',
    letterSpacing:'.1em', textTransform:'uppercase', display:'block', marginBottom:6 };

  return (
    <div className="scroll" style={{ flex:1, display:'flex', flexDirection:'column',
      alignItems:'center', justifyContent:'flex-start', padding:'56px 32px' }}>
      <div style={{ width:'100%', maxWidth:520 }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:24 }}>
          <Ico n="projects" size={16} color="var(--accent-tx)"/>
          <span style={{ fontFamily:'var(--font-d)', fontSize:26, fontStyle:'italic', color:'var(--text)' }}>
            New project
          </span>
        </div>

        <div style={{ marginBottom:16 }}>
          <label style={labelStyle}>Name</label>
          <input ref={nameRef} value={name} onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onCancel(); }}
            placeholder="Acme Rebrand"
            style={{ width:'100%', padding:'11px 14px', fontFamily:'var(--font-b)', fontSize:15,
              fontStyle:'italic', color:'var(--text)', background:'var(--surface)',
              border:'1px solid var(--border-2)', borderRadius:9 }}/>
        </div>

        <div style={{ marginBottom:16 }}>
          <label style={labelStyle}>Description <span style={{ textTransform:'none', letterSpacing:0 }}>· one line, the only thing the main chat can see</span></label>
          <input value={description} onChange={e => setDescription(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onCancel(); }}
            placeholder="Logo, brand voice, and naming work."
            style={{ width:'100%', padding:'10px 14px', fontFamily:'var(--font-b)', fontSize:13.5,
              color:'var(--text)', background:'var(--surface)',
              border:'1px solid var(--border-2)', borderRadius:9 }}/>
        </div>

        <div style={{ marginBottom:16 }}>
          <label style={labelStyle}>Instructions <span style={{ textTransform:'none', letterSpacing:0 }}>· private system prompt for chats in this project</span></label>
          <textarea value={instructions} onChange={e => setInstructions(e.target.value)}
            placeholder="e.g. Use metric units, cite uploaded standards by section number…"
            rows={4}
            style={{ width:'100%', resize:'vertical', minHeight:90, padding:'12px 14px',
              fontFamily:'var(--font-b)', fontSize:13.5, color:'var(--text)', lineHeight:1.6,
              background:'var(--surface)', border:'1px solid var(--border-2)', borderRadius:9 }}/>
        </div>

        <div style={{ marginBottom:20 }}>
          <label style={labelStyle}>Files <span style={{ textTransform:'none', letterSpacing:0 }}>· optional, can add more later</span></label>
          <DropZone onFiles={files => setPending(prev => [...prev, ...files])}/>
          {pending.length > 0 && (
            <div style={{ marginTop:10, display:'flex', flexWrap:'wrap', gap:6 }}>
              {pending.map((f, i) => (
                <span key={i} style={{ fontFamily:'var(--font-m)', fontSize:10.5, padding:'3px 10px',
                  borderRadius:20, background:'var(--surface)', border:'1px solid var(--border-2)',
                  color:'var(--text-3)', display:'flex', alignItems:'center', gap:6 }}>
                  📄 {f.name}
                  <button onClick={() => setPending(prev => prev.filter((_, j) => j !== i))}
                    style={{ color:'var(--text-3)', cursor:'pointer', display:'grid', placeItems:'center' }}>
                    <Ico n="close" size={9} color="currentColor"/>
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {err && <div style={{ marginBottom:12, fontFamily:'var(--font-m)', fontSize:12, color:'#a94442' }}>{err}</div>}

        <div style={{ display:'flex', gap:10, justifyContent:'flex-end' }}>
          <button onClick={onCancel} style={{
            fontFamily:'var(--font-m)', fontSize:11.5, padding:'10px 20px', borderRadius:9,
            border:'1px solid var(--border-2)', color:'var(--text-3)', cursor:'pointer',
            background:'transparent', letterSpacing:'.04em',
          }}>Cancel</button>
          <button onClick={submit} disabled={busy} style={{
            fontFamily:'var(--font-b)', fontSize:13.5, fontStyle:'italic', padding:'10px 26px',
            borderRadius:9, border:'1px solid var(--accent-bd)', background:'var(--send-bg)',
            color:'var(--send-fg)', cursor: busy ? 'default' : 'pointer', opacity: busy ? .7 : 1,
          }}>{busy ? 'Creating…' : 'Create project'}</button>
        </div>
      </div>
    </div>
  );
}

/* ── Header actions menu (rename / delete) ── */
function HeaderMenu({ onRename, onDelete }) {
  const [open, setOpen]       = useState(false);
  const [confirm, setConfirm] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const fn = e => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setConfirm(false); } };
    document.addEventListener('mousedown', fn);
    return () => document.removeEventListener('mousedown', fn);
  }, []);

  return (
    <div ref={ref} style={{ position:'relative', flexShrink:0 }}>
      <button onClick={() => setOpen(o => !o)} title="Project actions" style={{
        width:28, height:28, borderRadius:7, display:'grid', placeItems:'center',
        border:'1px solid var(--border-2)', color:'var(--text-3)', cursor:'pointer',
        background: open ? 'var(--accent-bg)' : 'transparent',
      }}>
        <Ico n="more" size={14} color="currentColor"/>
      </button>
      {open && (
        <div style={{ position:'absolute', top:'calc(100% + 6px)', right:0, width:180, zIndex:60,
          background:'var(--surface)', border:'1px solid var(--border-2)', borderRadius:10,
          overflow:'hidden', boxShadow:'0 8px 32px rgba(0,0,0,.2)' }}>
          {!confirm ? (
            <>
              <button onClick={() => { setOpen(false); onRename(); }} style={menuItem()}>
                <Ico n="notes" size={12} color="var(--text-3)"/> Rename
              </button>
              <button onClick={() => setConfirm(true)} style={{ ...menuItem(), color:'#B5562E' }}>
                <Ico n="trash" size={12} color="#B5562E"/> Delete project
              </button>
            </>
          ) : (
            <div style={{ padding:'12px 14px' }}>
              <div style={{ fontFamily:'var(--font-b)', fontSize:12.5, color:'var(--text)', marginBottom:4 }}>
                Delete this project?
              </div>
              <div style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)', lineHeight:1.5, marginBottom:10 }}>
                Conversations and project memory are removed. Files are kept but unassigned.
              </div>
              <div style={{ display:'flex', gap:6 }}>
                <button onClick={() => { setOpen(false); setConfirm(false); onDelete(); }} style={{
                  flex:1, fontFamily:'var(--font-m)', fontSize:10, padding:'5px 0', borderRadius:6,
                  background:'#B5562E', color:'#FFF4E8', cursor:'pointer', letterSpacing:'.04em' }}>
                  Delete
                </button>
                <button onClick={() => setConfirm(false)} style={{
                  flex:1, fontFamily:'var(--font-m)', fontSize:10, padding:'5px 0', borderRadius:6,
                  border:'1px solid var(--border-2)', color:'var(--text-3)', cursor:'pointer' }}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
function menuItem() {
  return { width:'100%', textAlign:'left', display:'flex', alignItems:'center', gap:9,
    padding:'10px 14px', fontFamily:'var(--font-b)', fontSize:13, fontStyle:'italic',
    color:'var(--text-q)', cursor:'pointer', borderBottom:'1px solid var(--border)',
    background:'transparent' };
}

/* ── Project detail (right pane) ── */
function ProjectDetail({ project, initialTab, onUpdated, onDeleted, chat, openSessionId, onConsumeOpen }) {
  const [tab,          setTab]          = useState(initialTab || 'conversations');
  const [instructions, setInstructions] = useState(project.instructions || '');
  const [description,  setDescription]  = useState(project.description || '');
  const [docs,         setDocs]         = useState([]);
  const [atoms,        setAtoms]        = useState([]);
  const [docsLoaded,   setDocsLoaded]   = useState(false);
  const [uploading,    setUploading]    = useState(false);
  const [err,          setErr]          = useState(null);
  const [renaming,     setRenaming]     = useState(false);
  const [nameDraft,    setNameDraft]    = useState(project.name);
  const instrTimer = useRef(null);
  const descTimer  = useRef(null);

  /* Load documents */
  const loadDocs = useCallback(async () => {
    try {
      const r = await fetch(`/api/projects/${project.id}/documents`);
      const d = await r.json();
      setDocs(d.documents || []);
      setDocsLoaded(true);
    } catch {}
  }, [project.id]);

  /* Poll while processing */
  useEffect(() => {
    loadDocs();
    const t = setInterval(() => {
      setDocs(prev => {
        const busy = prev.some(d => ['queued','extracting','embedding'].includes(d.status));
        if (busy) { loadDocs(); }
        return prev;
      });
    }, 3000);
    return () => clearInterval(t);
  }, [project.id, loadDocs]);

  /* Load project memory when its tab opens */
  const loadAtoms = useCallback(async () => {
    try {
      const r = await fetch(`/api/projects/${project.id}/memory`);
      const d = await r.json();
      setAtoms(d.atoms || []);
    } catch {}
  }, [project.id]);
  useEffect(() => { if (tab === 'memory') loadAtoms(); }, [tab, loadAtoms]);

  /* Debounced PATCH helper */
  function patchProject(body) {
    return fetch(`/api/projects/${project.id}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body),
    }).then(r => r.json()).then(d => { if (d.project) onUpdated(d.project); }).catch(()=>{});
  }

  function handleInstructionsChange(val) {
    setInstructions(val);
    clearTimeout(instrTimer.current);
    instrTimer.current = setTimeout(() => patchProject({ instructions: val }), 600);
  }
  function handleDescriptionChange(val) {
    setDescription(val);
    clearTimeout(descTimer.current);
    descTimer.current = setTimeout(() => patchProject({ description: val }), 600);
  }

  /* Rename */
  function commitRename() {
    const v = nameDraft.trim();
    setRenaming(false);
    if (v && v !== project.name) patchProject({ name: v });
    else setNameDraft(project.name);
  }

  /* Delete */
  async function handleDelete() {
    try {
      await fetch(`/api/projects/${project.id}`, { method:'DELETE' });
      onDeleted(project.id);
    } catch {}
  }

  /* File upload */
  async function handleUpload(files) {
    setErr(null); setUploading(true);
    for (const f of files) {
      const form = new FormData(); form.append('file', f);
      try {
        const r = await fetch(`/api/projects/${project.id}/documents/upload`, { method:'POST', body:form });
        if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
      } catch (e) { setErr(e.message); }
    }
    setUploading(false);
    await loadDocs();
  }
  async function handleDeleteDoc(docId) {
    try { await fetch(`/api/projects/${project.id}/documents/${docId}`, { method:'DELETE' }); await loadDocs(); }
    catch (e) { setErr(e.message); }
  }
  async function handlePromoteAtom(atomId) {
    try { await fetch(`/api/memory/${atomId}/promote`, { method:'PATCH' }); setAtoms(prev => prev.filter(a => a.id !== atomId)); }
    catch {}
  }

  const activeCount = docs.filter(d => ['queued','extracting','embedding'].includes(d.status)).length;
  const readyCount  = docs.filter(d => d.status === 'ready').length;

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>

      {/* Project header */}
      <div style={{
        height:52, flexShrink:0, background:'var(--nav-bg)',
        borderBottom:'1px solid var(--border)',
        display:'flex', alignItems:'center', padding:'0 20px 0 28px',
        justifyContent:'space-between', gap:12,
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, minWidth:0 }}>
          <Ico n="projects" size={14} color="var(--accent-tx)"/>
          {renaming ? (
            <input autoFocus value={nameDraft} onChange={e => setNameDraft(e.target.value)}
              onBlur={commitRename}
              onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') { setRenaming(false); setNameDraft(project.name); } }}
              style={{ fontFamily:'var(--font-b)', fontSize:14.5, fontStyle:'italic', color:'var(--text)',
                background:'var(--surface)', border:'1px solid var(--accent-bd)', borderRadius:6,
                padding:'3px 8px', minWidth:240 }}/>
          ) : (
            <span style={{ fontFamily:'var(--font-b)', fontSize:14.5, fontStyle:'italic',
              color:'var(--text)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              {project.name}
            </span>
          )}
          {readyCount > 0 && (
            <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)',
              letterSpacing:'.06em', flexShrink:0 }}>
              {readyCount} file{readyCount !== 1 ? 's' : ''} ready
            </span>
          )}
        </div>
        <HeaderMenu onRename={() => { setNameDraft(project.name); setRenaming(true); }} onDelete={handleDelete}/>
      </div>

      {/* Tab nav */}
      <TabNav
        tabs={[
          { id:'conversations', label:'Conversations' },
          { id:'files',         label:'Files', live: activeCount > 0 },
          { id:'instructions',  label:'Instructions' },
          { id:'memory',        label:'Memory' },
          { id:'about',         label:'About' },
        ]}
        active={tab}
        onSelect={setTab}
      />

      {/* ── Conversations tab: embedded, project-scoped chat ── */}
      {tab === 'conversations' && (
        <div style={{ flex:1, minHeight:0, display:'flex', flexDirection:'column' }}>
          <ChatSurface key={project.id} {...chat} projectId={project.id}
            openSessionId={openSessionId} onConsumeOpen={onConsumeOpen}/>
        </div>
      )}

      {/* ── Other tabs: padded scroll area ── */}
      {tab !== 'conversations' && (
        <div className="scroll" style={{ flex:1, padding:'32px 56px' }}>
          <div style={{ maxWidth:780 }}>

            {tab === 'files' && (
              <div>
                <div style={{ marginBottom:24 }}>
                  <DropZone onFiles={handleUpload}/>
                  {uploading && (
                    <div style={{ marginTop:10, display:'flex', alignItems:'center', gap:8,
                      fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)' }}>
                      <Pulse size={6}/> Uploading…
                    </div>
                  )}
                  {err && <div style={{ marginTop:8, fontFamily:'var(--font-m)', fontSize:12, color:'#a94442' }}>{err}</div>}
                </div>

                {docs.length > 0 && (
                  <div style={{ display:'flex', gap:20, marginBottom:16, fontFamily:'var(--font-m)',
                    fontSize:11, color:'var(--text-3)', letterSpacing:'.06em', textTransform:'uppercase' }}>
                    <span>{docs.length} file{docs.length !== 1 ? 's' : ''}</span>
                    {readyCount > 0 && <span>{readyCount} ready · searchable</span>}
                    {activeCount > 0 && (
                      <span style={{ display:'flex', alignItems:'center', gap:5 }}>
                        <Pulse size={5}/>{activeCount} processing
                      </span>
                    )}
                  </div>
                )}

                {!docsLoaded ? (
                  <div style={{ display:'flex', alignItems:'center', gap:8,
                    fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)' }}>
                    <Pulse size={6}/> Loading…
                  </div>
                ) : docs.length === 0 ? (
                  <div style={{ textAlign:'center', padding:'48px 0', opacity:.4 }}>
                    <Ico n="notes" size={26} color="var(--text-3)"/>
                    <div style={{ marginTop:12, fontFamily:'var(--font-b)', fontSize:15,
                      fontStyle:'italic', color:'var(--text-2)' }}>No files yet</div>
                    <div style={{ marginTop:5, fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', lineHeight:1.6 }}>
                      Upload PDFs, docs, or text files above — they'll be chunked, embedded,
                      and referenced by the AI when you chat in this project.
                    </div>
                  </div>
                ) : (
                  docs.map(doc => <DocRow key={doc.id} doc={doc} onDelete={handleDeleteDoc}/>)
                )}
              </div>
            )}

            {tab === 'instructions' && (
              <div>
                <div style={{ marginBottom:18 }}>
                  <div style={{ fontFamily:'var(--font-b)', fontSize:16, fontStyle:'italic',
                    color:'var(--text)', marginBottom:7 }}>
                    Project instructions
                  </div>
                  <div style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', lineHeight:1.65 }}>
                    This text becomes the system prompt for every chat inside this project.
                    Use it to set context, preferred tone, citation format, or domain constraints.
                    It stays private to the project — the main chat never sees it.
                  </div>
                </div>
                <textarea
                  className="ph"
                  value={instructions}
                  onChange={e => handleInstructionsChange(e.target.value)}
                  placeholder="e.g. You are helping me write a structural engineering report. Use metric units, cite uploaded standards by section number, and flag any load assumption I haven't stated."
                  rows={10}
                  style={{
                    width:'100%', resize:'vertical', minHeight:150,
                    fontFamily:'var(--font-b)', fontSize:14, fontStyle:'italic',
                    color:'var(--text)', lineHeight:1.7,
                    background:'var(--surface)', border:'1px solid var(--border-2)',
                    borderRadius:10, padding:'14px 18px',
                  }}
                />
                <div style={{ marginTop:8, fontFamily:'var(--font-m)', fontSize:10.5,
                  color:'var(--text-3)', fontStyle:'italic' }}>
                  Auto-saved as you type
                </div>
              </div>
            )}

            {tab === 'memory' && (
              <div>
                <div style={{ marginBottom:18 }}>
                  <div style={{ fontFamily:'var(--font-b)', fontSize:16, fontStyle:'italic',
                    color:'var(--text)', marginBottom:7 }}>
                    Project memory
                  </div>
                  <div style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', lineHeight:1.65 }}>
                    Facts learned from chats in this project. They only surface here — not in global chats.
                    Hit <em>promote global</em> to make an atom available everywhere.
                  </div>
                </div>

                {atoms.length === 0 ? (
                  <div style={{ textAlign:'center', padding:'48px 0', opacity:.4 }}>
                    <Ico n="memory" size={26} color="var(--text-3)"/>
                    <div style={{ marginTop:12, fontFamily:'var(--font-b)', fontSize:15,
                      fontStyle:'italic', color:'var(--text-2)' }}>No project memory yet</div>
                    <div style={{ marginTop:5, fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)' }}>
                      Facts from project chats will appear here after a few conversations
                    </div>
                  </div>
                ) : (
                  <div>
                    {atoms.map(atom => (
                      <ProjectAtomRow key={atom.id} atom={atom} onPromote={handlePromoteAtom}/>
                    ))}
                  </div>
                )}
              </div>
            )}

            {tab === 'about' && (
              <div>
                <div style={{ marginBottom:18 }}>
                  <div style={{ fontFamily:'var(--font-b)', fontSize:16, fontStyle:'italic',
                    color:'var(--text)', marginBottom:7 }}>
                    Description
                  </div>
                  <div style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', lineHeight:1.65 }}>
                    A short, human-facing blurb. This is the <em>only</em> thing the main chat can see about
                    this project — it can never read your files, instructions, or project memory.
                  </div>
                </div>
                <input
                  value={description}
                  onChange={e => handleDescriptionChange(e.target.value)}
                  placeholder="Logo, brand voice, and naming work."
                  style={{ width:'100%', padding:'12px 16px', fontFamily:'var(--font-b)', fontSize:14,
                    color:'var(--text)', background:'var(--surface)',
                    border:'1px solid var(--border-2)', borderRadius:10 }}/>
                <div style={{ marginTop:8, fontFamily:'var(--font-m)', fontSize:10.5,
                  color:'var(--text-3)', fontStyle:'italic' }}>
                  Auto-saved as you type
                </div>

                <div style={{ marginTop:32, display:'flex', gap:32, flexWrap:'wrap' }}>
                  <Stat label="Files" value={`${readyCount} ready · ${docs.length} total`}/>
                  <Stat label="Created" value={relTime(project.created_at)}/>
                  <Stat label="Updated" value={relTime(project.updated_at)}/>
                </div>
              </div>
            )}

          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
        letterSpacing:'.1em', textTransform:'uppercase', marginBottom:5 }}>{label}</div>
      <div style={{ fontFamily:'var(--font-b)', fontSize:14, fontStyle:'italic', color:'var(--text)' }}>{value}</div>
    </div>
  );
}

/* ── Empty state (centered in the work area) ── */
function ProjectsEmptyState({ onCreate }) {
  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center',
      justifyContent:'center', gap:18, padding:40 }}>
      <div style={{ width:60, height:60, borderRadius:15, background:'var(--accent-bg)',
        border:'1px solid var(--accent-bd)', display:'grid', placeItems:'center' }}>
        <Ico n="projects" size={26} color="var(--accent-tx)"/>
      </div>
      <div style={{ textAlign:'center', maxWidth:360 }}>
        <div style={{ fontFamily:'var(--font-d)', fontSize:24, fontStyle:'italic',
          color:'var(--text)', marginBottom:8 }}>
          A workspace for each project
        </div>
        <div style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', lineHeight:1.7 }}>
          Group conversations, files, and instructions together. Everything inside a project
          stays scoped to it — the main chat never sees in.
        </div>
      </div>
      <button onClick={onCreate} style={{
        fontFamily:'var(--font-b)', fontSize:13.5, fontStyle:'italic', padding:'10px 24px',
        borderRadius:9, border:'1px solid var(--accent-bd)', background:'var(--send-bg)',
        color:'var(--send-fg)', cursor:'pointer', marginTop:4,
      }}>
        New project
      </button>
    </div>
  );
}

/* ── Main surface ── */
function ProjectsSurface({ onSetup, onSearchSetup, onWeatherSetup, onStockSetup,
                           onToggleTheme, onOpenSettings, onNav, onPlay,
                           onMoved, target, onConsumeTarget }) {
  const [projects,      setProjects]      = useState([]);
  const [activeId,      setActiveId]      = useState(null);
  const [loading,       setLoading]       = useState(true);
  const [creating,      setCreating]      = useState(false);
  const [pendingTab,    setPendingTab]    = useState('conversations');
  const [openSessionId, setOpenSessionId] = useState(null);

  // Handlers forwarded to the embedded chat so it has full parity with the main one.
  const chat = { onSetup, onSearchSetup, onWeatherSetup, onStockSetup,
                 onToggleTheme, onOpenSettings, onNav, onPlay, onMoved };

  // A conversation moved into a project: open that project + that chat.
  useEffect(() => {
    if (target && target.projectId) {
      setCreating(false);
      setActiveId(target.projectId);
      setPendingTab('conversations');
      setOpenSessionId(target.sessionId || null);
      if (onConsumeTarget) onConsumeTarget();
    }
  }, [target]);

  const loadProjects = useCallback(async () => {
    try {
      const r = await fetch('/api/projects');
      const d = await r.json();
      setProjects(d.projects || []);
    } catch {}
    setLoading(false);
  }, []);
  useEffect(() => { loadProjects(); }, [loadProjects]);

  function handleCreated(proj, hadFiles) {
    setProjects(prev => [proj, ...prev]);
    setPendingTab(hadFiles ? 'files' : 'conversations');
    setActiveId(proj.id);
    setCreating(false);
  }

  function handleUpdated(updated) {
    setProjects(prev => prev.map(p => p.id === updated.id ? { ...p, ...updated } : p));
  }

  function handleDeleted(id) {
    setProjects(prev => prev.filter(p => p.id !== id));
    if (activeId === id) setActiveId(null);
  }

  const activeProject = projects.find(p => p.id === activeId) || null;

  let right;
  if (creating) {
    right = <CreateProjectCard onCancel={() => setCreating(false)} onCreated={handleCreated}/>;
  } else if (activeProject) {
    right = <ProjectDetail key={activeProject.id} project={activeProject} initialTab={pendingTab}
              onUpdated={handleUpdated} onDeleted={handleDeleted} chat={chat}
              openSessionId={openSessionId} onConsumeOpen={() => setOpenSessionId(null)}/>;
  } else {
    right = <ProjectsEmptyState onCreate={() => { setPendingTab('conversations'); setCreating(true); }}/>;
  }

  return (
    <div style={{ display:'flex', height:'100%', overflow:'hidden' }} className="surface-enter">
      <SplitLayout
        leftWidth={220}
        left={
          <ProjectList
            projects={projects}
            activeId={activeId}
            creating={creating}
            loading={loading}
            onSelect={id => { setCreating(false); setOpenSessionId(null); setActiveId(id); }}
            onNew={() => { setOpenSessionId(null); setPendingTab('conversations'); setCreating(true); }}
          />
        }
        right={right}
      />
    </div>
  );
}

window.V2Projects = { ProjectsSurface };
