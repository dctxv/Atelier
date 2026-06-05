/* ====== v2 Memory surface — live backend ====== */
const { useState, useEffect } = React;

/* Map backend category names to display labels */
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

function MemorySurface() {
  const [memories, setMemories] = useState([]);
  const [skills, setSkills]     = useState([]);
  const [filter, setFilter]     = useState('all');
  const [query, setQuery]       = useState('');
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch('/api/memory').then(r=>r.ok?r.json():{memories:[]}).catch(()=>({memories:[]})),
      fetch('/api/skills').then(r=>r.ok?r.json():{skills:[]}).catch(()=>({skills:[]})),
    ]).then(([memData, skillData]) => {
      setMemories(memData.memories || memData.memory || []);
      setSkills(skillData.skills || []);
      setLoading(false);
    });
  }, []);

  function displayTag(mem) {
    const raw = (mem.category || mem.categories?.[0] || 'fact').toLowerCase();
    return CAT_MAP[raw] || 'facts';
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

  /* Filter memories */
  const filtered = memories.filter(m => {
    const tag = displayTag(m);
    if (filter !== 'all' && tag !== filter) return false;
    if (query && !(m.text||'').toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  /* Group by display tag */
  const groups = {};
  filtered.forEach(m => {
    const t = displayTag(m);
    if (!groups[t]) groups[t] = [];
    groups[t].push(m);
  });

  async function toggleSkill(sk) {
    const newStatus = sk.status === 'active' ? 'inactive' : 'active';
    // Optimistic update
    setSkills(prev => prev.map(s => s.id===sk.id ? {...s,status:newStatus} : s));
    try {
      await fetch(`/api/skills/${sk.id}/toggle`, {
        method:'POST',
      });
    } catch(e) {
      // Revert on error
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

      {/* ── Filter bar ── */}
      <div style={{ height:48, flexShrink:0, background:'var(--nav-bg)',
        borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center',
        padding:'0 40px', gap:0 }}>
        {DISPLAY_TAGS.map(t => {
          const on = filter === t;
          return (
            <button key={t} onClick={() => setFilter(t)} style={{
              padding:'0 16px 0 0',
              fontFamily:'var(--font-b)', fontSize:13, fontStyle:'italic',
              color: on ? 'var(--text)' : 'var(--text-2)',
              borderBottom:`1.5px solid ${on ? 'var(--accent)' : 'transparent'}`,
              paddingBottom:10, marginBottom:-1,
              cursor:'pointer', transition:'color var(--t), border-color var(--t)',
              whiteSpace:'nowrap', flexShrink:0,
            }}>{t}</button>
          );
        })}
        {/* search */}
        <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:8,
          padding:'4px 12px', border:'1px solid var(--border-2)', borderRadius:8,
          background:'var(--thread-bg)' }}>
          <Ico n="search" size={12} color="var(--text-3)"/>
          <input value={query} onChange={e=>setQuery(e.target.value)}
            placeholder="Search memory…"
            style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text)', width:140 }}/>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>
        <div style={{ maxWidth:760, margin:'0 auto', padding:'32px 56px' }}>

          {/* Memory fragments */}
          <div style={{ marginBottom:40 }}>
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
                        <div style={{ display:'flex', gap:10 }}>
                          <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}>{relTime(m.timestamp)}</span>
                          {m.session_id && <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)', opacity:.5 }}>·</span>}
                          {m.session_id && <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}>{m.session_id.slice(0,8)}</span>}
                        </div>
                      </div>
                    </div>
                    {i < groups[tag].length-1 && <Rule/>}
                  </div>
                ))}
              </div>
            ))}
          </div>

          {/* Divider */}
          <div style={{ display:'flex', alignItems:'center', gap:14, marginBottom:32 }}>
            <Rule style={{ flex:1 }}/>
            <span style={{ fontSize:7, color:'var(--text-3)', letterSpacing:'.1em', opacity:.6 }}>◆</span>
            <Rule style={{ flex:1 }}/>
          </div>

          {/* Skills */}
          <div>
            <SectionLabel right={`${skills.filter(s=>s.status==='active').length} of ${skills.length} enabled`}
              style={{ marginBottom:16 }}>Skills</SectionLabel>

            {skills.length === 0 && (
              <p style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', fontStyle:'italic' }}>
                No skills found.
              </p>
            )}

            {skills.map((sk, i) => {
              const isOn = sk.enabled !== false;
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
        </div>
      </div>
    </div>
  );
}

window.V2Memory = { MemorySurface };
