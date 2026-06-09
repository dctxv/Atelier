/* ====== /play — fully client-side minigames (no backend, no model) ======
 * §8.2 of the chat/search hardening plan: a discoverable delight layer,
 * opened from the command palette, never auto-triggered.
 */
const { useState, useEffect, useRef, useCallback } = React;

/* ── 2048 ── */
function emptyGrid() { return Array.from({ length: 4 }, () => [0, 0, 0, 0]); }
function cloneGrid(g) { return g.map(r => r.slice()); }
function spawn(g) {
  const empty = [];
  for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) if (!g[r][c]) empty.push([r, c]);
  if (!empty.length) return g;
  const [r, c] = empty[Math.floor(Math.random() * empty.length)];
  g[r][c] = Math.random() < 0.9 ? 2 : 4;
  return g;
}
function slideRow(row) {
  let arr = row.filter(v => v);
  let gained = 0;
  for (let i = 0; i < arr.length - 1; i++) {
    if (arr[i] === arr[i + 1]) { arr[i] *= 2; gained += arr[i]; arr[i + 1] = 0; }
  }
  arr = arr.filter(v => v);
  while (arr.length < 4) arr.push(0);
  return { row: arr, gained };
}
function rotate(g) {
  const n = emptyGrid();
  for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) n[c][3 - r] = g[r][c];
  return n;
}
function move(grid, dir) {
  let g = cloneGrid(grid);
  const rots = { left: 0, up: 3, right: 2, down: 1 }[dir];
  for (let i = 0; i < rots; i++) g = rotate(g);
  let gained = 0, moved = false;
  for (let r = 0; r < 4; r++) {
    const res = slideRow(g[r]);
    if (res.row.some((v, c) => v !== g[r][c])) moved = true;
    g[r] = res.row; gained += res.gained;
  }
  for (let i = 0; i < (4 - rots) % 4; i++) g = rotate(g);
  return { grid: g, gained, moved };
}
function hasMoves(g) {
  for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) {
    if (!g[r][c]) return true;
    if (c < 3 && g[r][c] === g[r][c + 1]) return true;
    if (r < 3 && g[r][c] === g[r + 1][c]) return true;
  }
  return false;
}
const TILE_BG = {
  0:'var(--surface)', 2:'rgba(138,90,52,.10)', 4:'rgba(138,90,52,.16)',
  8:'rgba(138,90,52,.26)', 16:'rgba(138,90,52,.38)', 32:'rgba(138,90,52,.5)',
  64:'rgba(138,90,52,.62)', 128:'rgba(138,90,52,.72)', 256:'rgba(138,90,52,.82)',
  512:'rgba(138,90,52,.9)', 1024:'var(--accent)', 2048:'var(--accent)',
};

function Game2048() {
  const [grid, setGrid] = useState(() => spawn(spawn(emptyGrid())));
  const [score, setScore] = useState(0);
  const [over, setOver] = useState(false);
  const gridRef = useRef(grid);
  gridRef.current = grid;

  const doMove = useCallback((dir) => {
    if (over) return;
    const { grid: ng, gained, moved } = move(gridRef.current, dir);
    if (!moved) return;
    spawn(ng);
    setGrid(ng); setScore(s => s + gained);
    if (!hasMoves(ng)) setOver(true);
  }, [over]);

  useEffect(() => {
    const onKey = (e) => {
      const m = { ArrowLeft:'left', ArrowRight:'right', ArrowUp:'up', ArrowDown:'down' }[e.key];
      if (m) { e.preventDefault(); doMove(m); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [doMove]);

  function reset() { setGrid(spawn(spawn(emptyGrid()))); setScore(0); setOver(false); }

  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:14 }}>
      <div style={{ display:'flex', justifyContent:'space-between', width:300, alignItems:'center' }}>
        <span style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)' }}>
          Score <b style={{ color:'var(--accent-tx)' }}>{score}</b>
        </span>
        <button onClick={reset} style={btnStyle}>New game</button>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 68px)', gap:8,
        padding:8, background:'var(--panel-bg)', borderRadius:10, position:'relative' }}>
        {grid.flat().map((v, i) => (
          <div key={i} style={{ width:68, height:68, borderRadius:7, display:'grid',
            placeItems:'center', background:TILE_BG[v] || 'var(--accent)',
            transition:'background .12s' }}>
            {v ? <span style={{ fontFamily:'var(--font-d)', fontSize: v>=1024?20:26,
              fontWeight:500, color: v>=32?'#FBF7EF':'var(--text)' }}>{v}</span> : null}
          </div>
        ))}
        {over && (
          <div style={{ position:'absolute', inset:0, display:'grid', placeItems:'center',
            background:'rgba(0,0,0,.35)', borderRadius:10 }}>
            <div style={{ textAlign:'center' }}>
              <p style={{ fontFamily:'var(--font-d)', fontSize:22, fontStyle:'italic', color:'#FBF7EF' }}>Game over</p>
              <button onClick={reset} style={{ ...btnStyle, marginTop:8 }}>Try again</button>
            </div>
          </div>
        )}
      </div>
      <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>
        Arrow keys to move
      </span>
    </div>
  );
}

/* ── Number guess ── */
function NumberGuess() {
  const [target, setTarget] = useState(() => 1 + Math.floor(Math.random() * 100));
  const [guess, setGuess]   = useState('');
  const [hint, setHint]     = useState('I’m thinking of a number between 1 and 100.');
  const [tries, setTries]   = useState(0);
  const [won, setWon]       = useState(false);

  function submit() {
    const g = parseInt(guess, 10);
    if (isNaN(g)) return;
    setTries(t => t + 1);
    if (g === target) { setHint(`Got it in ${tries + 1} tries!`); setWon(true); }
    else setHint(g < target ? `${g} is too low — go higher.` : `${g} is too high — go lower.`);
    setGuess('');
  }
  function reset() { setTarget(1 + Math.floor(Math.random()*100)); setHint('New number — between 1 and 100.'); setTries(0); setWon(false); setGuess(''); }

  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:16, padding:'20px 0' }}>
      <p style={{ fontFamily:'var(--font-d)', fontSize:18, fontStyle:'italic', color:'var(--text)', textAlign:'center', maxWidth:280 }}>{hint}</p>
      {!won ? (
        <div style={{ display:'flex', gap:8 }}>
          <input autoFocus value={guess} onChange={e=>setGuess(e.target.value)}
            onKeyDown={e=>e.key==='Enter'&&submit()} placeholder="?"
            style={{ width:80, textAlign:'center', fontFamily:'var(--font-m)', fontSize:15,
              padding:'8px', border:'1px solid var(--border-2)', borderRadius:8,
              background:'var(--surface)', color:'var(--text)' }}/>
          <button onClick={submit} style={btnStyle}>Guess</button>
        </div>
      ) : (
        <button onClick={reset} style={btnStyle}>Play again</button>
      )}
      <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>{tries} guesses</span>
    </div>
  );
}

/* ── Typing test ── */
const TYPING_SENTENCES = [
  "The quiet workshop held tools worn smooth by years of patient hands.",
  "A single lamp burned late while the city outside fell into silence.",
  "Ideas arrive unannounced and leave before you can write them down.",
];
function TypingTest() {
  const [sentence] = useState(() => TYPING_SENTENCES[Math.floor(Math.random()*TYPING_SENTENCES.length)]);
  const [typed, setTyped]   = useState('');
  const [start, setStart]   = useState(null);
  const [done, setDone]     = useState(false);
  const [wpm, setWpm]       = useState(0);

  function onChange(e) {
    const v = e.target.value;
    if (!start) setStart(Date.now());
    setTyped(v);
    if (v === sentence) {
      const mins = (Date.now() - (start || Date.now())) / 60000;
      const words = sentence.split(' ').length;
      setWpm(Math.round(words / Math.max(mins, 0.001)));
      setDone(true);
    }
  }
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:14, padding:'8px 0', maxWidth:420 }}>
      <p style={{ fontFamily:'var(--font-b)', fontSize:15, lineHeight:1.7, color:'var(--text-q)' }}>
        {sentence.split('').map((ch, i) => {
          let color = 'var(--text-3)';
          if (i < typed.length) color = typed[i] === ch ? 'var(--text)' : '#B5562E';
          return <span key={i} style={{ color }}>{ch}</span>;
        })}
      </p>
      {!done ? (
        <textarea autoFocus value={typed} onChange={onChange} rows={2}
          placeholder="Start typing…"
          style={{ width:'100%', resize:'none', fontFamily:'var(--font-b)', fontSize:14,
            padding:'10px', border:'1px solid var(--border-2)', borderRadius:8,
            background:'var(--surface)', color:'var(--text)' }}/>
      ) : (
        <p style={{ fontFamily:'var(--font-d)', fontSize:22, fontStyle:'italic', color:'var(--accent-tx)' }}>
          {wpm} WPM
        </p>
      )}
    </div>
  );
}

const btnStyle = {
  fontFamily:'var(--font-m)', fontSize:11, padding:'6px 14px', borderRadius:8,
  border:'1px solid var(--accent-bd)', background:'var(--accent-bg)',
  color:'var(--accent-tx)', cursor:'pointer',
};

const GAMES = [
  { id:'2048',  name:'2048',        desc:'Slide & merge tiles',     render: () => <Game2048/> },
  { id:'guess', name:'Number Guess',desc:'Find the secret number',  render: () => <NumberGuess/> },
  { id:'type',  name:'Typing Test', desc:'Measure your WPM',        render: () => <TypingTest/> },
];

function GamesModal({ onClose }) {
  const [active, setActive] = useState(null);
  const game = GAMES.find(g => g.id === active);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') { active ? setActive(null) : onClose(); } };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [active, onClose]);

  return (
    <div onMouseDown={onClose} style={{ position:'fixed', inset:0, zIndex:200,
      background:'rgba(0,0,0,.4)', display:'grid', placeItems:'center' }}>
      <div onMouseDown={e=>e.stopPropagation()} style={{ width:active?'auto':380, minWidth:340,
        background:'var(--thread-bg)', border:'1px solid var(--border-2)', borderRadius:14,
        padding:'22px 24px', boxShadow:'0 16px 48px rgba(0,0,0,.3)' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            {active && <button onClick={()=>setActive(null)} style={{ ...btnStyle, padding:'3px 9px' }}>‹ Back</button>}
            <span style={{ fontFamily:'var(--font-d)', fontSize:20, fontStyle:'italic', color:'var(--text)' }}>
              {game ? game.name : 'Play'}
            </span>
          </div>
          <button onClick={onClose} style={{ background:'transparent', border:'none', cursor:'pointer' }}>
            <Ico n="close" size={16} color="var(--text-3)"/>
          </button>
        </div>
        {game ? game.render() : (
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {GAMES.map(g => (
              <button key={g.id} onClick={()=>setActive(g.id)} style={{ display:'flex',
                alignItems:'center', gap:12, padding:'12px 14px', borderRadius:10,
                border:'1px solid var(--border)', background:'var(--surface)', cursor:'pointer',
                textAlign:'left', transition:'border-color var(--t)' }}>
                <Ico n="grid" size={16} color="var(--accent-tx)"/>
                <div>
                  <div style={{ fontFamily:'var(--font-b)', fontSize:14, fontStyle:'italic', color:'var(--text)' }}>{g.name}</div>
                  <div style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>{g.desc}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

window.V2Games = { GamesModal };
