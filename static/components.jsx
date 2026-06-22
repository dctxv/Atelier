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
  chevron: "M6 9l6 6 6-6",
  close:   "M18 6L6 18M6 6l12 12",
  book:    "M4 19.5A2.5 2.5 0 016.5 17H20M4 4h16v13H6.5A2.5 2.5 0 004 19.5z",
  toggle:  "M18 20V10M12 20V4M6 20v-6",
  pin:     "M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0zM12 10h.01",
  more:    "M12 13a1 1 0 100-2 1 1 0 000 2zM12 6a1 1 0 100-2 1 1 0 000 2zM12 20a1 1 0 100-2 1 1 0 000 2z",
  agents:  "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  check:   "M20 6L9 17l-5-5",
  copy:    "M8 4H6a2 2 0 00-2 2v12a2 2 0 002 2h8a2 2 0 002-2v-2M8 4h8l4 4v8a2 2 0 01-2 2H8a2 2 0 01-2-2V6a2 2 0 012-2z",
  link:    "M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71",
  sun:     "M12 7a5 5 0 110 10A5 5 0 0112 7zM12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42",
  moon:    "M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z",
  refresh: "M1 4v6h6M23 20v-6h-6M20.49 9A9 9 0 005.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 013.51 15",
  copy:    "M9 9h10v10H9zM5 15V5h10",
  link:    "M10 14a4 4 0 005.66 0l3-3a4 4 0 00-5.66-5.66l-1 1M14 10a4 4 0 00-5.66 0l-3 3a4 4 0 005.66 5.66l1-1",
  play:    "M8 5v14l11-7z",
  sparkle: "M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z",
  grid:    "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  trash:    "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6",
  projects: "M3 7l9-4 9 4-9 4-9-4zM3 12l9 4 9-4M3 17l9 4 9-4",
  globe:   "M12 2a10 10 0 100 20 10 10 0 000-20zM2 12h20M12 2a15 15 0 010 20M12 2a15 15 0 000 20",
  gear:    "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09a1.65 1.65 0 00-1.08-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09a1.65 1.65 0 001.51-1.08 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z",
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

/* ── Inline renderer: `code`, **bold**, [link](url), emoji upright ── */
function renderInline(text) {
  if (!text) return text;
  // Order: inline code, bold, markdown link, emoji
  const re = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|\[([^\]]+)\]\((https?:\/\/[^\)]+)\)|([☀-➿]|\uD83C[\uDF00-\uDFFF]|\uD83D[\uDC00-\uDEFF]|\uD83E[\uDD00-\uDDFF])/g;
  const out = [];
  let k = 0, pos = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > pos) out.push(text.slice(pos, m.index));
    if (m[1] !== undefined)
      out.push(<span key={k++} style={{ fontFamily:'var(--font-m)', fontSize:'0.875em',
        background:'var(--surface)', padding:'1px 5px', borderRadius:3,
        color:'var(--text)', fontStyle:'normal' }}>{m[1]}</span>);
    else if (m[2] !== undefined)
      out.push(<strong key={k++} style={{ fontWeight:700 }}>{m[2]}</strong>);
    else if (m[3] !== undefined && m[4] !== undefined)
      out.push(<a key={k++} href={m[4]} target="_blank" rel="noopener noreferrer"
        style={{ color:'var(--accent-tx)', textDecoration:'underline',
          textUnderlineOffset:2, fontStyle:'normal' }}>{m[3]}</a>);
    else
      out.push(<span key={k++} style={{ fontStyle:'normal' }}>{m[5]}</span>);
    pos = m.index + m[0].length;
  }
  if (pos < text.length) out.push(text.slice(pos));
  return out.length ? out : text;
}

/* ── Block parser ── */
function splitTableRow(line) {
  const cells = line.split('|').map(c => c.trim());
  const start = cells.length > 0 && cells[0] === '' ? 1 : 0;
  const end = cells.length > 0 && cells[cells.length-1] === '' ? cells.length-1 : cells.length;
  return cells.slice(start, end);
}

function parseBlocks(raw) {
  if (!raw) return [];
  const lines = raw.split('\n');
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    // Code fence — capture verbatim; unclosed fence = rest of text is code
    const fenceM = line.match(/^```(\w*)\s*$/);
    if (fenceM) {
      const lang = fenceM[1] || '';
      const codeLines = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) { codeLines.push(lines[i]); i++; }
      if (i < lines.length) i++; // consume closing fence
      blocks.push({ type:'code', lang, text:codeLines.join('\n') });
      continue;
    }

    // ATX heading
    const hdgM = line.match(/^(#{1,6})\s+(.+)$/);
    if (hdgM) {
      blocks.push({ type:'heading', level:hdgM[1].length, text:hdgM[2].trim() });
      i++; continue;
    }

    // Horizontal rule --- *** ___ (3+ identical chars, nothing else)
    if (/^([-*_])\1{2,}\s*$/.test(line.trim())) {
      blocks.push({ type:'hr' }); i++; continue;
    }

    // Table: pipe-row + separator row
    if (line.includes('|') && i+1 < lines.length) {
      const sep = lines[i+1];
      if (/^[\s|:\-]+$/.test(sep) && sep.includes('-') && sep.includes('|')) {
        const headers = splitTableRow(line);
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].includes('|')) { rows.push(splitTableRow(lines[i])); i++; }
        blocks.push({ type:'table', headers, rows });
        continue;
      }
    }

    // Unordered list (- or * + space + non-whitespace — won't match HR)
    if (/^\s*[-*]\s+\S/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+\S/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, '')); i++;
      }
      blocks.push({ type:'ulist', items }); continue;
    }

    // Ordered list (1. 1) 1·)
    if (/^\s*\d+[.)·]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)·]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)·]\s+/, '')); i++;
      }
      blocks.push({ type:'olist', items }); continue;
    }

    // Paragraph: consume non-blank lines until a block-starter appears
    const paraLines = [];
    while (i < lines.length) {
      const l = lines[i];
      if (!l.trim()) break;
      if (/^```/.test(l) || /^#{1,6}\s/.test(l) || /^([-*_])\1{2,}\s*$/.test(l.trim())) break;
      if (l.includes('|') && i+1 < lines.length) {
        const s = lines[i+1];
        if (/^[\s|:\-]+$/.test(s) && s.includes('-') && s.includes('|')) break;
      }
      if (/^\s*[-*]\s+\S/.test(l) || /^\s*\d+[.)·]\s+/.test(l)) break;
      paraLines.push(l); i++;
    }
    if (paraLines.length) blocks.push({ type:'paragraph', text:paraLines.join(' ') });
  }
  return blocks;
}

/* ── Mermaid diagram block ── */
let _mermaidCounter = 0;
let _mermaidReady = false;

function MermaidBlock({ code }) {
  const idRef = React.useRef(null);
  if (!idRef.current) idRef.current = 'm' + (++_mermaidCounter);

  const [svg, setSvg] = React.useState(null);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    if (!window.mermaid) { setFailed(true); return; }
    if (!_mermaidReady) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'base',
        themeVariables: {
          fontFamily: "'Lora', Georgia, serif",
          primaryColor: '#EDE6D8',
          primaryBorderColor: '#C4B09A',
          lineColor: '#8A5A34',
          primaryTextColor: '#18130E',
          mainBkg: '#F6F1E7',
          clusterBkg: '#EDE6D8',
          edgeLabelBackground: '#F6F1E7',
        },
        flowchart: { curve: 'linear' },
      });
      _mermaidReady = true;
    }
    let cancelled = false;
    mermaid.render(idRef.current, code)
      .then(({ svg: svgStr }) => { if (!cancelled) setSvg(svgStr); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [code]);

  const preStyle = {
    fontFamily:'var(--font-m)', fontSize:12.5, lineHeight:1.65,
    color:'var(--text)', background:'var(--surface)',
    padding:'12px 16px', borderRadius:8,
    overflowX:'auto', whiteSpace:'pre', margin:0,
    border:'1px solid var(--border-2)',
  };

  if (failed) return (
    <div>
      <p className="mermaid-fallback-note">Diagram couldn't render — showing source.</p>
      <pre style={preStyle}>{code}</pre>
    </div>
  );
  if (!svg) return <pre style={{ ...preStyle, color:'var(--text-3)' }}>{code}</pre>;
  return <div className="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}

/* ── Code block (own component so its hooks stay isolated from renderBlock's .map) ── */
function CodeBlock({ block, compact }) {
  const [copied, setCopied] = React.useState(false);
  function copyCode() {
    navigator.clipboard.writeText(block.text || '').then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 1800);
    }).catch(() => {});
  }
  return (
    <div style={{ marginBottom:compact?10:14 }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:4 }}>
        {block.lang
          ? <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
              letterSpacing:'.08em', textTransform:'uppercase' }}>{block.lang}</span>
          : <span/>}
        <button onClick={copyCode} style={{
          fontFamily:'var(--font-m)', fontSize:8.5, color: copied ? 'var(--accent-tx)' : 'var(--text-3)',
          padding:'2px 7px', border:'1px solid var(--border-2)', borderRadius:6,
          cursor:'pointer', background:'transparent', display:'flex', alignItems:'center', gap:4,
          transition:'color var(--t)',
        }}>
          <Ico n={copied ? 'check' : 'copy'} size={9} color="currentColor"/>
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre style={{
        fontFamily:'var(--font-m)', fontSize:12.5, lineHeight:1.65,
        color:'var(--text)', background:'var(--surface)',
        padding:compact?'10px 12px':'12px 16px', borderRadius:8,
        overflowX:'auto', whiteSpace:'pre', margin:0,
        border:'1px solid var(--border-2)',
      }}>{block.text}</pre>
    </div>
  );
}

/* ── Block renderer ── */
function renderBlock(block, idx, compact, bodyFs, bodyLh, streaming) {
  const mb = compact ? 10 : 13;
  switch (block.type) {
    case 'heading': {
      const lvl = block.level;
      const fontSizes = compact ? [17,15.5,14,13,12.5,12] : [24,20,17.5,16,15,14];
      const fs = fontSizes[lvl-1] || (compact ? 12 : 14);
      return (
        <p key={idx} style={{
          fontFamily:'var(--font-d)', fontSize:fs,
          fontWeight: lvl<=2 ? 500 : 400,
          fontStyle: lvl<=2 ? 'italic' : 'normal',
          color:'var(--text)', lineHeight:1.25,
          marginBottom: compact ? 8 : 10,
          marginTop: idx > 0 ? (compact ? 10 : 14) : 0,
        }}>{renderInline(block.text)}</p>
      );
    }
    case 'paragraph':
      return (
        <p key={idx} style={{ fontFamily:'var(--font-b)', fontSize:bodyFs, lineHeight:bodyLh,
          color:'var(--text)', marginBottom:mb }}>
          {renderInline(block.text)}
        </p>
      );
    case 'olist':
      return (
        <div key={idx} style={{ marginBottom:mb }}>
          {block.items.map((item, j) => (
            <div key={j} style={{ display:'flex', gap:compact?12:16, marginBottom:compact?5:7 }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--accent)',
                flexShrink:0, paddingTop:compact?3:4, letterSpacing:'.04em' }}>{j+1}.</span>
              <span style={{ fontFamily:'var(--font-b)', fontSize:bodyFs, lineHeight:bodyLh,
                color:'var(--text)' }}>{renderInline(item)}</span>
            </div>
          ))}
        </div>
      );
    case 'ulist':
      return (
        <div key={idx} style={{ marginBottom:mb }}>
          {block.items.map((item, j) => (
            <div key={j} style={{ display:'flex', gap:compact?12:16, marginBottom:compact?5:7 }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--accent)',
                flexShrink:0, paddingTop:compact?5:6 }}>–</span>
              <span style={{ fontFamily:'var(--font-b)', fontSize:bodyFs, lineHeight:bodyLh,
                color:'var(--text)' }}>{renderInline(item)}</span>
            </div>
          ))}
        </div>
      );
    case 'code': {
      if (block.lang === 'mermaid' && !streaming) {
        return (
          <div key={idx} style={{ marginBottom:compact?10:14 }}>
            <MermaidBlock code={block.text} />
          </div>
        );
      }
      return <CodeBlock key={idx} block={block} compact={compact} />;
    }
    case 'table':
      return (
        <div key={idx} style={{ marginBottom:compact?10:14, overflowX:'auto' }}>
          <table style={{ borderCollapse:'collapse', width:'100%' }}>
            <thead>
              <tr>
                {block.headers.map((h, j) => (
                  <th key={j} style={{
                    fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)',
                    letterSpacing:'.08em', textTransform:'uppercase',
                    padding:compact?'6px 10px':'8px 14px', textAlign:'left',
                    borderBottom:'1.5px solid var(--border-2)', whiteSpace:'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, ri) => (
                <tr key={ri} style={{ borderBottom:'1px solid var(--border)' }}>
                  {row.map((cell, ci) => (
                    <td key={ci} style={{
                      fontFamily:'var(--font-b)', fontSize:compact?13:bodyFs, lineHeight:1.55,
                      color:'var(--text)', padding:compact?'6px 10px':'8px 14px',
                    }}>{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case 'hr':
      return <div key={idx} style={{ height:1, background:'var(--rule)', margin:compact?'10px 0':'14px 0' }}/>;
    default:
      return null;
  }
}

/* ── AI block — lede + left accent bar ── */
function AiBlock({ text, model='', isLast, compact=false, streaming=false, timestamp }) {
  const ledeFs = compact ? 16.5 : 21;
  const bodyFs = compact ? 14   : 16;
  const bodyLh = compact ? 1.75 : 1.92;
  const rootRef = React.useRef(null);
  const [showTs, setShowTs] = React.useState(false);

  React.useEffect(() => {
    if (!streaming && window.renderMathInElement && rootRef.current) {
      window.renderMathInElement(rootRef.current, {
        delimiters: [
          { left:'$$',  right:'$$',  display:true  },
          { left:'\\[', right:'\\]', display:true  },
          { left:'\\(', right:'\\)', display:false },
        ],
        ignoredTags: ['script','noscript','style','textarea','pre','code'],
        throwOnError: false,
      });
    }
  }, [streaming, text]);

  const blocks = parseBlocks(text || '');

  // First block is italic Cormorant lede only when it is a plain paragraph
  let ledeText = '';
  let bodyBlocks = blocks;
  if (blocks.length > 0 && blocks[0].type === 'paragraph') {
    ledeText = blocks[0].text;
    bodyBlocks = blocks.slice(1);
  }

  return (
    <div className="fade-up" style={{ flexShrink:0 }}>
      {/* colophon */}
      <div
        onMouseEnter={() => setShowTs(true)}
        onMouseLeave={() => setShowTs(false)}
        style={{ display:'flex', alignItems:'center', gap:10, marginBottom: compact?12:18 }}
      >
        <ModelBadge model={model}/>
        <span style={{ color:'var(--text-3)', fontSize:10 }}>—</span>
        <span style={{ fontFamily:'var(--font-d)', fontSize:12.5, fontStyle:'italic', color:'var(--text-3)' }}>
          Atelier
        </span>
        {timestamp && (
          <span style={{
            fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
            marginLeft:'auto', opacity: showTs ? 0.7 : 0,
            transition:'opacity 0.15s ease', letterSpacing:'.04em',
          }}>
            {timestamp}
          </span>
        )}
      </div>
      {/* bar + content */}
      <div style={{ display:'flex', gap: compact?14:20 }}>
        <div style={{ width:1.5, background:'var(--bar)', borderRadius:1, flexShrink:0 }}/>
        <div ref={rootRef} style={{ flex:1 }}>
          {/* lede — italic Cormorant display paragraph */}
          {ledeText && (
            <p style={{ fontFamily:'var(--font-d)', fontSize:ledeFs, fontStyle:'italic',
              lineHeight: compact?1.62:1.68, color:'var(--text)',
              marginBottom: bodyBlocks.length ? (compact?13:18) : 0 }}>
              {renderInline(ledeText)}
            </p>
          )}
          {/* typed body blocks */}
          {bodyBlocks.map((block, i) => renderBlock(block, i, compact, bodyFs, bodyLh, streaming))}
          {/* streaming cursor */}
          {streaming && (
            <span style={{ display:'inline-block', width:2, height:18,
              background:'var(--accent)', animation:'writing 1.1s step-end infinite', marginLeft:2 }}/>
          )}
          {/* actions */}
          {isLast && !streaming && (
            <div style={{ display:'flex', gap:6, marginTop: compact?14:20 }}>
              <button onClick={() => navigator.clipboard.writeText(text || '')}
                style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)',
                  padding:'2px 9px', border:'1px solid var(--border-2)', borderRadius:10,
                  cursor:'pointer', background:'transparent' }}>Copy</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Card shell — shared visual register for all local-answer cards ── */
function _CardShell({ children, onAskAbout, label, style:sx }) {
  return (
    <div className="fade-up" style={{
      padding:'16px 20px', marginBottom:14,
      background:'var(--surface)', border:'1px solid var(--border-2)',
      borderRadius:12, flexShrink:0, ...sx,
    }}>
      {label && (
        <div style={{ fontFamily:'var(--font-m)', fontSize:8.5, color:'var(--text-3)',
          letterSpacing:'.1em', textTransform:'uppercase', marginBottom:10 }}>
          {label}
        </div>
      )}
      {children}
      {onAskAbout && (
        <button onClick={onAskAbout} style={{
          marginTop:12, fontFamily:'var(--font-m)', fontSize:9.5,
          color:'var(--accent-tx)', background:'var(--accent-bg)',
          border:'1px solid var(--accent-bd)', borderRadius:8,
          padding:'3px 10px', cursor:'pointer',
        }}>ask about this ↗</button>
      )}
    </div>
  );
}

/* ── Clock card (system-clock answer for time queries) ── */
function ClockCard({ data }) {
  if (!data) return null;
  return (
    <_CardShell label="Current Time">
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:20 }}>
        <span style={{
          fontFamily:'var(--font-m)', fontSize:30, fontWeight:400,
          letterSpacing:'-.02em', color:'var(--text)', lineHeight:1, whiteSpace:'nowrap',
        }}>{data.time}</span>
        <div style={{display:'flex',flexDirection:'column',alignItems:'flex-end',gap:4}}>
          <span style={{fontFamily:'var(--font-m)',fontSize:12,color:'var(--text-q)',letterSpacing:'.01em'}}>
            {data.date}
          </span>
          <span style={{fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',letterSpacing:'.04em'}}>
            {data.location}
          </span>
        </div>
      </div>
    </_CardShell>
  );
}

/* ── Math card ── */
function MathCard({ data, onAskAbout }) {
  if (!data) return null;
  return (
    <_CardShell label="Computed" onAskAbout={onAskAbout}>
      <div style={{ display:'flex', alignItems:'baseline', gap:16, flexWrap:'wrap' }}>
        <span style={{ fontFamily:'var(--font-m)', fontSize:26, fontWeight:400,
          color:'var(--text)', lineHeight:1 }}>{data.result}</span>
        <span style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)',
          fontStyle:'italic' }}>{data.expr}</span>
      </div>
    </_CardShell>
  );
}

/* ── Unit conversion card ── */
function UnitCard({ data, onAskAbout }) {
  if (!data) return null;
  return (
    <_CardShell label="Unit Conversion" onAskAbout={onAskAbout}>
      <div style={{ display:'flex', alignItems:'baseline', gap:12 }}>
        <span style={{ fontFamily:'var(--font-m)', fontSize:22, fontWeight:400,
          color:'var(--text)', lineHeight:1 }}>{data.result}</span>
      </div>
      {data.expr && (
        <div style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)',
          marginTop:6 }}>{data.expr}</div>
      )}
    </_CardShell>
  );
}

/* ── Stock card ── */
function StockCard({ data, onAskAbout }) {
  if (!data) return null;
  const change = data.change || 0;
  const pct    = data.percent_change || 0;
  const isUp   = change >= 0;
  const color  = isUp ? '#4caf7d' : '#e05454';
  const asOf   = data.as_of ? new Date(data.as_of * 1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : null;
  return (
    <_CardShell label={`Stock · ${data.symbol || data.kind || ''}`} onAskAbout={onAskAbout}>
      <div style={{ display:'flex', alignItems:'baseline', gap:14 }}>
        <span style={{ fontFamily:'var(--font-m)', fontSize:27, fontWeight:400,
          color:'var(--text)', lineHeight:1 }}>
          ${(data.current_price || 0).toFixed(2)}
        </span>
        <span style={{ fontFamily:'var(--font-m)', fontSize:13, color, fontVariantNumeric:'tabular-nums' }}>
          {isUp ? '+' : ''}{(change).toFixed(2)} ({isUp ? '+' : ''}{(pct).toFixed(2)}%)
        </span>
      </div>
      <div style={{ display:'flex', gap:20, marginTop:8, flexWrap:'wrap' }}>
        {data.low_day != null && (
          <span style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)' }}>
            Low ${(data.low_day).toFixed(2)}
          </span>
        )}
        {data.high_day != null && (
          <span style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)' }}>
            High ${(data.high_day).toFixed(2)}
          </span>
        )}
        {asOf && (
          <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)', marginLeft:'auto' }}>
            as of {asOf}
          </span>
        )}
      </div>
    </_CardShell>
  );
}

/* ── Weather card ── */
function WeatherCard({ data, onAskAbout }) {
  if (!data) return null;
  const temp = data.temperature_celsius != null ? Math.round(data.temperature_celsius) : '—';
  const feels = data.feels_like_celsius != null ? Math.round(data.feels_like_celsius) : null;
  return (
    <_CardShell label={`Weather · ${data.location || ''}`} onAskAbout={onAskAbout}>
      <div style={{ display:'flex', alignItems:'baseline', gap:12 }}>
        <span style={{ fontFamily:'var(--font-m)', fontSize:33, fontWeight:400,
          color:'var(--text)', lineHeight:1 }}>{temp}°C</span>
        <span style={{ fontFamily:'var(--font-b)', fontSize:15, fontStyle:'italic',
          color:'var(--text-q)', textTransform:'capitalize' }}>{data.condition}</span>
      </div>
      <div style={{ display:'flex', gap:16, marginTop:8, flexWrap:'wrap' }}>
        {feels != null && (
          <span style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)' }}>
            Feels {feels}°C
          </span>
        )}
        {data.humidity_percent != null && (
          <span style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)' }}>
            {data.humidity_percent}% humidity
          </span>
        )}
        {data.wind_speed_m_s != null && (
          <span style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)' }}>
            {data.wind_speed_m_s} m/s wind
          </span>
        )}
      </div>
    </_CardShell>
  );
}

/* ── Generic local-tool card (date, base conv, hash, color, tip) ── */
function LocalToolCard({ data, onAskAbout }) {
  if (!data) return null;
  const LABELS = {
    date: 'Date', base_conv: 'Base Conversion', hash: 'Hash', encode: 'Encode',
    color: 'Color', tip_split: 'Tip & Split', timezone_diff: 'Time Conversion',
  };
  const label = LABELS[data.kind] || 'Local Compute';
  return (
    <_CardShell label={label} onAskAbout={onAskAbout}>
      <div style={{ display:'flex', alignItems:'baseline', gap:12, flexWrap:'wrap' }}>
        <span style={{ fontFamily:'var(--font-m)', fontSize:20, fontWeight:400,
          color:'var(--text)', lineHeight:1.3, wordBreak:'break-all' }}>{data.result}</span>
      </div>
      {data.label && (
        <div style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)', marginTop:5 }}>
          {data.label}
        </div>
      )}
      {data.detail && (
        <div style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)', marginTop:3 }}>
          {data.detail}
        </div>
      )}
      {/* Color swatch */}
      {data.kind === 'color' && data.hex && (
        <div style={{
          marginTop:10, width:40, height:20, borderRadius:6,
          background: data.hex,
          border:'1px solid var(--border-2)',
        }}/>
      )}
    </_CardShell>
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

/* ── Provenance chips — the answer's grounding, made legible (§7.3) ── */
function ProvenanceChips({ prov, onNav }) {
  if (!prov) return null;
  const chips = [];
  if (prov.computed) chips.push({ icon:'sparkle', label:'computed' });
  if (prov.web)      chips.push({ icon:'globe',  label:`${prov.web} source${prov.web>1?'s':''}` });
  if (prov.memory)   chips.push({ icon:'memory', label:'memory' });
  (prov.docs || []).forEach(fn => chips.push({ icon:'files', label:fn }));
  (prov.sources || []).forEach(s => {
    if (s.kind === 'note')     chips.push({ icon:'notes',  label:'a note',     nav:'notes' });
    else if (s.kind === 'research') chips.push({ icon:'search', label:'your research', nav:'research' });
  });
  if (!chips.length) return null;
  return (
    <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginBottom:12 }}>
      {chips.map((c, i) => {
        const clickable = c.nav && onNav;
        return (
          <button key={i} disabled={!clickable}
            onClick={clickable ? () => onNav(c.nav) : undefined}
            title={clickable ? `Grounded in ${c.label} — open` : `Grounded in ${c.label}`}
            style={{ display:'flex', alignItems:'center', gap:5, padding:'3px 9px',
              borderRadius:20, border:'1px solid var(--border-2)', background:'var(--surface)',
              cursor: clickable ? 'pointer' : 'default', maxWidth:200 }}>
            <Ico n={c.icon} size={10} color="var(--text-3)"/>
            <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)',
              letterSpacing:'.02em', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              {c.label}
            </span>
          </button>
        );
      })}
    </div>
  );
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


Object.assign(window, {
  Ico, Pulse, ModelBadge, TurnDots, AiBlock, UserQuery, SectionLabel, Rule, EmptyState,
  WebSearchTrace, ClockCard, MathCard, UnitCard, StockCard, WeatherCard, LocalToolCard,
  ProvenanceChips, parseBlocks, renderBlock,
});
