import { useMemo, useRef, useState } from 'react';
import { Activity, Cpu, Download, FileUp, Radio, RotateCcw } from 'lucide-react';
import {
  buildTransfer, CHUNK_SIZES, deliverFrame, MAX_STREAM_BYTES, opticalSymbols, reassemble, scopePath,
} from './transferModel.js';
import { SAMPLE } from './learningSample.js';
import './transfer-lab.css';

const SOURCE = 'https://github.com/luckyprinter/OpenVLC-Public/blob/411f183a8592d8285118f613bb4909c5bbd9d3cc';
const OUTCOMES = {
  notice: 'Notice received',
  stored: 'Chunk accepted',
  duplicate: 'Duplicate skipped',
  rejected: 'Frame CRC failed',
  missing: 'Frame dropped',
};

const format = new Intl.NumberFormat();
const hex = (value, width = 2) => value.toString(16).padStart(width, '0').toUpperCase();
const initialRound = () => ({ round: 1, cursor: 0, received: new Map(), outcomes: {}, latest: null, altered: null });

function frameFields(transfer, frame) {
  const nameLength = frame.payloadOffset - 20;
  return [
    ['Start of frame', 0, 1, '0xA5'],
    ['Version', 1, 1, '1'],
    ['Frame type', 2, 1, frame.notice ? '0xFE (notice)' : '0x01 (data)'],
    ['Transfer ID', 3, 2, hex(transfer.transferId, 4)],
    ['File size', 5, 4, `${format.format(transfer.file.bytes.length)} B`],
    ['Total chunks', 9, 2, transfer.total],
    ['Chunk index', 11, 2, frame.index],
    ['Payload length', 13, 2, `${frame.payload.length} B`],
    ['File CRC', 15, 2, hex(transfer.fileCrc, 4)],
    ['Chunk CRC', 17, 2, hex(frame.chunkCrc, 4)],
    ['Filename length', 19, 1, `${nameLength} B`],
    ['Filename bytes', 20, nameLength, `${nameLength} B`],
    ['Payload', frame.payloadOffset, frame.payload.length, `${frame.payload.length} B`],
    ['Frame CRC', frame.bytes.length - 2, 2, hex(frame.frameCrc, 4)],
  ];
}

function readableSymbols(symbols, mode) {
  if (mode === 'sync') return [symbols[0], symbols.slice(1, 65), symbols.slice(65)].join(' / ');
  return symbols.match(/.{5}/g).join(' ');
}

function PacketInspector({ transfer, packet, selectPacket, state, rate }) {
  const [fieldIndex, setFieldIndex] = useState(0);
  const [mode, setMode] = useState('frame');
  const frame = transfer.frames[packet];
  const fields = frameFields(transfer, frame);
  const [field, offset, length] = fields[fieldIndex];
  // Preview the intended frame, with the altered RX bytes available for the rejected frame.
  const altered = state.altered?.frame === frame ? state.altered.bytes : null;
  const activeOffset = Math.min(offset, frame.bytes.length - 1);
  const symbols = opticalSymbols(frame.bytes, mode, activeOffset);
  const alteredSymbols = altered && mode === 'frame' ? opticalSymbols(altered, mode, activeOffset) : null;
  const symbolTime = Math.floor(1000000 / rate);

  return (
    <section className="transfer-panel transfer-inspector" aria-labelledby="transfer-inspector-heading">
      <div className="transfer-panel-head">
        <div><Radio size={20} aria-hidden="true" /><h2 id="transfer-inspector-heading">Optical frame inspector</h2></div>
        <label className="transfer-field transfer-field-inline">Frame
          <select value={packet} onChange={(event) => { setFieldIndex(0); selectPacket(Number(event.target.value)); }}>
            {transfer.frames.map((item, index) => (
              <option key={index} value={index}>
                {item.notice ? 'Notice' : `Chunk ${item.index + 1} of ${transfer.total}`}
                {state.outcomes[index] ? ` · ${OUTCOMES[state.outcomes[index]]}` : ''}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="transfer-inspector-layout">
        <div>
          <label className="transfer-field">Inspect field
            <select value={fieldIndex} onChange={(event) => setFieldIndex(Number(event.target.value))}>
              {fields.map(([label, , , value], index) => (
                <option key={label} value={index}>{label} · {value}</option>
              ))}
            </select>
          </label>
          <dl className="transfer-readouts">
            <div><dt>Frame length</dt><dd>{frame.bytes.length} B</dd></div>
            <div><dt>Field offset</dt><dd>{offset} B</dd></div>
            <div><dt>Field length</dt><dd>{length} B</dd></div>
          </dl>
          <p className="transfer-small">{field} bytes in hexadecimal{length > 24 ? ' (first 24)' : ''}</p>
          <div className="transfer-hex">
            {Array.from(frame.bytes.subarray(offset, offset + Math.min(length, 24)), (byte, index) => (
              <code key={index} className={altered && altered[offset + index] !== byte ? 'transfer-altered' : ''}>
                {hex(byte)}
              </code>
            ))}
            {!length && <span>Empty field</span>}
          </div>
          {altered && offset <= frame.payloadOffset && offset + length > frame.payloadOffset && (
            <p className="transfer-small">Injected change at byte {frame.payloadOffset}: TX sent {hex(frame.bytes[frame.payloadOffset])}, RX received {hex(altered[frame.payloadOffset])}.</p>
          )}
          <a href={`${SOURCE}/firmware/tx/tx.ino#L182-L200`} target="_blank" rel="noreferrer">Read the frame builder</a>
        </div>
        <div className="transfer-scope">
          <div className="transfer-scope-head">
            <h3><Activity size={18} aria-hidden="true" /> Logical OOK trace</h3>
            <div className="transfer-toggle-group" role="group" aria-label="Waveform region">
              <button type="button" aria-pressed={mode === 'sync'} onClick={() => setMode('sync')}>Preamble + sync</button>
              <button type="button" aria-pressed={mode === 'frame'} onClick={() => setMode('frame')}>Frame bytes</button>
            </div>
          </div>
          <div className="transfer-scope-chart">
            <div aria-hidden="true"><span>ON</span><span>OFF</span></div>
            <svg viewBox="0 0 640 112" preserveAspectRatio="none" role="img"
              aria-label={`Modeled on-off keying with ${symbols.length} symbols and ${symbolTime} microseconds per symbol`}>
              <path className="transfer-wave-grid" d="M0 24H640 M0 56H640 M0 88H640" />
              <path className="transfer-wave-tx" vectorEffect="non-scaling-stroke" d={scopePath(symbols)} />
              {alteredSymbols !== null && alteredSymbols !== symbols && (
                <path className="transfer-wave-rx" vectorEffect="non-scaling-stroke" d={scopePath(alteredSymbols)} />
              )}
            </svg>
          </div>
          <div className="transfer-scope-time"><span>0 µs</span><span>{format.format(symbols.length * symbolTime)} µs</span></div>
          <p className="transfer-small">
            {mode === 'sync'
              ? 'One start-edge symbol, 64 alternating preamble symbols, then the raw 0xD5B7 sync word.'
              : `Up to four bytes from offset ${activeOffset}. Each nibble maps to a five-symbol codeword.`}
            {' '}The trace models LED on/off states. {alteredSymbols && alteredSymbols !== symbols ? 'The dashed trace shows the injected receiver-side change. ' : ''}
            One symbol lasts {symbolTime} µs using the transmitter’s integer timing calculation.
          </p>
          <details className="transfer-bit-detail">
            <summary>Show exact symbols</summary>
            <code aria-label="Transmitted symbols">{readableSymbols(symbols, mode)}</code>
            {alteredSymbols && alteredSymbols !== symbols && <code aria-label="Altered symbols">{readableSymbols(alteredSymbols, mode)}</code>}
          </details>
          <a href={`${SOURCE}/firmware/tx/tx.ino#L147-L179`} target="_blank" rel="noreferrer">Read the optical encoder</a>
        </div>
      </div>
    </section>
  );
}

export default function TransferLab({ guided = false, onOpenCode }) {
  const [file, setFile] = useState(SAMPLE);
  const [chunkSize, setChunkSize] = useState(256);
  const [rate, setRate] = useState(15000);
  const [scenario, setScenario] = useState(guided ? 'corrupt' : 'clean');
  const [session, setSession] = useState(initialRound);
  const [packet, setPacket] = useState(0);
  const [fileError, setFileError] = useState('');
  const [reading, setReading] = useState(false);
  const fileInput = useRef(null);
  const uploadVersion = useRef(0);
  const transfer = useMemo(() => buildTransfer(file, chunkSize), [file, chunkSize]);
  const result = useMemo(() => reassemble(transfer, session.received), [transfer, session.received]);
  const roundFinished = session.cursor === transfer.frames.length;
  const complete = result?.crcMatches && result.exactMatch;
  const nextFrame = transfer.frames[session.cursor];
  const targetedIndex = Math.floor(transfer.total / 2) + 1;

  function resetRun() {
    setSession(initialRound());
    setPacket(0);
  }

  function chooseSample() {
    uploadVersion.current++;
    fileInput.current.value = '';
    setReading(false);
    setFileError('');
    setFile(SAMPLE);
    resetRun();
  }

  async function chooseFile(event) {
    const selected = event.target.files?.[0];
    if (!selected) return;
    const upload = ++uploadVersion.current;
    setFileError('');
    if (selected.size === 0 || selected.size > MAX_STREAM_BYTES) {
      setReading(false);
      setFileError('Choose a nonempty file up to 80 KiB for this single-part STREAM exercise.');
      event.target.value = '';
      return;
    }
    setReading(true);
    try {
      const bytes = new Uint8Array(await selected.arrayBuffer());
      if (upload === uploadVersion.current) {
        setFile({ name: selected.name, bytes });
        resetRun();
      }
    } catch {
      if (upload === uploadVersion.current) {
        setFileError('The browser could not read that file. Choose it again or use the sample.');
      }
    } finally {
      if (upload === uploadVersion.current) setReading(false);
    }
  }

  function send(toEnd) {
    let next = deliverFrame(session, transfer, scenario);
    while (toEnd && next.cursor < transfer.frames.length) next = deliverFrame(next, transfer, scenario);
    const incident = Object.entries(next.outcomes).find(([, outcome]) => outcome === 'rejected' || outcome === 'missing');
    setSession(next);
    setPacket(toEnd && incident ? Number(incident[0]) : next.cursor - 1);
  }

  function repeatRound() {
    setSession({ ...session, round: session.round + 1, cursor: 0, outcomes: {}, latest: null, altered: null });
    setPacket(0);
  }

  function download() {
    const url = URL.createObjectURL(new Blob([result.bytes], { type: 'application/octet-stream' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `received-${file.name}`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 30000);
  }

  let readout = 'Send the notice to begin this optical round.';
  if (session.latest) readout = OUTCOMES[session.latest.status] + '.';
  if (roundFinished && !complete) readout = result ? 'Whole-file verification failed.' : 'Incomplete round. Repeat STREAM_START to send every chunk again.';
  if (complete) readout = 'File CRC passed. The reconstructed bytes match the source file.';

  return (
    <section className="transfer-lab" aria-labelledby="transfer-heading">
      <header className="transfer-heading">
        <h1 id="transfer-heading">File transfer lab</h1>
        <p>Follow the prototype’s non-DMA STREAM path. Prepare a file, transmit its notice and data frames, then inspect what the receiver can reconstruct.</p>
        <p className="transfer-disclosure">This browser exercise uses the firmware’s frame layout and CRC. Loss and corruption are controlled examples. Files stay in your browser, and the lab has no serial connection or live optical measurements.</p>
      </header>
      {guided && <aside className="transfer-guide" aria-label="Guided transfer">
        <strong>Try recovering light-notes.txt</strong>
        <p>{complete ? 'The recovered file matches the sample. Now trace how the receiver validates a frame.' : roundFinished ? 'One frame failed its check. Repeat the full round, then send the rest of that round.' : session.round > 1 ? 'Send the rest of the repeat round. Watch the receiver fill the missing slot.' : 'Send the rest of the first round. Look for a CRC rejection and a missing chunk.'}</p>
        <button type="button" onClick={() => onOpenCode('rx-crc')}>Open receiver validation code</button>
      </aside>}
      <div className="transfer-workbench">
        <section className="transfer-panel" aria-labelledby="transfer-tx-heading">
          <div className="transfer-panel-head"><div><Cpu size={20} aria-hidden="true" /><h2 id="transfer-tx-heading">Transmitter</h2></div></div>
          <div className="transfer-panel-body">
            <label className="transfer-field"><span><FileUp size={16} aria-hidden="true" /> Choose a file (up to 80 KiB)</span>
              <input ref={fileInput} type="file" onChange={chooseFile} />
            </label>
            {fileError && <p className="transfer-error" role="alert">{fileError}</p>}
            <div className="transfer-file">
              <div><strong>{file.name}</strong><span>{format.format(file.bytes.length)} B · CRC {hex(transfer.fileCrc, 4)}</span></div>
              <button type="button" onClick={chooseSample}>Use sample</button>
            </div>
            <div className="transfer-settings">
              <label className="transfer-field">Chunk size
                <select value={chunkSize} onChange={(event) => { setChunkSize(Number(event.target.value)); resetRun(); }}>
                  {CHUNK_SIZES.map((size) => <option key={size} value={size}>{size} bytes</option>)}
                </select>
              </label>
              <label className="transfer-field">Symbol rate
                <select value={rate} onChange={(event) => setRate(Number(event.target.value))}>
                  <option value={10000}>10,000 symbols/s</option>
                  <option value={15000}>15,000 symbols/s</option>
                  <option value={20000}>20,000 symbols/s</option>
                </select>
              </label>
              <label className="transfer-field">First-round condition
                <select value={scenario} onChange={(event) => { setScenario(event.target.value); resetRun(); }}>
                  <option value="clean">Clean link</option>
                  <option value="loss">Drop one data frame</option>
                  <option value="corrupt">Corrupt one data frame</option>
                </select>
              </label>
            </div>
            <p className="transfer-small">{scenario === 'clean' ? 'Every frame arrives intact.' : `Chunk ${targetedIndex} is affected on its first transmission only.`}</p>
            <div className="transfer-buttons">
              <button className="transfer-primary" type="button" onClick={() => send(false)} disabled={reading || roundFinished}>
                {nextFrame?.notice ? 'Send notice' : 'Send next chunk'}
              </button>
              <button type="button" onClick={() => send(true)} disabled={reading || roundFinished}>Send rest of round</button>
              {roundFinished && !complete && <button className="transfer-primary" type="button" onClick={repeatRound}>Repeat full round</button>}
              <button type="button" onClick={resetRun}><RotateCcw size={15} aria-hidden="true" /> Reset</button>
            </div>
          </div>
        </section>

        <section className="transfer-panel" aria-labelledby="transfer-rx-heading">
          <div className="transfer-panel-head"><div><Radio size={20} aria-hidden="true" /><h2 id="transfer-rx-heading">Receiver</h2></div></div>
          <div className="transfer-panel-body transfer-receiver">
            <div className="transfer-progress-label"><span>Round {session.round}</span><strong>{session.received.size} / {transfer.total} chunks</strong></div>
            <progress aria-label="Chunks received" value={session.received.size} max={transfer.total} />
            <p className="transfer-status" role="status">{readout}</p>
            {session.latest && <p className="transfer-small">Last frame: {session.latest.frame.notice ? 'Notice' : `Chunk ${session.latest.frame.index + 1}`} · {OUTCOMES[session.latest.status]}</p>}
            <dl className="transfer-readouts">
              <div><dt>Frame loss this round</dt><dd>{Object.values(session.outcomes).filter((outcome) => outcome === 'missing').length}</dd></div>
              <div><dt>CRC rejects this round</dt><dd>{Object.values(session.outcomes).filter((outcome) => outcome === 'rejected').length}</dd></div>
              <div><dt>Whole-file CRC</dt><dd>{result ? result.crcMatches ? 'Pass' : 'Fail' : 'Pending'}</dd></div>
            </dl>
            <div className="transfer-buttons"><button className="transfer-primary" type="button" disabled={!complete} onClick={download}><Download size={16} aria-hidden="true" /> Download received file</button></div>
            <p className="transfer-small">A later pass sends the notice and every chunk again. The receiver fills missing slots and keeps the valid chunks it already has. The optical link has no acknowledgement for an individual lost frame.</p>
            <a href={`${SOURCE}/firmware/rx/rx.ino#L860-L941`} target="_blank" rel="noreferrer">Read receiver verification and reassembly</a>
          </div>
        </section>
      </div>
      <PacketInspector transfer={transfer} packet={packet} selectPacket={setPacket} state={session} rate={rate} />
    </section>
  );
}
