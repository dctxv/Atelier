/* ====== Projects surface — scoped AI workspaces ====== */
const { useState, useEffect, useRef, useCallback } = React;

/* ── Relative time helper ── */
function relTime(ts) {
  if (!ts) return '';
  const diff = Date.now() / 1000 - ts;
  if (diff < 60)    return 'just now';
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

/* ── Project list (left pane) ── */
function ProjectList({ projects, activeId, loading, onSelect, creating, setCreating, newName, setNewName, onCreate }) {
  const inputRef = useRef(null);
  useEffect(() => { if (creating) setTimeout(() => inputRef.current?.focus(), 40); }, [creating]);

  function handleKey(e) {
    if (e.key === 'Enter') onCreate();
    if (e.key === 'Escape') { setCreating(false); setNewName(''); }
  }

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
        <button onClick={() => setCreating(true)} title="New project" style={{
          width:26, height:26, borderRadius:7, display:'grid', placeItems:'center',
          border:'1px solid var(--border-2)', color:'var(--text-3)', cursor:'pointer',
        }}>
          <Ico n="plus" size={12} color="currentColor"/>
        </button>
      </div>

      {/* Inline create */}
      {creating && (
        <div style={{ padding:'10px 12px', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
          <input ref={inputRef} value={newName} onChange={e => setNewName(e.target.value)}
            onKeyDown={handleKey} placeholder="Project name…"
            style={{ width:'100%', fontFamily:'var(--font-b)', fontSize:13, fontStyle:'italic',
              color:'var(--text)', background:'transparent', marginBottom:7 }}
          />
          <div style={{ display:'flex', gap:5 }}>
            <button onClick={onCreate} style={{
              flex:1, fontFamily:'var(--font-m)', fontSize:10, padding:'4px 0',
              borderRadius:6, background:'var(--accent)', color:'#FFF4E8', cursor:'pointer',
              letterSpacing:'.04em',
            }}>Create</button>
            <button onClick={() => { setCreating(false); setNewName(''); }} style={{
              flex:1, fontFamily:'var(--font-m)', fontSize:10, padding:'4px 0',
              borderRadius:6, border:'1px solid var(--border-2)', color:'var(--text-3)', cursor:'pointer',
            }}>Cancel</button>
          </div>
        </div>
      )}

      {/* List body */}
      <div className="scroll" style={{ flex:1 }}>
        {loading && (
          <div style={{ padding:24, textAlign:'center' }}><Pulse size={7}/></div>
        )}
        {!loading && projects.length === 0 && !creating && (
          <div style={{ padding:'28px 14px', textAlign:'center', opacity:.45 }}>
            <div style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)' }}>
              No projects yet
            </div>
          </div>
        )}
        {projects.map(p => {
          const on = p.id === activeId;
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

/* ── Project detail (right pane) ── */
function ProjectDetail({ project, onUpdated, onOpenChat }) {
  const [tab,          setTab]          = useState('files');
  const [instructions, setInstructions] = useState(project.instructions || '');
  const [docs,         setDocs]         = useState([]);
  const [atoms,        setAtoms]        = useState([]);
  const [docsLoaded,   setDocsLoaded]   = useState(false);
  const [uploading,    setUploading]    = useState(false);
  const [err,          setErr]          = useState(null);
  const saveTimer = useRef(null);

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

  /* Load project memory on first visit to tab */
  const loadAtoms = useCallback(async () => {
    try {
      const r = await fetch(`/api/projects/${project.id}/memory`);
      const d = await r.json();
      setAtoms(d.atoms || []);
    } catch {}
  }, [project.id]);

  useEffect(() => {
    if (tab === 'memory') loadAtoms();
  }, [tab, loadAtoms]);

  /* Instructions autosave (600ms debounce) */
  function handleInstructionsChange(val) {
    setInstructions(val);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      try {
        const r = await fetch(`/api/projects/${project.id}`, {
          method:'PATCH', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ instructions: val }),
        });
        const d = await r.json();
        if (d.project) onUpdated(d.project);
      } catch {}
    }, 600);
  }

  /* File upload */
  async function handleUpload(files) {
    setErr(null);
    setUploading(true);
    for (const f of files) {
      const form = new FormData();
      form.append('file', f);
      try {
        const r = await fetch(`/api/projects/${project.id}/documents/upload`,
          { method:'POST', body:form });
        if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
      } catch (e) { setErr(e.message); }
    }
    setUploading(false);
    await loadDocs();
  }

  async function handleDeleteDoc(docId) {
    try {
      await fetch(`/api/projects/${project.id}/documents/${docId}`, { method:'DELETE' });
      await loadDocs();
    } catch (e) { setErr(e.message); }
  }

  async function handlePromoteAtom(atomId) {
    try {
      await fetch(`/api/memory/${atomId}/promote`, { method:'PATCH' });
      setAtoms(prev => prev.filter(a => a.id !== atomId));
    } catch {}
  }

  const activeCount = docs.filter(d => ['queued','extracting','embedding'].includes(d.status)).length;
  const readyCount  = docs.filter(d => d.status === 'ready').length;

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>

      {/* Project header */}
      <div style={{
        height:52, flexShrink:0, background:'var(--nav-bg)',
        borderBottom:'1px solid var(--border)',
        display:'flex', alignItems:'center', padding:'0 28px',
        justifyContent:'space-between', gap:12,
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, minWidth:0 }}>
          <Ico n="projects" size={14} color="var(--accent-tx)"/>
          <span style={{ fontFamily:'var(--font-b)', fontSize:14.5, fontStyle:'italic',
            color:'var(--text)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {project.name}
          </span>
          {readyCount > 0 && (
            <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)',
              letterSpacing:'.06em', flexShrink:0 }}>
              {readyCount} file{readyCount !== 1 ? 's' : ''} ready
            </span>
          )}
        </div>
        <button onClick={() => onOpenChat(project)} style={{
          display:'flex', alignItems:'center', gap:6, padding:'6px 16px',
          borderRadius:9, background:'var(--accent)', color:'#FFF4E8',
          fontFamily:'var(--font-m)', fontSize:10.5, letterSpacing:'.04em',
          cursor:'pointer', flexShrink:0, border:'none',
        }}>
          <Ico n="chat" size={11} color="#FFF4E8"/>
          Chat in project
        </button>
      </div>

      {/* Tab nav */}
      <TabNav
        tabs={[
          { id:'files',        label:'Files', live: activeCount > 0 },
          { id:'instructions', label:'Instructions' },
          { id:'memory',       label:'Memory' },
        ]}
        active={tab}
        onSelect={setTab}
      />

      {/* Tab content */}
      <div className="scroll" style={{ flex:1, padding:'32px 56px', maxWidth:780 }}>

        {/* ── Files tab ── */}
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
              {err && (
                <div style={{ marginTop:8, fontFamily:'var(--font-m)', fontSize:12, color:'#a94442' }}>{err}</div>
              )}
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

        {/* ── Instructions tab ── */}
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
                Leave blank to fall back to the global system prompt.
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

        {/* ── Memory tab ── */}
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

      </div>
    </div>
  );
}

/* ── Empty state ── */
function ProjectsEmptyState({ onCreate }) {
  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center',
      justifyContent:'center', gap:16, opacity:.5, padding:40 }}>
      <Ico n="projects" size={32} color="var(--text-3)"/>
      <div style={{ textAlign:'center' }}>
        <div style={{ fontFamily:'var(--font-b)', fontSize:16, fontStyle:'italic',
          color:'var(--text-2)', marginBottom:6 }}>
          No project selected
        </div>
        <div style={{ fontFamily:'var(--font-m)', fontSize:11.5, color:'var(--text-3)', lineHeight:1.6 }}>
          Select a project from the list, or create one with + to get started.
        </div>
      </div>
      <button onClick={onCreate} style={{
        fontFamily:'var(--font-m)', fontSize:11, padding:'7px 20px',
        borderRadius:9, border:'1px solid var(--border-2)',
        color:'var(--text-3)', cursor:'pointer', marginTop:4,
      }}>
        New project
      </button>
    </div>
  );
}

/* ── Main surface ── */
function ProjectsSurface({ onOpenChat }) {
  const [projects,  setProjects]  = useState([]);
  const [activeId,  setActiveId]  = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [creating,  setCreating]  = useState(false);
  const [newName,   setNewName]   = useState('');

  const loadProjects = useCallback(async () => {
    try {
      const r = await fetch('/api/projects');
      const d = await r.json();
      setProjects(d.projects || []);
      setLoading(false);
    } catch { setLoading(false); }
  }, []);

  useEffect(() => { loadProjects(); }, [loadProjects]);

  async function handleCreate() {
    if (!newName.trim()) return;
    try {
      const r = await fetch('/api/projects', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ name: newName.trim() }),
      });
      const d = await r.json();
      if (d.project) {
        setProjects(prev => [d.project, ...prev]);
        setActiveId(d.project.id);
      }
    } catch {}
    setCreating(false);
    setNewName('');
  }

  function handleUpdated(updated) {
    setProjects(prev => prev.map(p => p.id === updated.id ? { ...p, ...updated } : p));
  }

  const activeProject = projects.find(p => p.id === activeId) || null;

  return (
    <div style={{ display:'flex', height:'100%', overflow:'hidden' }} className="surface-enter">
      <SplitLayout
        leftWidth={220}
        left={
          <ProjectList
            projects={projects}
            activeId={activeId}
            loading={loading}
            onSelect={setActiveId}
            creating={creating}
            setCreating={setCreating}
            newName={newName}
            setNewName={setNewName}
            onCreate={handleCreate}
          />
        }
        right={
          activeProject
            ? <ProjectDetail
                key={activeProject.id}
                project={activeProject}
                onUpdated={handleUpdated}
                onOpenChat={onOpenChat}
              />
            : <ProjectsEmptyState onCreate={() => setCreating(true)}/>
        }
      />
    </div>
  );
}

window.V2Projects = { ProjectsSurface };
