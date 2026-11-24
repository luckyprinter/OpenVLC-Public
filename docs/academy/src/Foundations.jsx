import { useState } from 'react';
import { CircuitBoard, FileText, Lightbulb } from 'lucide-react';
import { SAMPLE } from './learningSample.js';
import { buildTransfer, deliverFrame, opticalSymbols, reassemble, scopePath } from './transferModel.js';
import './foundations.css';

const stages = ['Byte to light', 'Light to a bit', 'Frames to a file'];
const transfer = buildTransfer(SAMPLE, 256);
const originalByte = SAMPLE.bytes[0];
const levels = [0.38, 0.63, 0.69];

function runRound({ round, received = new Map(), condition }) {
  let state = { round, cursor: 0, received, outcomes: {}, altered: null };
  for (const _frame of transfer.frames) state = deliverFrame(state, transfer, condition);
  return state.received;
}

const incomplete = runRound({ round: 1, condition: 'corrupt' });
const recovered = runRound({ round: 2, received: incomplete, condition: 'corrupt' });

export function OpticalIntro() {
  const [on, setOn] = useState(true);
  return <div className="optical-intro">
    <div className="optical-intro-label">A single optical symbol</div>
    <div className={'optical-chain'+(on ? ' is-lit' : '')}>
      <span><CircuitBoard aria-hidden="true"/>ESP32</span>
      <span><Lightbulb aria-hidden="true"/>LED</span>
      <span><CircuitBoard aria-hidden="true"/>Receiver</span>
    </div>
    <div className="optical-actions">
      <div><button aria-pressed={!on} onClick={()=>setOn(false)}>Send 0</button><button aria-pressed={on} onClick={()=>setOn(true)}>Send 1</button></div>
      <output>{on ? 'LED on · symbol 1' : 'LED off · symbol 0'}</output>
    </div>
  </div>;
}

function Encoder({ onOpenCode }) {
  const [nibble, setNibble] = useState(originalByte & 15);
  const high = originalByte >> 4;
  const byte = (high << 4) | nibble;
  const encoded = opticalSymbols(Uint8Array.of(byte), 'frame', 0);
  return <>
    <h2>How can an LED carry a byte?</h2>
    <p>The transmitter packs bytes into a frame. It splits each frame byte into two four-bit groups called nibbles, then looks up a five-symbol code for each group. The LED turns on for a 1 and off for a 0.</p>
    <div className="foundation-instrument">
      <label>Change the low nibble <select value={nibble} onChange={e=>setNibble(Number(e.target.value))}>
        {Array.from({length:16}, (_, value)=><option key={value} value={value}>{value.toString(2).padStart(4,'0')}</option>)}
      </select></label>
      <dl className="foundation-values" aria-live="polite">
        <div><dt>Input byte</dt><dd>{high.toString(2).padStart(4, '0')} {nibble.toString(2).padStart(4, '0')}</dd></div>
        <div><dt>4B5B output</dt><dd>{encoded.slice(0,5)} {encoded.slice(5)}</dd></div>
      </dl>
      <svg viewBox="0 0 640 112" role="img" aria-label={'Logical LED waveform: '+encoded}>
        <path className="foundation-trace" vectorEffect="non-scaling-stroke" d={scopePath(encoded)}/>
      </svg>
      <p className="foundation-caption">Modeled OOK waveform · upper level means LED on</p>
    </div>
    <p>The starting value is the first byte of <code>{SAMPLE.name}</code>, the letter O. Changing its low nibble changes the last five symbols in this example.</p>
    <button className="foundation-link" onClick={()=>onOpenCode('tx-encode')}>See the firmware’s 4B5B lookup</button>
  </>;
}

function Detector() {
  const [threshold, setThreshold] = useState(0.5);
  const samples = levels.map(value=>Number(value > threshold));
  const result = Number(samples.reduce((sum, bit)=>sum+bit, 0) >= 2);
  return <>
    <h2>How does the receiver decide on a bit?</h2>
    <p>The photodiode converts incoming light to current. An amplifier converts the current to a voltage. The comparator compares it with a reference, and the ESP32 can take three digital samples and use the majority value.</p>
    <div className="foundation-instrument">
      <label>Reference threshold <span aria-hidden="true">{threshold.toFixed(2)}</span>
        <input type="range" min="0.2" max="0.85" step="0.01" value={threshold} onChange={e=>setThreshold(Number(e.target.value))}/>
      </label>
      <svg viewBox="0 0 360 125" role="img" aria-label="Three modeled samples and an adjustable threshold">
        <path className="foundation-trace" d={levels.map((value,index)=>[index ? 'L' : 'M',60+index*120,110-value*100].join(' ')).join(' ')}/>
        <path className="foundation-threshold" d={'M0 '+(110-threshold*100)+'H360'}/>
        {levels.map((value,index)=><circle key={index} cx={60+index*120} cy={110-value*100} r="6" fill="currentColor"/>)}
      </svg>
      <dl className="foundation-values">
        <div><dt>Comparator samples</dt><dd>{samples.join(' · ')}</dd></div>
        <div><dt>Majority bit</dt><dd>{result}</dd></div>
      </dl>
    </div>
    <p>Try raising the threshold past 0.63. The result flips when at least two samples fall on the same side. These normalized values illustrate the decision and carry no voltage or hardware measurement.</p>
  </>;
}

function Assembly() {
  const [pass, setPass] = useState(0);
  const received = [null, incomplete, recovered][pass];
  const verified = received && reassemble(transfer, received)?.crcMatches;
  return <>
    <h2>What if a chunk never makes it?</h2>
    <p>The receiver stores valid payloads by chunk index. When a corrupted frame fails its checksum, that slot stays empty. A later round sends all the chunks again, so the receiver can fill the missing slot.</p>
    <div className="foundation-instrument">
      <p><code>{SAMPLE.name}</code> · {transfer.total} chunks</p>
      <ol className="foundation-slots">
        {transfer.frames.slice(1).map(({index})=><li key={index} className={received?.has(index) ? 'accepted' : ''}>
          <b>Chunk {index+1}</b><span>{received?.has(index) ? 'Stored' : pass ? 'Rejected by CRC' : 'Waiting'}</span>
        </li>)}
      </ol>
      <p role="status">{verified ? 'Whole-file CRC passed.' : pass ? 'Incomplete file. Whole-file check is pending.' : 'Ready to send the sample.'}</p>
      <button className="reading-primary" onClick={()=>setPass((pass+1)%3)}>{['Send with one corrupt frame','Repeat the full round','Reset example'][pass]}</button>
    </div>
  </>;
}

export default function Foundations({ navigate, onOpenCode }) {
  const [stage,setStage] = useState(0);
  return <section className="foundation-lesson reading-surface">
    <header><p className="reading-kicker">Foundations</p><h1>Follow a file through light</h1>
      <p>Start with one byte from <code>{SAMPLE.name}</code>. See how the transmitter turns it into an optical signal and how the receiver builds the file back up.</p></header>
    <nav className="foundation-stages" aria-label="Foundation stages">
      {stages.map((label,index)=><button key={label} aria-current={index===stage?'step':undefined} onClick={()=>setStage(index)}>{label}</button>)}
    </nav>
    <article className="foundation-stage" key={stage}>
      {stage===0 && <Encoder onOpenCode={onOpenCode}/>}
      {stage===1 && <Detector/>}
      {stage===2 && <Assembly/>}
    </article>
    <div className="foundation-next">
      {stage>0 && <button className="reading-secondary" onClick={()=>setStage(stage-1)}>Previous stage</button>}
      {stage<2 ? <button className="reading-primary" onClick={()=>setStage(stage+1)}>Next stage</button> :
        <button className="reading-primary" onClick={()=>navigate('lab/guided')}><FileText size={17} aria-hidden="true"/> Try the guided transfer</button>}
    </div>
  </section>;
}
