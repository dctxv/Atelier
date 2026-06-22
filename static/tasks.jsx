/* ====== Tasks surface - commitments into action ====== */
const { useState: useTaskState, useEffect: useTaskEffect, useMemo: useTaskMemo } = React;

function _taskDate(v) {
  if (!v) return '';
  try {
    return new Date(v).toLocaleDateString(undefined, { month:'short', day:'numeric' });
  } catch { return ''; }
}

function _taskFetch(url, opts) {
  return fetch(url, {
    headers: { 'Content-Type':'application/json', ...(opts && opts.headers ? opts.headers : {}) },
    ...(opts || {}),
  });
}

function TaskComposer({ onCreate }) {
  const [title, setTitle] = useTaskState('');
  const [priority, setPriority] = useTaskState('medium');

  async function submit(e) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    await onCreate({ title: clean, priority, status:'todo' });
    setTitle('');
    setPriority('medium');
  }

  return (
    <form onSubmit={submit} style={{
      display:'grid', gridTemplateColumns:'minmax(0,1fr) 112px 34px',
      gap:8, alignItems:'center', marginBottom:14,
    }}>
      <input value={title} onChange={e=>setTitle(e.target.value)} placeholder="New task"
        style={{
          height:34, minWidth:0, border:'1px solid var(--border-2)',
          borderRadius:7, background:'var(--surface)', color:'var(--text)',
          fontFamily:'var(--font-b)', fontSize:14, padding:'0 11px',
        }}/>
      <select value={priority} onChange={e=>setPriority(e.target.value)}
        style={{
          height:34, border:'1px solid var(--border-2)', borderRadius:7,
          background:'var(--surface)', color:'var(--text-q)',
          fontFamily:'var(--font-m)', fontSize:11, padding:'0 8px',
        }}>
        <option value="low">low</option>
        <option value="medium">medium</option>
        <option value="high">high</option>
      </select>
      <button type="submit" title="Add task" style={{
        width:34, height:34, borderRadius:7, display:'grid', placeItems:'center',
        border:'1px solid var(--accent-bd)', background:'var(--accent-bg)',
        color:'var(--accent-tx)', cursor:'pointer',
      }}>
        <Ico n="plus" size={13} color="currentColor"/>
      </button>
    </form>
  );
}

function TaskRow({ task, onUpdate, onDelete }) {
  const [title, setTitle] = useTaskState(task.title || '');
  const [description, setDescription] = useTaskState(task.description || '');

  useTaskEffect(() => {
    setTitle(task.title || '');
    setDescription(task.description || '');
  }, [task.id, task.title, task.description]);

  const done = task.status === 'done' || task.status === 'completed';
  const sourceLabel = task.source_kind === 'commitment'
    ? 'commitment'
    : task.source_kind === 'assistant_commitment'
      ? 'legacy commitment'
      : null;

  function saveText() {
    const patch = {};
    if (title.trim() && title.trim() !== task.title) patch.title = title.trim();
    if ((description || '') !== (task.description || '')) patch.description = description;
    if (Object.keys(patch).length) onUpdate(task.id, patch);
  }

  return (
    <div style={{
      border:'1px solid var(--border)', borderRadius:8, background:'var(--panel-bg)',
      padding:'12px 14px', display:'grid', gridTemplateColumns:'28px minmax(0,1fr) 118px 30px',
      gap:10, alignItems:'start',
    }}>
      <button onClick={()=>onUpdate(task.id, { status: done ? 'todo' : 'done' })}
        title={done ? 'Mark open' : 'Mark done'} style={{
          width:24, height:24, borderRadius:7, display:'grid', placeItems:'center',
          border:`1px solid ${done ? 'var(--accent-bd)' : 'var(--border-2)'}`,
          background: done ? 'var(--accent-bg)' : 'var(--surface)',
          color: done ? 'var(--accent-tx)' : 'var(--text-3)', cursor:'pointer',
        }}>
        <Ico n="check" size={13} color="currentColor"/>
      </button>

      <div style={{ minWidth:0 }}>
        <input value={title} onChange={e=>setTitle(e.target.value)}
          onBlur={saveText}
          onKeyDown={e=>{ if (e.key === 'Enter') e.currentTarget.blur(); }}
          style={{
            width:'100%', minWidth:0, border:0, outline:0, background:'transparent',
            color: done ? 'var(--text-3)' : 'var(--text)', opacity: done ? .72 : 1,
            fontFamily:'var(--font-b)', fontSize:15, lineHeight:1.35,
            textDecoration: done ? 'line-through' : 'none',
          }}/>
        <textarea value={description} onChange={e=>setDescription(e.target.value)}
          onBlur={saveText} placeholder="Context"
          style={{
            width:'100%', minWidth:0, minHeight:34, resize:'vertical', border:0,
            outline:0, background:'transparent', color:'var(--text-2)',
            fontFamily:'var(--font-b)', fontSize:12.5, lineHeight:1.45,
            marginTop:3, padding:0,
          }}/>
        <div style={{ display:'flex', gap:8, alignItems:'center', flexWrap:'wrap', marginTop:5 }}>
          {sourceLabel && (
            <span style={{
              fontFamily:'var(--font-m)', fontSize:9, color:'var(--accent-tx)',
              background:'var(--accent-bg)', border:'1px solid var(--accent-bd)',
              borderRadius:999, padding:'2px 7px',
            }}>{sourceLabel}</span>
          )}
          <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)' }}>
            {_taskDate(task.updated_at)}
          </span>
        </div>
      </div>

      <select value={task.priority || 'medium'}
        onChange={e=>onUpdate(task.id, { priority:e.target.value })}
        style={{
          height:30, border:'1px solid var(--border-2)', borderRadius:7,
          background:'var(--surface)', color:'var(--text-q)',
          fontFamily:'var(--font-m)', fontSize:10.5, padding:'0 8px',
        }}>
        <option value="low">low</option>
        <option value="medium">medium</option>
        <option value="high">high</option>
      </select>

      <button onClick={()=>onDelete(task.id)} title="Delete task" style={{
        width:30, height:30, borderRadius:7, display:'grid', placeItems:'center',
        color:'var(--text-3)', border:'1px solid transparent', cursor:'pointer',
      }}>
        <Ico n="trash" size={13} color="currentColor"/>
      </button>
    </div>
  );
}

function CommitmentProposal({ item, onConfirm, onReject }) {
  const ctx = item.context || {};
  const quote = ctx.user_text || ctx.assistant_text || item.atom_text || '';
  return (
    <div style={{
      border:'1px solid var(--accent-bd)', borderRadius:8,
      background:'var(--accent-bg)', padding:'13px 14px',
      display:'grid', gridTemplateColumns:'minmax(0,1fr) auto', gap:14,
      alignItems:'start',
    }}>
      <div style={{ minWidth:0 }}>
        <div style={{
          fontFamily:'var(--font-b)', fontSize:15, color:'var(--text)',
          lineHeight:1.4, marginBottom:6,
        }}>{item.title}</div>
        {quote && (
          <div style={{
            fontFamily:'var(--font-b)', fontSize:12.5, color:'var(--text-2)',
            lineHeight:1.45, maxHeight:54, overflow:'hidden',
          }}>{quote}</div>
        )}
        <div style={{
          fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
          marginTop:7, letterSpacing:'.04em',
        }}>{_taskDate(item.created_at)}</div>
      </div>
      <div style={{ display:'flex', gap:6, flexShrink:0 }}>
        <button onClick={()=>onConfirm(item.id)} style={{
          height:30, borderRadius:7, padding:'0 10px', display:'flex',
          alignItems:'center', gap:5, border:'1px solid var(--accent-bd)',
          color:'var(--accent-tx)', background:'var(--surface)', cursor:'pointer',
          fontFamily:'var(--font-m)', fontSize:10.5,
        }}>
          <Ico n="check" size={11} color="currentColor"/>Confirm
        </button>
        <button onClick={()=>onReject(item.id)} title="Reject commitment" style={{
          width:30, height:30, borderRadius:7, display:'grid', placeItems:'center',
          border:'1px solid var(--border-2)', color:'var(--text-3)',
          background:'transparent', cursor:'pointer',
        }}>
          <Ico n="close" size={12} color="currentColor"/>
        </button>
      </div>
    </div>
  );
}

function TasksSurface() {
  const [tab, setTab] = useTaskState('open');
  const [tasks, setTasks] = useTaskState([]);
  const [proposals, setProposals] = useTaskState([]);
  const [loading, setLoading] = useTaskState(true);

  async function load() {
    setLoading(true);
    try {
      const [tr, cr] = await Promise.all([
        fetch('/api/tasks'),
        fetch('/api/commitments?status=proposed'),
      ]);
      const td = tr.ok ? await tr.json() : { tasks:[] };
      const cd = cr.ok ? await cr.json() : { commitments:[] };
      setTasks(td.tasks || []);
      setProposals(cd.commitments || []);
    } finally {
      setLoading(false);
    }
  }

  useTaskEffect(() => { load(); }, []);

  async function createTask(data) {
    const r = await _taskFetch('/api/tasks', {
      method:'POST', body:JSON.stringify(data),
    });
    if (r.ok) {
      const d = await r.json();
      setTasks(prev => [d.task, ...prev]);
    }
  }

  async function updateTask(id, patch) {
    const r = await _taskFetch(`/api/tasks/${id}`, {
      method:'PUT', body:JSON.stringify(patch),
    });
    if (r.ok) {
      const d = await r.json();
      setTasks(prev => prev.map(t => t.id === id ? d.task : t));
    }
  }

  async function deleteTask(id) {
    const r = await fetch(`/api/tasks/${id}`, { method:'DELETE' });
    if (r.ok) setTasks(prev => prev.filter(t => t.id !== id));
  }

  async function confirmCommitment(id) {
    const r = await fetch(`/api/commitments/${id}/confirm`, { method:'POST' });
    if (r.ok) await load();
  }

  async function rejectCommitment(id) {
    const r = await fetch(`/api/commitments/${id}/reject`, { method:'POST' });
    if (r.ok) setProposals(prev => prev.filter(c => c.id !== id));
  }

  const openTasks = useTaskMemo(
    () => tasks.filter(t => t.status !== 'done' && t.status !== 'completed'),
    [tasks]
  );
  const doneTasks = useTaskMemo(
    () => tasks.filter(t => t.status === 'done' || t.status === 'completed'),
    [tasks]
  );

  const tabs = [
    { id:'open', label:`Open ${openTasks.length}` },
    { id:'proposed', label:`Proposed ${proposals.length}` },
    { id:'done', label:`Done ${doneTasks.length}` },
  ];
  const shown = tab === 'done' ? doneTasks : openTasks;

  return (
    <div style={{ flex:1, minHeight:0, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TabNav tabs={tabs} active={tab} onSelect={setTab}
        right={<button onClick={load} title="Refresh" style={{
          width:28, height:28, borderRadius:7, display:'grid', placeItems:'center',
          border:'1px solid var(--border-2)', color:'var(--text-3)',
          background:'transparent', cursor:'pointer',
        }}><Ico n="refresh" size={12} color="currentColor"/></button>}/>

      <div style={{ flex:1, minHeight:0, overflow:'auto', padding:'28px 56px 48px' }}>
        <div style={{ maxWidth:900, margin:'0 auto' }}>
          {tab === 'open' && <TaskComposer onCreate={createTask}/>}

          {tab === 'proposed' ? (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              {loading && <EmptyState icon="tasks" title="Loading"/>}
              {!loading && proposals.length === 0 && (
                <EmptyState icon="tasks" title="No proposed commitments"/>
              )}
              {!loading && proposals.map(c => (
                <CommitmentProposal key={c.id} item={c}
                  onConfirm={confirmCommitment} onReject={rejectCommitment}/>
              ))}
            </div>
          ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              {loading && <EmptyState icon="tasks" title="Loading"/>}
              {!loading && shown.length === 0 && (
                <EmptyState icon="tasks" title={tab === 'done' ? 'Nothing completed' : 'No open tasks'}/>
              )}
              {!loading && shown.map(t => (
                <TaskRow key={t.id} task={t} onUpdate={updateTask} onDelete={deleteTask}/>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

window.V2Tasks = { TasksSurface };
