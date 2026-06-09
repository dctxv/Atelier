/* ====== v2 shell — LeftRail + ChatTabBar ====== */
const { useRef, useEffect, useState } = React;

const NAV = [
  { id:'chat',      icon:'chat'     },
  { id:'projects',  icon:'projects' },
  { id:'research',  icon:'search'   },
  { id:'memory',    icon:'memory'   },
  { id:'notes',     icon:'notes'    },
  { id:'scratchpad',icon:'sparkle'  },
  { id:'tasks',     icon:'tasks'    },
  { id:'documents', icon:'book'     },
  { id:'files',     icon:'files'    },
  { id:'settings',  icon:'gear'     },
];

function LeftRail({ active, onNav, theme, onTheme }) {
  return (
    <div style={{
      width:54, flexShrink:0, height:'100%',
      background:'var(--surface)', borderRight:'1px solid var(--border)',
      display:'flex', flexDirection:'column', alignItems:'center', padding:'0 0 16px',
    }}>
      <div style={{ width:'100%', height:52, display:'flex', alignItems:'center',
        justifyContent:'center', borderBottom:'1px solid var(--border)', marginBottom:12, flexShrink:0 }}>
        <div style={{ width:30, height:30, borderRadius:7, background:'var(--accent-bg)',
          border:'1px solid var(--accent-bd)', display:'grid', placeItems:'center' }}>
          <span style={{ fontFamily:'var(--font-d)', fontSize:19, fontWeight:500,
            color:'var(--accent-tx)', lineHeight:1 }}>A</span>
        </div>
      </div>

      <div style={{ flex:1, display:'flex', flexDirection:'column', gap:3,
        width:'100%', padding:'0 7px' }}>
        {NAV.map(item => {
          const on = item.id === active;
          return (
            <button key={item.id} title={item.id} onClick={() => onNav(item.id)} style={{
              width:'100%', height:40, borderRadius:8, display:'grid', placeItems:'center',
              background: on ? 'var(--accent-bg)' : 'transparent',
              border: `1px solid ${on ? 'var(--accent-bd)' : 'transparent'}`,
              color: on ? 'var(--accent-tx)' : 'var(--text-3)',
              transition:'all var(--t)',
            }}>
              <Ico n={item.icon} size={15} color="currentColor"/>
            </button>
          );
        })}
      </div>

      <button onClick={onTheme} title="Toggle theme" style={{
        width:36, height:36, borderRadius:9, marginBottom:8,
        border:'1px solid var(--border-2)', display:'grid', placeItems:'center',
        color:'var(--text-3)', transition:'all var(--t)',
      }}>
        <Ico n={theme === 'natural' ? 'moon' : 'sun'} size={14} color="currentColor"/>
      </button>

      <Pulse size={6}/>
    </div>
  );
}

/* ── Scrollable chat session tab bar ── */
function ChatTabBar({ tabs, active, onSelect, onDelete, onNew }) {
  const scrollRef = useRef(null);
  const dragging  = useRef(false);
  const startX    = useRef(0);
  const startScroll = useRef(0);
  const [hoveredId, setHoveredId] = useState(null);

  /* Non-passive wheel listener — intercept vertical scroll, redirect to horizontal */
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const handler = (e) => {
      e.preventDefault();
      el.scrollLeft += (e.deltaY !== 0 ? e.deltaY : e.deltaX);
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, []);

  /* Scroll active tab into view */
  useEffect(() => {
    if (!scrollRef.current || !active) return;
    const el = scrollRef.current.querySelector('[data-active="true"]');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
  }, [active]);

  /* Click-drag scroll */
  function handleMouseDown(e) {
    if (e.button !== 0) return;
    if (e.target.closest('[data-action]')) return;
    dragging.current = true;
    startX.current = e.clientX;
    startScroll.current = scrollRef.current ? scrollRef.current.scrollLeft : 0;
    e.preventDefault();
  }

  useEffect(() => {
    const onMove = (e) => {
      if (!dragging.current || !scrollRef.current) return;
      scrollRef.current.scrollLeft = startScroll.current - (e.clientX - startX.current);
    };
    const onUp = () => { dragging.current = false; };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  return (
    <div style={{ height:48, flexShrink:0, background:'var(--nav-bg)',
      borderBottom:'1px solid var(--border)', display:'flex', alignItems:'stretch',
      overflow:'hidden' }}>

      {/* Left padding */}
      <div style={{ width:56, flexShrink:0 }}/>

      {/* Scrollable tab strip */}
      <div ref={scrollRef} onMouseDown={handleMouseDown}
        style={{ flex:1, display:'flex', alignItems:'flex-end', overflow:'hidden',
          cursor: dragging.current ? 'grabbing' : 'grab', userSelect:'none' }}>
        {tabs.map((tab, idx) => {
          const on = tab.id === active;
          const hov = hoveredId === tab.id;
          return (
            <div key={tab.id} data-active={on ? 'true' : 'false'}
              onMouseEnter={() => setHoveredId(tab.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{ display:'flex', alignItems:'center', flexShrink:0,
                padding:'0 0 10px 0', marginRight:20, position:'relative' }}>
              {/* Tab label */}
              <button onClick={() => onSelect(tab.id)} style={{
                display:'flex', alignItems:'center', gap:5,
                fontFamily:'var(--font-b)', fontSize:13.5, fontStyle:'italic',
                color: on ? 'var(--text)' : 'var(--text-2)',
                borderBottom:`1.5px solid ${on ? 'var(--accent)' : 'transparent'}`,
                cursor:'pointer', whiteSpace:'nowrap',
                transition:'color var(--t), border-color var(--t)',
                paddingBottom:2,
              }}>
                <span style={{ fontFamily:'var(--font-m)', fontSize:8.5,
                  color: on ? 'var(--accent)' : 'var(--text-3)', letterSpacing:'.04em' }}>
                  {String(idx+1).padStart(2,'0')} ·
                </span>
                {tab.label}
              </button>
              {/* Delete × */}
              {onDelete && (
                <button data-action="delete"
                  onClick={(e) => { e.stopPropagation(); onDelete(tab.id); }}
                  title="Delete"
                  style={{ width:14, height:14, borderRadius:'50%', flexShrink:0,
                    display:'grid', placeItems:'center', marginLeft:5,
                    color:'var(--text-3)', cursor:'pointer',
                    opacity: hov ? 0.75 : 0,
                    transition:'opacity var(--t)',
                    pointerEvents: hov ? 'auto' : 'none',
                  }}>
                  <Ico n="close" size={9} color="currentColor"/>
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* New session button */}
      <div style={{ padding:'0 14px', display:'flex', alignItems:'center',
        flexShrink:0, borderLeft:'1px solid var(--border)' }}>
        <button onClick={onNew} title="New conversation"
          style={{ width:24, height:24, borderRadius:7,
            display:'grid', placeItems:'center', border:'1px solid var(--border-2)',
            color:'var(--text-3)', cursor:'pointer' }}>
          <Ico n="plus" size={12} color="currentColor"/>
        </button>
      </div>
    </div>
  );
}

/* ── Generic horizontal tab nav (research / other surfaces) ── */
function TabNav({ tabs, active, onSelect, right, style }) {
  return (
    <div style={{ height:48, flexShrink:0, background:'var(--nav-bg)',
      borderBottom:'1px solid var(--border)', display:'flex', alignItems:'flex-end',
      padding:'0 56px', gap:0, overflow:'hidden', ...style }}>
      {tabs.map((tab, idx) => {
        const on = tab.id === active;
        return (
          <button key={tab.id} onClick={() => onSelect(tab.id)} style={{
            display:'flex', alignItems:'center', gap:7, padding:'0 22px 10px 0',
            fontFamily:'var(--font-b)', fontSize:13.5, fontStyle:'italic',
            color: on ? 'var(--text)' : 'var(--text-2)',
            borderBottom:`1.5px solid ${on ? 'var(--accent)' : 'transparent'}`,
            cursor:'pointer', whiteSpace:'nowrap', flexShrink:0,
            transition:'color var(--t), border-color var(--t)',
          }}>
            {tab.live && <Pulse size={5}/>}
            <span style={{ fontFamily:'var(--font-m)', fontSize:8.5,
              color: on ? 'var(--accent)' : 'var(--text-3)', marginRight:2, letterSpacing:'.04em' }}>
              {String(idx+1).padStart(2,'0')} ·
            </span>
            {tab.label}
          </button>
        );
      })}
      {right && <div style={{ marginLeft:'auto', paddingBottom:10, display:'flex', alignItems:'center', gap:8 }}>{right}</div>}
    </div>
  );
}

/* ── Split layout helper ── */
function SplitLayout({ left, right, leftWidth=200 }) {
  return (
    <div style={{ display:'flex', height:'100%', overflow:'hidden' }}>
      <div style={{ width:leftWidth, flexShrink:0, background:'var(--panel-bg)',
        borderRight:'1px solid var(--border)', display:'flex', flexDirection:'column', overflow:'hidden' }}>
        {left}
      </div>
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
        {right}
      </div>
    </div>
  );
}

Object.assign(window, { LeftRail, ChatTabBar, TabNav, SplitLayout });
