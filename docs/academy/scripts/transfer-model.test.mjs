import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildTransfer, crc16, deliverFrame, MAX_STREAM_BYTES, opticalSymbols, reassemble, verifyFrame,
} from '../src/transferModel.js';

const blank = (round = 1, received = new Map()) => ({ round, received, cursor: 0, outcomes: {} });
const file = { name: 'light.txt', bytes: Uint8Array.from({ length: 600 }, (_, index) => index % 256) };
const sendRound = (start, transfer, scenario) => transfer.frames.reduce(
  (state) => deliverFrame(state, transfer, scenario),
  start,
);

test('STREAM frame layout follows the firmware offsets and checksum order', () => {
  assert.equal(crc16(new TextEncoder().encode('123456789')), 0x29b1);

  const transfer = buildTransfer(file, 256);
  const [notice, first, , last] = transfer.frames;
  assert.deepEqual(Array.from(notice.bytes.subarray(0, 20)), [
    0xa5, 1, 0xfe, 0, 1, 0, 0, 2, 88, 0, 3, 0, 0, 0, 0,
    transfer.fileCrc >> 8, transfer.fileCrc & 255, 255, 255, 9,
  ]);
  assert.equal(verifyFrame(notice.bytes), 'notice');
  assert.equal(verifyFrame(first.bytes), 'stored');
  assert.equal(last.payload.length, 256);
  assert.ok(last.payload.slice(88).every((byte) => byte === 0));

  const invalidChunkCrc = first.bytes.slice();
  invalidChunkCrc[first.payloadOffset] ^= 1;
  const frameCrc = crc16(invalidChunkCrc.subarray(0, -2));
  new DataView(invalidChunkCrc.buffer).setUint16(invalidChunkCrc.length - 2, frameCrc);
  assert.equal(verifyFrame(invalidChunkCrc), 'rejected');
});

test('clean and repeated impaired rounds reconstruct the identical original bytes', () => {
  const transfer = buildTransfer(file, 256);
  for (const scenario of ['clean', 'loss', 'corrupt']) {
    const firstRound = sendRound(blank(), transfer, scenario);
    const impaired = scenario !== 'clean';
    assert.equal(firstRound.received.size, impaired ? 2 : 3);
    if (impaired) {
      assert.equal(reassemble(transfer, firstRound.received), null);
      assert.equal(firstRound.outcomes[2], scenario === 'loss' ? 'missing' : 'rejected');
    }
    const finalRound = impaired ? sendRound(blank(2, firstRound.received), transfer, scenario) : firstRound;
    if (impaired) assert.equal(finalRound.outcomes[1], 'duplicate');
    const result = reassemble(transfer, finalRound.received);
    assert.equal(result.crcMatches, true);
    assert.equal(result.exactMatch, true);
    assert.deepEqual(result.bytes, file.bytes);
  }
});

test('the scope encodes both raw synchronization and 4B5B frame bytes', () => {
  const sync = opticalSymbols(Uint8Array.of(), 'sync', 0);
  assert.equal(sync, '0' + '10'.repeat(32) + '1101010110110111');
  assert.equal(opticalSymbols(Uint8Array.of(0xa5), 'frame', 0), '1011001011');
});

test('single-part file limits and valid chunk sizes bound the demo', () => {
  assert.equal(buildTransfer({ name: 'large', bytes: new Uint8Array(MAX_STREAM_BYTES) }, 256).total, 320);
  assert.throws(() => buildTransfer({ name: 'large', bytes: new Uint8Array(MAX_STREAM_BYTES + 1) }, 256), RangeError);
  assert.throws(() => buildTransfer({ name: 'empty', bytes: new Uint8Array(0) }, 256), RangeError);
  assert.throws(() => buildTransfer(file, 128), RangeError);
});
