// Single-part STREAM framing from OpenVLC-Public 411f183a.
export const MAX_STREAM_BYTES = 80 * 1024;
export const CHUNK_SIZES = [256, 512, 1024];
const CODE_4B5B = [30, 9, 20, 21, 10, 11, 14, 15, 18, 19, 22, 23, 26, 27, 28, 29];
const NAME_OFFSET = 20;
const TRANSFER_ID = 1;

export function crc16(bytes) {
  let crc = 0xffff;
  for (const byte of bytes) {
    crc ^= byte << 8;
    for (let bit = 0; bit < 8; bit++) {
      crc = ((crc << 1) ^ (crc & 0x8000 ? 0x1021 : 0)) & 0xffff;
    }
  }
  return crc;
}

export function buildTransfer(file, chunkSize) {
  if (!CHUNK_SIZES.includes(chunkSize) || !file.bytes.length || file.bytes.length > MAX_STREAM_BYTES) {
    throw new RangeError('Unsupported single-part STREAM settings.');
  }
  const name = new TextEncoder().encode(file.name).slice(0, 80);
  const fileCrc = crc16(file.bytes);
  const total = Math.ceil(file.bytes.length / chunkSize);

  function frame(index, payload, notice = false) {
    const payloadOffset = NAME_OFFSET + name.length;
    const bytes = new Uint8Array(payloadOffset + payload.length + 2);
    const header = new DataView(bytes.buffer);
    header.setUint8(0, 0xa5);
    header.setUint8(1, 1);
    header.setUint8(2, notice ? 0xfe : 1);
    header.setUint16(3, TRANSFER_ID);
    header.setUint32(5, file.bytes.length);
    header.setUint16(9, total);
    header.setUint16(11, index);
    header.setUint16(13, payload.length);
    header.setUint16(15, fileCrc);
    const chunkCrc = crc16(payload);
    header.setUint16(17, chunkCrc);
    header.setUint8(19, name.length);
    bytes.set(name, NAME_OFFSET);
    bytes.set(payload, payloadOffset);
    const frameCrc = crc16(bytes.subarray(0, -2));
    header.setUint16(bytes.length - 2, frameCrc);
    return { index, bytes, payload, payloadOffset, chunkCrc, frameCrc, notice };
  }

  const frames = [frame(0, new Uint8Array(0), true)];
  for (let index = 0; index < total; index++) {
    const payload = new Uint8Array(chunkSize);
    payload.set(file.bytes.subarray(index * chunkSize, (index + 1) * chunkSize));
    frames.push(frame(index, payload));
  }
  return { total, frames, fileCrc, chunkSize, file, transferId: TRANSFER_ID };
}

export function verifyFrame(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const end = bytes.length - 2;
  if (view.getUint16(end) !== crc16(bytes.subarray(0, end))) return 'rejected';
  const payloadOffset = NAME_OFFSET + view.getUint8(19);
  const chunkLength = view.getUint16(13);
  if (payloadOffset + chunkLength !== end || view.getUint16(17) !== crc16(bytes.subarray(payloadOffset, end))) {
    return 'rejected';
  }
  return view.getUint8(2) === 0xfe ? 'notice' : 'stored';
}

export function deliverFrame(state, transfer, scenario) {
  const frame = transfer.frames[state.cursor];
  if (!frame) return state;
  let bytes = frame.bytes;
  let status;
  const targeted = !frame.notice && frame.index === Math.floor(transfer.total / 2) && state.round === 1;
  if (targeted && scenario === 'loss') {
    status = 'missing';
  } else {
    if (targeted && scenario === 'corrupt') {
      bytes = bytes.slice();
      // Change one encoded payload byte after TX computes both checksums.
      bytes[frame.payloadOffset] ^= 1;
    }
    status = verifyFrame(bytes);
  }

  const received = new Map(state.received);
  if (status === 'stored') {
    if (received.has(frame.index)) {
      status = 'duplicate';
    } else {
      received.set(frame.index, bytes.subarray(frame.payloadOffset, -2));
    }
  }
  return {
    ...state,
    cursor: state.cursor + 1,
    received,
    latest: { status, bytes, frame, round: state.round },
    outcomes: { ...state.outcomes, [state.cursor]: status },
    altered: status === 'rejected' ? { frame, bytes } : state.altered,
  };
}

export function reassemble(transfer, received) {
  if (received.size !== transfer.total) return null;
  const bytes = new Uint8Array(transfer.file.bytes.length);
  for (const [index, payload] of received) {
    const offset = index * transfer.chunkSize;
    bytes.set(payload.subarray(0, bytes.length - offset), offset);
  }
  return {
    bytes,
    crcMatches: crc16(bytes) === transfer.fileCrc,
    exactMatch: bytes.every((value, index) => value === transfer.file.bytes[index]),
  };
}

export function opticalSymbols(bytes, mode, activeOffset) {
  if (mode === 'sync') {
    // Idle-on drops for the start edge, then alternates before the sync word.
    return '0' + '10'.repeat(32) + (0xd5b7).toString(2).padStart(16, '0');
  }
  return Array.from(bytes.subarray(activeOffset, activeOffset + 4), (value) => (
    CODE_4B5B[value >> 4].toString(2).padStart(5, '0') +
    CODE_4B5B[value & 15].toString(2).padStart(5, '0')
  )).join('');
}

export function scopePath(symbols) {
  const step = 640 / symbols.length;
  const y = (bit) => bit === '1' ? 24 : 88;
  return [...symbols].map((bit, index) => {
    const start = index ? 'V' : 'M0 ';
    return `${start}${y(bit)}H${((index + 1) * step).toFixed(2)}`;
  }).join('');
}
