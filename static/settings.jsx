/* ====== Settings surface — Atelier ======
 *
 * Scrollable settings page that composes the shared section components.
 * Desktop: left-rail section nav + right content area.
 * Mobile (≤768px): stacked accordion layout.
 */
const { useState, useEffect, useRef, useCallback } = React;

const { EndpointSection, ModelSection, PersonaSection } = window.AtelierSections;

const SECTIONS = [
  { id:'endpoints', label:'Endpoints',     icon:'plus'   },
  { id:'models',    label:'Models',        icon:'chat'   },
  { id:'persona',   label:'System Prompt', icon:'notes'  },
  { id:'memory',    label:'Memory',        icon:'memory' },
];

// ── Memory tier section ───────────────────────────────────────────────────────

const TIER_LABELS = {
  basic:      { title:'Basic',      cost:'< $0.50/mo',    desc:'Extracts and stores facts. No background jobs.' },
  reflective: { title:'Reflective', cost:'$1.00–2.00/mo', desc:'Adds conflict detection and goal staleness checks.' },
  prescient:  { title:'Prescient',  cost:'$2.00–5.00/mo', desc:'Adds hypothesis generation, drift analysis, and narrative.' },
};

function MemoryTierSection() {
  const [tier, setTier]       = useState(null);   // current depth string or null
  const [selected, setSelected] = useState(null); // radio selection
  const [saving, setSaving]   = useState(false);
  const [saved, setSaved]     = useState(false);

  useEffect(() => {
    fetch('/api/memory/tier')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          const depth = d.tier_selected ? (d.depth || 'basic') : null;
          setTier(depth);
          setSelected(depth);
        }
      })
      .catch(() => {});
  }, []);

  async function handleSave() {
    if (!selected || selected === tier) return;
    setSaving(true);
    try {
      await fetch('/api/memory/tier', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ depth: selected }),
      });
      setTier(selected);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch(e) {}
    setSaving(false);
  }

  const isUpgrade = tier && selected && ['basic','reflective','prescient'].indexOf(selected) > ['basic','reflective','prescient'].indexOf(tier);
  const isDowngrade = tier && selected && ['basic','reflective','prescient'].indexOf(selected) < ['basic','reflective','prescient'].indexOf(tier);

  return (
    <div id="section-memory" style={{ marginBottom: 40 }}>
      <SectionLabel style={{ marginBottom: 20 }}>Memory Tier</SectionLabel>

      {tier === null && (
        <p style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', fontStyle:'italic' }}>
          No tier selected yet. Visit the Memory page to set one up.
        </p>
      )}

      {tier !== null && (
        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          {Object.entries(TIER_LABELS).map(([key, info]) => {
            const on = selected === key;
            return (
              <label key={key} style={{
                display:'flex', alignItems:'flex-start', gap:14, padding:'14px 16px',
                border:`1px solid ${on ? 'var(--accent-bd)' : 'var(--border-2)'}`,
                borderRadius:8, cursor:'pointer',
                background: on ? 'var(--accent-bg)' : 'var(--nav-bg)',
                transition:'all var(--t)',
              }}>
                <input type="radio" name="memory_tier" value={key}
                  checked={on} onChange={() => setSelected(key)}
                  style={{ marginTop:3, accentColor:'var(--accent)', flexShrink:0 }}/>
                <div style={{ flex:1 }}>
                  <div style={{ display:'flex', alignItems:'baseline', gap:10, marginBottom:2 }}>
                    <span style={{ fontFamily:'var(--font-b)', fontSize:14, fontStyle:'italic',
                      color: on ? 'var(--text)' : 'var(--text-2)' }}>{info.title}</span>
                    <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
                      padding:'2px 6px', border:'1px solid var(--border)', borderRadius:3 }}>
                      ~{info.cost}
                    </span>
                    {key === tier && (
                      <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--accent)',
                        letterSpacing:'.08em', textTransform:'uppercase' }}>current</span>
                    )}
                  </div>
                  <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)', lineHeight:1.55 }}>
                    {info.desc}
                  </p>
                </div>
              </label>
            );
          })}

          {selected !== tier && (
            <div style={{ marginTop:6, padding:'12px 16px',
              border:'1px solid var(--border-2)', borderRadius:8, background:'var(--nav-bg)',
              display:'flex', alignItems:'center', justifyContent:'space-between', gap:16 }}>
              <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)', lineHeight:1.55 }}>
                {isUpgrade
                  ? 'Upgrading takes effect immediately — new, richer processing begins.'
                  : isDowngrade
                    ? 'Downgrading stops further higher-tier processing. Existing memories are kept.'
                    : ''}
              </p>
              <button onClick={handleSave} disabled={saving} style={{
                fontFamily:'var(--font-b)', fontSize:12, fontStyle:'italic',
                padding:'7px 18px', borderRadius:6,
                background:'var(--accent)', color:'#fff', border:'none',
                cursor: saving ? 'wait' : 'pointer', flexShrink:0,
                opacity: saving ? 0.7 : 1, transition:'opacity var(--t)',
              }}>
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          )}

          {saved && (
            <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--accent)', marginTop:4 }}>
              Tier updated.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function SettingsSurface({ initialSection }) {
  const [config, setConfig]       = useState(null);
  const [loading, setLoading]     = useState(true);
  const [activeSection, setActive] = useState(initialSection || 'endpoints');
  const contentRef = useRef(null);

  const fetchConfig = useCallback(async () => {
    try {
      const resp = await fetch('/api/config');
      const data = await resp.json();
      setConfig(data);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { fetchConfig(); }, []);

  // Deep-link: scroll to section when initialSection changes
  useEffect(() => {
    if (initialSection) {
      setActive(initialSection);
      const el = document.getElementById(`section-${initialSection}`);
      if (el) el.scrollIntoView({ behavior:'smooth', block:'start' });
    }
  }, [initialSection]);

  function handleSectionClick(id) {
    setActive(id);
    const el = document.getElementById(`section-${id}`);
    if (el) el.scrollIntoView({ behavior:'smooth', block:'start' });
  }

  if (loading || !config) {
    return (
      <div style={{flex:1,display:'flex',alignItems:'center',justifyContent:'center'}}>
        <Pulse size={10}/>
      </div>
    );
  }

  const sectionProps = { mode:'settings', config, onConfigChange:fetchConfig };

  // Mobile check via matchMedia
  const isMobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;

  if (isMobile) {
    return (
      <div className="surface-enter" style={{display:'flex',flexDirection:'column',height:'100%',overflow:'hidden'}}>
        {/* Header */}
        <div style={{height:52,flexShrink:0,background:'var(--nav-bg)',
          borderBottom:'1px solid var(--border)',display:'flex',alignItems:'center',
          padding:'0 20px',gap:10}}>
          <Ico n="gear" size={15} color="var(--accent-tx)"/>
          <span style={{fontFamily:'var(--font-d)',fontSize:20,fontStyle:'italic',
            color:'var(--text)'}}>Settings</span>
        </div>
        {/* Stacked sections */}
        <div className="scroll" style={{flex:1,padding:'16px 16px 40px'}}>
          <EndpointSection {...sectionProps} />
          <ModelSection {...sectionProps} />
          <PersonaSection {...sectionProps} />
          <MemoryTierSection/>
        </div>
      </div>
    );
  }

  return (
    <div className="surface-enter" style={{display:'flex',flexDirection:'column',height:'100%',overflow:'hidden'}}>
      {/* Header bar */}
      <div style={{height:52,flexShrink:0,background:'var(--nav-bg)',
        borderBottom:'1px solid var(--border)',display:'flex',alignItems:'center',
        padding:'0 32px',gap:10}}>
        <Ico n="gear" size={15} color="var(--accent-tx)"/>
        <span style={{fontFamily:'var(--font-d)',fontSize:20,fontStyle:'italic',
          color:'var(--text)'}}>Settings</span>
      </div>

      {/* Body: sidebar + content */}
      <div style={{flex:1,display:'flex',overflow:'hidden'}}>
        {/* Section nav rail */}
        <div style={{width:200,flexShrink:0,background:'var(--panel-bg)',
          borderRight:'1px solid var(--border)',padding:'20px 0',
          display:'flex',flexDirection:'column',gap:2}}>
          {SECTIONS.map(s => {
            const on = s.id === activeSection;
            return (
              <button key={s.id} onClick={()=>handleSectionClick(s.id)} style={{
                display:'flex',alignItems:'center',gap:10,padding:'10px 20px',
                background:on?'var(--accent-bg)':'transparent',
                borderLeft:`2.5px solid ${on?'var(--accent)':'transparent'}`,
                cursor:'pointer',transition:'all var(--t)',
                width:'100%',textAlign:'left',
              }}>
                <Ico n={s.icon} size={13} color={on?'var(--accent-tx)':'var(--text-3)'}/>
                <span style={{fontFamily:'var(--font-b)',fontSize:13.5,fontStyle:'italic',
                  color:on?'var(--text)':'var(--text-2)'}}>
                  {s.label}
                </span>
              </button>
            );
          })}

        </div>

        {/* Content area */}
        <div ref={contentRef} className="scroll" style={{flex:1,
          padding:'28px 40px 60px',maxWidth:680}}>
          <EndpointSection {...sectionProps} />
          <ModelSection {...sectionProps} />
          <PersonaSection {...sectionProps} />
          <MemoryTierSection/>
        </div>
      </div>
    </div>
  );
}

window.SettingsSurface = SettingsSurface;
