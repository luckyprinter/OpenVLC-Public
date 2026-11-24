export const SAMPLE = {
  name: 'light-notes.txt',
  bytes: new TextEncoder().encode([
    'OpenVLC transfers digital data through modulated light.',
    'The desktop transmitter prepares a transfer ID and a file checksum before uploading the bytes to the ESP32.',
    'The firmware sends an optical notice and then data frames. Each payload byte becomes two five-symbol codewords.',
    'At the receiver, checksums reject damaged frames. Valid chunks are stored by index, so a repeated round can fill a missing slot.',
    'A whole-file CRC check runs after all chunks arrive. The receiver uses the file size to exclude padding at the end.',
    'This text is an example payload for the browser lab. It contains no measurements from the prototype.',
  ].join('\n\n')),
};
