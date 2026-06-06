/* ====== v2 shared components ====== */

/* ── Icons ── */
const IC = {
  chat:    "M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z",
  search:  "M11 5a6 6 0 110 12A6 6 0 0111 5zm5.2 9.8L21 21",
  memory:  "M12 2a5 5 0 015 5c0 2-.8 3.8-2 5l-1 3H8l-1-3a7 7 0 01-2-5 5 5 0 015-5zm-2 13h4",
  notes:   "M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6",
  tasks:   "M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11",
  files:   "M3 7h6l2 2h10v11H3V7z",
  plus:    "M12 5v14M5 12h14",
  send:    "M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z",
  attach:  "M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48",
  mic:     "M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3zM19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8",
  chevron: "M6 9l6 6 6-6",
  close:   "M18 6L6 18M6 6l12 12",
  book:    "M4 19.5A2.5 2.5 0 016.5 17H20M4 4h16v13H6.5A2.5 2.5 0 004 19.5z",
  toggle:  "M18 20V10M12 20V4M6 20v-6",
  pin:     "M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0zM12 10h.01",
  more:    "M12 13a1 1 0 100-2 1 1 0 000 2zM12 6a1 1 0 100-2 1 1 0 000 2zM12 20a1 1 0 100-2 1 1 0 000 2z",
  agents:  "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  check:   "M20 6L9 17l-5-5",
  sun:     "M12 7a5 5 0 110 10A5 5 0 0112 7zM12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42",
  moon:    "M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z",
  refresh: "M1 4v6h6M23 20v-6h-6M20.49 9A9 9 0 005.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 013.51 15",
  trash:   "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6",
  globe:   "M12 2a10 10 0 100 20 10 10 0 000-20zM2 12h20M12 2a15 15 0 010 20M12 2a15 15 0 000 20",
};

function Ico({ n, size=16, color='currentColor', style }) {
  const d = IC[n] || IC.more;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={style}>
      {d.split('M').filter(Boolean).map((s,i) => <path key={i} d={'M'+s}/>)}
    </svg>
  );
}

/* ── Pulse dot ── */
function Pulse({ size=6, style }) {
  return <span style={{ width:size, height:size, borderRadius:'50%', display:'inline-block',
    flexShrink:0, background:'var(--dot)', animation:'breathe 2.8s ease-in-out infinite', ...style }}/>;
}

/* ── Model badge ◆ model ── */
function ModelBadge({ model='opus' }) {
  const short = model.split('/').pop().split(':')[0].split('-').slice(0,2).join('-').toLowerCase();
  return (
    <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--accent-tx)',
      background:'var(--accent-bg)', border:'1px solid var(--accent-bd)',
      borderRadius:10, padding:'2px 9px', display:'inline-flex', alignItems:'center', gap:4 }}>
      ◆ {short || model}
    </span>
  );
}

/* ── Turn divider — rule + three dots ── */
function TurnDots() {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:14, flexShrink:0 }}>
      <div style={{ flex:1, height:1, background:'var(--rule)' }}/>
      <div style={{ display:'flex', gap:5 }}>
        {[0,1,2].map(i => (
          <span key={i} style={{ width:4, height:4, borderRadius:'50%',
            background: i===1 ? 'var(--accent)' : 'var(--text-3)',
            opacity: i===1 ? .5 : .28 }}/>
        ))}
      </div>
      <div style={{ flex:1, height:1, background:'var(--rule)' }}/>
    </div>
  );
}

/* ── Inline renderer: **bold** + emoji upright ── */
function renderInline(text) {
  if (!text) return text;
  // Match **bold** spans or common emoji (surrogate pairs + misc symbol blocks)
  const re = /\*\*([^*\n]+)\*\*|([☀-➿]|\uD83C[\uDF00-\uDFFF]|\uD83D[\uDC00-\uDEFF]|\uD83E[\uDD00-\uDDFF])/g;
  const out = [];
  let k = 0, i = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > i) out.push(text.slice(i, m.index));
    if (m[1] !== undefined)
      out.push(<strong key={k++} style={{ fontWeight:700 }}>{m[1]}</strong>);
    else
      out.push(<span key={k++} style={{ fontStyle:'normal' }}>{m[2]}</span>);
    i = m.index + m[0].length;
  }
  if (i < text.length) out.push(text.slice(i));
  return out.length ? out : text;
}

/* ── AI block — lede + left accent bar ── */
function AiBlock({ lede, body, model='', isLast, compact=false, streaming=false }) {
  const ledeFs = compact ? 16.5 : 21;
  const bodyFs = compact ? 14   : 16;
  const bodyLh = compact ? 1.75 : 1.92;
  const parts  = body ? body.split('\n\n') : [];
  const rootRef = React.useRef(null);

  React.useEffect(() => {
    if (!streaming && window.renderMathInElement && rootRef.current) {
      window.renderMathInElement(rootRef.current, {
        delimiters: [
          {left: '$$', right: '$$', display: true},
          {left: '\\[', right: '\\]', display: true},
          {left: '$', right: '$', display: false},
          {left: '\\(', right: '\\)', display: false}
        ],
        throwOnError: false
      });
    }
  }, [streaming, lede, body]);

  return (
    <div className="fade-up" style={{ flexShrink:0 }}>
      {/* colophon */}
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom: compact?12:18 }}>
        <ModelBadge model={model}/>
        <span style={{ color:'var(--text-3)', fontSize:10 }}>—</span>
        <span style={{ fontFamily:'var(--font-d)', fontSize:12.5, fontStyle:'italic', color:'var(--text-3)' }}>
          The Atelier
        </span>
      </div>
      {/* bar + content */}
      <div style={{ display:'flex', gap: compact?14:20 }}>
        <div style={{ width:1.5, background:'var(--bar)', borderRadius:1, flexShrink:0 }}/>
        <div ref={rootRef} style={{ flex:1 }}>
          {/* lede */}
          {lede && (
            <p style={{ fontFamily:'var(--font-d)', fontSize:ledeFs, fontStyle:'italic',
              lineHeight: compact?1.62:1.68, color:'var(--text)',
              marginBottom: parts.length ? (compact?13:18) : 0 }}>
              {renderInline(lede)}
            </p>
          )}
          {/* body paragraphs */}
          {parts.map((para, i) => {
            const mb = i < parts.length-1 ? (compact?10:13) : 0;
            const num = para.match(/^(\d+\s*[·.])\s+([\s\S]+)$/);
            if (num) return (
              <div key={i} style={{ display:'flex', gap:compact?12:16, marginBottom:mb }}>
                <span style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--accent)',
                  flexShrink:0, paddingTop:compact?3:4, letterSpacing:'.04em' }}>{num[1]}</span>
                <span style={{ fontFamily:'var(--font-b)', fontSize:bodyFs, lineHeight:bodyLh, color:'var(--text)' }}>{renderInline(num[2])}</span>
              </div>
            );
            return <p key={i} style={{ fontFamily:'var(--font-b)', fontSize:bodyFs, lineHeight:bodyLh,
              color:'var(--text)', marginBottom:mb }}>{renderInline(para)}</p>;
          })}
          {/* streaming cursor */}
          {streaming && (
            <span style={{ display:'inline-block', width:2, height:18,
              background:'var(--accent)', animation:'writing 1.1s step-end infinite', marginLeft:2 }}/>
          )}
          {/* actions */}
          {isLast && !streaming && (
            <div style={{ display:'flex', gap:6, marginTop: compact?14:20 }}>
              <button onClick={() => {
                const text = (lede ? lede + '\n\n' : '') + (body || '');
                navigator.clipboard.writeText(text);
              }} style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)', padding:'2px 9px', border:'1px solid var(--border-2)', borderRadius:10, cursor:'pointer', background:'transparent' }}>Copy</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Clock card (system-clock answer for time queries) ── */
function ClockCard({ data }) {
  if (!data) return null;
  return (
    <div className="fade-up" style={{
      display:'flex', alignItems:'center', justifyContent:'space-between',
      padding:'18px 22px', marginBottom:14,
      background:'var(--surface)', border:'1px solid var(--border-2)',
      borderRadius:12, gap:20, flexShrink:0,
    }}>
      {/* Time */}
      <span style={{
        fontFamily:'var(--font-d)', fontSize:38, fontWeight:500,
        letterSpacing:'-.01em', color:'var(--text)', lineHeight:1, whiteSpace:'nowrap',
      }}>
        {data.time}
      </span>
      {/* Date + location */}
      <div style={{display:'flex',flexDirection:'column',alignItems:'flex-end',gap:4}}>
        <span style={{fontFamily:'var(--font-m)',fontSize:12,color:'var(--text-q)',letterSpacing:'.01em'}}>
          {data.date}
        </span>
        <span style={{fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',letterSpacing:'.04em'}}>
          {data.location}
        </span>
      </div>
    </div>
  );
}

/* ── Web search trace (shows the real query + real sources used) ── */
function _domain(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); }
  catch { return (url || '').replace(/^https?:\/\//, '').split('/')[0].replace(/^www\./, ''); }
}
function _relTime(epoch) {
  if (!epoch) return '';
  const d = Date.now()/1000 - epoch;
  if (d < 3600) return Math.max(1,Math.round(d/60))+'m ago';
  if (d < 86400) return Math.round(d/3600)+'h ago';
  if (d < 86400*30) return Math.round(d/86400)+'d ago';
  try { return new Date(epoch*1000).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}); }
  catch { return ''; }
}

function WebSearchTrace({ trace, searching=false }) {
  const [open, setOpen] = React.useState(false);
  const [showAll, setShowAll] = React.useState(false);
  const results = (trace && trace.results) || [];
  const shown = showAll ? results : results.slice(0, 3);
  const extra = results.length - shown.length;
  const label = searching ? 'Searching the web' : 'Searched the web';

  return (
    <div className="fade-up" style={{ flexShrink:0, marginBottom:14,
      border:'1px solid var(--border-2)', borderRadius:10, overflow:'hidden',
      background:'var(--surface)' }}>
      {/* header */}
      <button onClick={()=>setOpen(o=>!o)} style={{ width:'100%', display:'flex',
        alignItems:'center', gap:9, padding:'9px 12px', cursor:'pointer',
        background:'transparent', transition:'background var(--t)' }}>
        {searching
          ? <Pulse size={11} style={{ background:'var(--accent)' }}/>
          : <Ico n="globe" size={13} color="var(--accent-tx)"/>}
        <span style={{ fontFamily:'var(--font-m)', fontSize:11, letterSpacing:'.02em',
          color:'var(--text-q)', flex:1, textAlign:'left' }}>
          {label}
          {!searching && results.length>0 &&
            <span style={{ color:'var(--text-3)' }}> · {results.length} source{results.length>1?'s':''}</span>}
        </span>
        {trace && trace.providers && trace.providers.length>0 && (
          <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
            border:'1px solid var(--border-2)', borderRadius:6, padding:'1px 6px',
            textTransform:'capitalize' }}>
            {trace.from_cache ? 'cache' : trace.providers[0]}
          </span>
        )}
        <Ico n="chevron" size={10} color="var(--text-3)"
          style={{ transform:open?'rotate(180deg)':'none', transition:'transform var(--t)' }}/>
      </button>

      {open && trace && (
        <div style={{ borderTop:'1px solid var(--border)', padding:'10px 12px' }}>
          {/* the actual query */}
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
            <Ico n="search" size={11} color="var(--text-3)"/>
            <span style={{ fontFamily:'var(--font-b)', fontSize:12.5, fontStyle:'italic',
              color:'var(--text-q)' }}>{trace.query}</span>
          </div>
          {/* real sources */}
          <div style={{ display:'flex', flexDirection:'column', gap:2 }}>
            {shown.map((r,i) => {
              const dom = _domain(r.url);
              return (
                <a key={i} href={r.url} target="_blank" rel="noreferrer"
                  style={{ display:'flex', alignItems:'center', gap:9, padding:'6px 6px',
                    borderRadius:7, textDecoration:'none', transition:'background var(--t)' }}
                  onMouseEnter={e=>e.currentTarget.style.background='var(--accent-bg)'}
                  onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                  <img src={`https://icons.duckduckgo.com/ip3/${dom}.ico`} width="15" height="15"
                    style={{ borderRadius:3, flexShrink:0, opacity:.9 }}
                    onError={e=>{e.target.style.visibility='hidden';}}/>
                  <span style={{ fontFamily:'var(--font-b)', fontSize:12.5, color:'var(--text)',
                    overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1 }}>
                    {r.title || dom}
                  </span>
                  {r.published_at && (
                    <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)', flexShrink:0 }}>
                      {_relTime(r.published_at)}
                    </span>
                  )}
                  <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)',
                    flexShrink:0, maxWidth:140, overflow:'hidden', textOverflow:'ellipsis',
                    whiteSpace:'nowrap' }}>{dom}</span>
                </a>
              );
            })}
          </div>
          {extra>0 && (
            <button onClick={()=>setShowAll(true)} style={{ marginTop:6, marginLeft:6,
              fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--accent-tx)',
              cursor:'pointer', background:'transparent' }}>
              +{extra} more
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ── User query ── */
function UserQuery({ text, compact=false }) {
  return (
    <div className="fade-up" style={{ display:'flex', justifyContent:'flex-end',
      alignItems:'flex-start', gap:10, flexShrink:0 }}>
      <div style={{ maxWidth: compact?'82%':'52%', display:'flex', flexDirection:'column',
        alignItems:'flex-end', gap:4 }}>
        <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--accent)',
          letterSpacing:'.1em', textTransform:'uppercase' }}>Q —</span>
        <p style={{ fontFamily:'var(--font-b)', fontSize:compact?13.5:15, fontStyle:'italic',
          lineHeight:1.62, color:'var(--text-q)', textAlign:'right' }}>{renderInline(text)}</p>
      </div>
      <div style={{ width:compact?20:24, height:compact?20:24, borderRadius:'50%', flexShrink:0,
        marginTop:18, background:'var(--accent-bg)', border:'1px solid var(--accent-bd)',
        display:'grid', placeItems:'center',
        fontFamily:'var(--font-m)', fontSize:compact?7.5:8.5, color:'var(--accent-tx)' }}>A</div>
    </div>
  );
}

/* ── Section label (UPPERCASE MONO) ── */
function SectionLabel({ children, right, style }) {
  return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', ...style }}>
      <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
        letterSpacing:'.14em', textTransform:'uppercase' }}>{children}</span>
      {right && <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--accent-tx)' }}>{right}</span>}
    </div>
  );
}

/* ── Simple thin rule ── */
function Rule({ style }) {
  return <div style={{ height:1, background:'var(--rule)', flexShrink:0, ...style }}/>;
}

/* ── Empty state placeholder ── */
function EmptyState({ icon='more', title, subtitle }) {
  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center',
      justifyContent:'center', gap:12, opacity:.4, padding:40 }}>
      <Ico n={icon} size={28} color="var(--text-3)"/>
      {title && <span style={{ fontFamily:'var(--font-d)', fontSize:22, fontStyle:'italic',
        color:'var(--text)' }}>{title}</span>}
      {subtitle && <span style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)',
        letterSpacing:'.1em', textTransform:'uppercase' }}>{subtitle}</span>}
    </div>
  );
}

Object.assign(window, { Ico, Pulse, ModelBadge, TurnDots, AiBlock, UserQuery, SectionLabel, Rule, EmptyState, WebSearchTrace, ClockCard });
