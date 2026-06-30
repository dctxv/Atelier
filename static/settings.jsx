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
];

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
        </div>
      </div>
    </div>
  );
}

window.SettingsSurface = SettingsSurface;
