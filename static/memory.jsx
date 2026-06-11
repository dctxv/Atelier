/* ====== v2 Memory surface — Living Memory System ====== */
const { useState, useEffect, useCallback } = React;

const CAT_MAP = {
  preference: 'preferences', identity: 'preferences', goal: 'preferences',
  contact: 'people',
  task: 'decisions',
  project: 'projects',
  fact: 'facts',
};
const DISPLAY_TAGS = ['all','preferences','people','decisions','projects','facts'];
const TAG_COLORS = {
  preferences: 'var(--accent)',
  people:      'oklch(52% .12 180)',
  decisions:   'oklch(48% .10 280)',
  projects:    'oklch(50% .10 120)',
  facts:       'var(--text-3)',
};
const MODALITY_COLORS = {
  desire:     'oklch(52% .12 40)',
  plan:       'oklch(50% .12 200)',
  commitment: 'oklch(48% .10 280)',
  hypothesis: 'oklch(52% .10 320)',
  insight:    'oklch(50% .12 160)',
};

function Toggle({ on, onToggle }) {
  return (
    <div onClick={onToggle} style={{
      width:34, height:19, borderRadius:12, flexShrink:0, cursor:'pointer',
      background: on ? 'var(--accent-bg)' : 'var(--border)',
      border:`1px solid ${on ? 'var(--accent-bd)' : 'var(--border-2)'}`,
      position:'relative', transition:'all var(--t)',
    }}>
      <div style={{
        position:'absolute', top:2, left: on?15:2, width:13, height:13,
        borderRadius:'50%', background: on ? 'var(--accent)' : 'var(--text-3)',
        transition:'left var(--t), background var(--t)',
      }}/>
    </div>
  );
}

function ReviewTab({ questions, onResolve }) {
  const open = questions.open || [];
  const resolved = questions.resolved || [];

  if (open.length === 0) {
    return (
      <div style={{ padding:'48px 56px', textAlign:'center' }}>
        <p style={{ fontFamily:'var(--font-b)', fontSize:15, color:'var(--text-2)', fontStyle:'italic' }}>
          Memory is coherent
        </p>
        <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)', marginTop:8 }}>
          No conflicts or gaps detected.
        </p>
        {resolved.length > 0 && (
          <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)', marginTop:16 }}>
            {resolved.length} previously resolved question{resolved.length!==1?'s':''}.
          </p>
        )}
      </div>
    );
  }

  return (
    <div style={{ maxWidth:760, margin:'0 auto', padding:'32px 56px' }}>
      <SectionLabel right={`${open.length} open`} style={{ marginBottom:20 }}>Review</SectionLabel>
      {open.map(q => (
        <QuestionCard key={q.id} q={q} onResolve={onResolve}/>
      ))}
    </div>
  );
}

function QuestionCard({ q, onResolve }) {
  const kindLabel = {
    conflict:        'Conflict',
    soft_conflict:   'Possible conflict',
    reversal_check:  'Changed your mind?',
    gap:             'Gap',
    stale_check:     'Still current?',
    goal_check:      'Goal update',
  }[q.kind] || q.kind;

  const kindColor = {
    conflict:       'oklch(52% .15 25)',
    soft_conflict:  'oklch(52% .10 40)',
    reversal_check: 'oklch(48% .10 280)',
    gap:            'oklch(50% .10 200)',
    stale_check:    'oklch(48% .08 180)',
    goal_check:     'oklch(50% .10 120)',
  }[q.kind] || 'var(--text-3)';

  return (
    <div style={{
      marginBottom:20, padding:'16px 20px',
      border:'1px solid var(--border-2)', borderRadius:10,
      background:'var(--nav-bg)',
    }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
        <span style={{
          fontFamily:'var(--font-m)', fontSize:9, letterSpacing:'.1em',
          textTransform:'uppercase', color:kindColor,
          padding:'2px 8px', border:`1px solid ${kindColor}`, borderRadius:4,
        }}>{kindLabel}</span>
        <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>
          {relTime(q.created_at)}
        </span>
      </div>

      <p style={{ fontFamily:'var(--font-b)', fontSize:13, color:'var(--text)', marginBottom:12 }}>
        {q.prompt_text}
      </p>

      {q.atoms && q.atoms.length > 0 && (
        <div style={{ marginBottom:16 }}>
          {q.atoms.map((a, i) => (
            <div key={a.id} style={{
              padding:'8px 12px', marginBottom:6,
              background:'var(--thread-bg)', borderRadius:6,
              display:'flex', alignItems:'center', justifyContent:'space-between', gap:12,
            }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text)', flex:1 }}>
                {a.text}
              </span>
              {q.atoms.length >= 2 && (
                <button onClick={() => onResolve(q.id, i === 0 ? 'confirm_a' : 'confirm_b', a.id)}
                  style={{
                    fontFamily:'var(--font-m)', fontSize:10, color:'var(--accent)',
                    padding:'3px 10px', border:'1px solid var(--accent-bd)', borderRadius:4,
                    cursor:'pointer', flexShrink:0,
                  }}>
                  This one
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
        {q.atoms && q.atoms.length >= 2 && (
          <button onClick={() => onResolve(q.id, 'both_true')} style={btnStyle('outline')}>Both true</button>
        )}
        {q.atoms && q.atoms.length >= 2 && (
          <button onClick={() => onResolve(q.id, 'neither')} style={btnStyle('outline')}>Neither</button>
        )}
        <button onClick={() => onResolve(q.id, 'dismiss')} style={btnStyle('ghost')}>Dismiss</button>
      </div>
    </div>
  );
}

function btnStyle(variant) {
  if (variant === 'outline') return {
    fontFamily:'var(--font-m)', fontSize:10, cursor:'pointer',
    padding:'4px 12px', borderRadius:5,
    border:'1px solid var(--border-2)', color:'var(--text-2)',
    background:'transparent',
  };
  return {
    fontFamily:'var(--font-m)', fontSize:10, cursor:'pointer',
    padding:'4px 12px', borderRadius:5,
    border:'1px solid transparent', color:'var(--text-3)',
    background:'transparent',
  };
}

function GoalsTab({ goals }) {
  if (!goals || goals.length === 0) {
    return (
      <div style={{ padding:'48px 56px', textAlign:'center' }}>
        <p style={{ fontFamily:'var(--font-b)', fontSize:15, color:'var(--text-2)', fontStyle:'italic' }}>
          No goals or aspirations yet
        </p>
        <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)', marginTop:8 }}>
          Goals are extracted from phrases like "I want to…" or "I'm planning to…"
        </p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth:760, margin:'0 auto', padding:'32px 56px' }}>
      <SectionLabel right={`${goals.length} active`} style={{ marginBottom:20 }}>Goals & Aspirations</SectionLabel>
      {goals.map((g, i) => {
        const color = MODALITY_COLORS[g.modality] || 'var(--text-3)';
        return (
          <div key={g.id||i}>
            <div style={{ padding:'10px 0 12px', display:'flex', gap:16 }}>
              <div style={{ width:1.5, background:color, opacity:.35, borderRadius:1, flexShrink:0 }}/>
              <div style={{ flex:1 }}>
                <p style={{ fontFamily:'var(--font-b)', fontSize:14.5, lineHeight:1.72,
                  color:'var(--text)', marginBottom:4 }}>{g.text}</p>
                <div style={{ display:'flex', gap:10 }}>
                  <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:color,
                    textTransform:'uppercase', letterSpacing:'.08em' }}>
                    {g.modality || 'goal'}
                  </span>
                  <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}>
                    · {relTime(g.timestamp)}
                  </span>
                </div>
              </div>
            </div>
            {i < goals.length-1 && <Rule/>}
          </div>
        );
      })}
    </div>
  );
}

function relTime(ts) {
  if (!ts) return '';
  const diff = (Date.now()/1000) - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff/86400)}d ago`;
  if (diff < 2592000) return `${Math.floor(diff/604800)}w ago`;
  return `${Math.floor(diff/2592000)}mo ago`;
}

const TABS = ['fragments', 'review', 'goals', 'skills'];
const TAB_LABELS = { fragments:'Memory', review:'Review', goals:'Goals', skills:'Skills' };

function MemorySurface() {
  const [tab,           setTab]           = useState('fragments');
  const [memories,      setMemories]      = useState([]);
  const [skills,        setSkills]        = useState([]);
  const [questions,     setQuestions]     = useState({open:[],resolved:[]});
  const [goals,         setGoals]         = useState([]);
  const [filter,        setFilter]        = useState('all');
  const [query,         setQuery]         = useState('');
  const [loading,       setLoading]       = useState(true);
  const [reviewBadge,   setReviewBadge]   = useState(0);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch('/api/memory').then(r=>r.ok?r.json():{memories:[]}).catch(()=>({memories:[]})),
      fetch('/api/skills').then(r=>r.ok?r.json():{skills:[]}).catch(()=>({skills:[]})),
      fetch('/api/memory/questions').then(r=>r.ok?r.json():{open:[],resolved:[]}).catch(()=>({open:[],resolved:[]})),
      fetch('/api/memory/goals').then(r=>r.ok?r.json():{goals:[]}).catch(()=>({goals:[]})),
    ]).then(([memData, skillData, qData, goalData]) => {
      setMemories(memData.memories || memData.memory || []);
      setSkills(skillData.skills || []);
      setQuestions(qData);
      setReviewBadge((qData.open || []).length);
      setGoals(goalData.goals || []);
      setLoading(false);
    });
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  async function handleResolve(questionId, choice, atomId) {
    await fetch(`/api/memory/questions/${questionId}/resolve`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({choice, atom_id:atomId}),
    });
    loadData();
  }

  function displayTag(mem) {
    const raw = (mem.category || 'fact').toLowerCase();
    return CAT_MAP[raw] || 'facts';
  }

  const filtered = memories.filter(m => {
    const tag = displayTag(m);
    if (filter !== 'all' && tag !== filter) return false;
    if (query && !(m.text||'').toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  const groups = {};
  filtered.forEach(m => {
    const t = displayTag(m);
    if (!groups[t]) groups[t] = [];
    groups[t].push(m);
  });

  async function toggleSkill(sk) {
    const newStatus = sk.status === 'active' ? 'inactive' : 'active';
    setSkills(prev => prev.map(s => s.id===sk.id ? {...s,status:newStatus} : s));
    try {
      await fetch(`/api/skills/${sk.id}/toggle`, { method:'POST' });
    } catch(e) {
      setSkills(prev => prev.map(s => s.id===sk.id ? {...s,status:sk.status} : s));
    }
  }

  if (loading) return (
    <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', opacity:.4 }}>
      <Pulse size={10}/>
    </div>
  );

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }} className="surface-enter">

      {/* ── Tab bar ── */}
      <div style={{ height:48, flexShrink:0, background:'var(--nav-bg)',
        borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center',
        padding:'0 40px', gap:0 }}>
        {TABS.map(t => {
          const on = tab === t;
          const label = TAB_LABELS[t];
          const badge = t === 'review' ? reviewBadge : 0;
          return (
            <button key={t} onClick={() => setTab(t)} style={{
              padding:'0 16px 0 0',
              fontFamily:'var(--font-b)', fontSize:13, fontStyle:'italic',
              color: on ? 'var(--text)' : 'var(--text-2)',
              borderBottom:`1.5px solid ${on ? 'var(--accent)' : 'transparent'}`,
              paddingBottom:10, marginBottom:-1,
              cursor:'pointer', transition:'color var(--t), border-color var(--t)',
              whiteSpace:'nowrap', flexShrink:0, position:'relative',
            }}>
              {label}
              {badge > 0 && (
                <span style={{
                  position:'absolute', top:4, right:0,
                  width:14, height:14, borderRadius:'50%',
                  background:'var(--accent)', color:'#fff',
                  fontFamily:'var(--font-m)', fontSize:8, fontWeight:700,
                  display:'flex', alignItems:'center', justifyContent:'center',
                }}>{badge > 9 ? '9+' : badge}</span>
              )}
            </button>
          );
        })}

        {/* Search (only on fragments tab) */}
        {tab === 'fragments' && (
          <>
            <div style={{ marginLeft:24, display:'flex', gap:0 }}>
              {DISPLAY_TAGS.map(t => {
                const on = filter === t;
                return (
                  <button key={t} onClick={() => setFilter(t)} style={{
                    padding:'0 12px 0 0', marginRight:4,
                    fontFamily:'var(--font-m)', fontSize:11,
                    color: on ? 'var(--text-2)' : 'var(--text-3)',
                    fontWeight: on ? 600 : 400,
                    cursor:'pointer',
                  }}>{t}</button>
                );
              })}
            </div>
            <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:8,
              padding:'4px 12px', border:'1px solid var(--border-2)', borderRadius:8,
              background:'var(--thread-bg)' }}>
              <Ico n="search" size={12} color="var(--text-3)"/>
              <input value={query} onChange={e=>setQuery(e.target.value)}
                placeholder="Search memory…"
                style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text)', width:140 }}/>
            </div>
          </>
        )}
      </div>

      {/* ── Content ── */}
      <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>

        {tab === 'fragments' && (
          <div style={{ maxWidth:760, margin:'0 auto', padding:'32px 56px' }}>
            <SectionLabel right={`${filtered.length} fragments`} style={{ marginBottom:16 }}>Memory</SectionLabel>

            {filtered.length === 0 && (
              <p style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', fontStyle:'italic' }}>
                {memories.length === 0 ? 'No memories yet — they build up as you chat.' : 'No matches.'}
              </p>
            )}

            {Object.keys(groups).map(tag => (
              <div key={tag} style={{ marginBottom:28 }}>
                <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
                  <span style={{ width:6, height:6, borderRadius:'50%', flexShrink:0,
                    background: TAG_COLORS[tag] || 'var(--text-3)', opacity:.7 }}/>
                  <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
                    letterSpacing:'.12em', textTransform:'uppercase' }}>{tag}</span>
                </div>
                {groups[tag].map((m, i) => (
                  <div key={m.id||i}>
                    <div style={{ padding:'10px 0 12px', display:'flex', gap:16 }}>
                      <div style={{ width:1.5, background: TAG_COLORS[tag] || 'var(--bar)',
                        opacity:.35, borderRadius:1, flexShrink:0 }}/>
                      <div style={{ flex:1 }}>
                        <p style={{ fontFamily:'var(--font-b)', fontSize:14.5, lineHeight:1.72,
                          color:'var(--text)', marginBottom:6 }}>{m.text}</p>
                        <div style={{ display:'flex', gap:10, flexWrap:'wrap' }}>
                          <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}>{relTime(m.timestamp)}</span>
                          {m.predicate && (
                            <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
                              padding:'1px 6px', border:'1px solid var(--border)', borderRadius:3 }}>
                              {m.predicate}
                            </span>
                          )}
                          {m.modality && m.modality !== 'factual' && (
                            <span style={{ fontFamily:'var(--font-m)', fontSize:9,
                              color: MODALITY_COLORS[m.modality] || 'var(--text-3)',
                              padding:'1px 6px', border:`1px solid ${MODALITY_COLORS[m.modality] || 'var(--border)'}`, borderRadius:3 }}>
                              {m.modality}
                            </span>
                          )}
                          {m.confidence !== null && m.confidence !== undefined && m.confidence < 0.7 && (
                            <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)', opacity:.7 }}>
                              {Math.round(m.confidence * 100)}% confident
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    {i < groups[tag].length-1 && <Rule/>}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {tab === 'review' && (
          <ReviewTab questions={questions} onResolve={handleResolve}/>
        )}

        {tab === 'goals' && (
          <GoalsTab goals={goals}/>
        )}

        {tab === 'skills' && (
          <div style={{ maxWidth:760, margin:'0 auto', padding:'32px 56px' }}>
            <SectionLabel right={`${skills.filter(s=>s.status==='active'||s.enabled!==false).length} of ${skills.length} enabled`}
              style={{ marginBottom:16 }}>Skills</SectionLabel>

            {skills.length === 0 && (
              <p style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', fontStyle:'italic' }}>
                No skills found.
              </p>
            )}

            {skills.map((sk, i) => {
              const isOn = sk.enabled !== false && sk.status !== 'inactive';
              return (
                <div key={sk.id||i}>
                  <div style={{ display:'flex', alignItems:'center', gap:16, padding:'12px 0' }}>
                    <div style={{ flex:1 }}>
                      <div style={{ display:'flex', alignItems:'baseline', gap:10, marginBottom:3 }}>
                        <span style={{ fontFamily:'var(--font-b)', fontSize:14.5, fontStyle:'italic',
                          color: isOn ? 'var(--text)' : 'var(--text-q)' }}>{sk.name}</span>
                        {sk.category && <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
                          letterSpacing:'.08em', textTransform:'uppercase' }}>{sk.category}</span>}
                      </div>
                      <span style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)' }}>
                        {sk.description || sk.when_to_use || ''}
                      </span>
                    </div>
                    <Toggle on={isOn} onToggle={() => toggleSkill(sk)}/>
                  </div>
                  {i < skills.length-1 && <Rule/>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

window.V2Memory = { MemorySurface };
