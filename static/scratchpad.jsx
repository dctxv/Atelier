/* ====== Scratchpad — the "living margin" (§10.3) ======
 * Every line is evaluated live and locally: math, units, dates, base/hash/color,
 * tips, and variable references (`a = 5`, `b = a * 2`). No model, no network for
 * deterministic lines (one debounced call to the local-only eval endpoint).
 */
const { useState, useEffect, useRef } = React;

const SCRATCH_PLACEHOLDER = `2 + 2
15% of 240
100 km to miles
days until christmas
a = 12
b = a * 3
255 in hex
#8A5A34 to rgb`;

const LINE_H = 26;  // px — shared by editor + gutter so rows align

function ScratchpadSurface() {
  const [text, setText] = useState(() => {
    try { return localStorage.getItem('atl_scratchpad') || SCRATCH_PLACEHOLDER; }
    catch { return SCRATCH_PLACEHOLDER; }
  });
  const [results, setResults] = useState([]);
  const timer = useRef(null);

  useEffect(() => { try { localStorage.setItem('atl_scratchpad', text); } catch {} }, [text]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      fetch('/api/scratchpad/eval', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ text }),
      })
        .then(r => r.ok ? r.json() : { results: [] })
        .then(d => setResults(d.results || []))
        .catch(() => {});
    }, 280);
    return () => timer.current && clearTimeout(timer.current);
  }, [text]);

  const lines = text.split('\n');

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', background:'var(--thread-bg)' }} className="surface-enter">
      <div style={{ padding:'18px 28px 12px', borderBottom:'1px solid var(--border)' }}>
        <SectionLabel>Scratchpad</SectionLabel>
        <p style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)', marginTop:6 }}>
          Live local calc · units · dates · variables — nothing leaves your machine
        </p>
      </div>

      <div className="scroll" style={{ flex:1, overflow:'auto' }}>
        <div style={{ maxWidth:820, margin:'0 auto', padding:'24px 28px', display:'flex', gap:0 }}>
          {/* Editor */}
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            spellCheck={false}
            style={{
              flex:1, minHeight:`${Math.max(lines.length, 12) * LINE_H}px`,
              resize:'none', border:'none', outline:'none', background:'transparent',
              fontFamily:'var(--font-m)', fontSize:14, lineHeight:`${LINE_H}px`,
              color:'var(--text)', whiteSpace:'pre', overflowWrap:'normal', overflowX:'auto',
            }}
          />
          {/* Result gutter — aligned row-for-row */}
          <div style={{ width:200, flexShrink:0, borderLeft:'1px solid var(--border)',
            paddingLeft:16, marginLeft:16 }}>
            {lines.map((ln, i) => {
              const r = results[i];
              const val = r && r.value;
              const isAssign = r && r.kind === 'assign';
              const isAsk = r && r.kind === 'ask';
              return (
                <div key={i} style={{ height:LINE_H, display:'flex', alignItems:'center',
                  overflow:'hidden', whiteSpace:'nowrap' }}>
                  {val != null ? (
                    <span style={{ fontFamily:'var(--font-m)', fontSize:13.5,
                      color: isAssign ? 'var(--text-3)' : 'var(--accent-tx)',
                      overflow:'hidden', textOverflow:'ellipsis' }}>
                      {isAssign ? `${r.name} = ${val}` : `= ${val}`}
                    </span>
                  ) : isAsk ? (
                    <span style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)', fontStyle:'italic' }}>
                      ? ask in chat
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

window.V2Scratchpad = { ScratchpadSurface };
