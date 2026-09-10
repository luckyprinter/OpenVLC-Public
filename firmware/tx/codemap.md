# firmware/tx/

## Responsibility
ESP32 Arduino firmware that transmits 4B5B + NRZ/OOK optical frames over the LED driver. It receives preloaded file data from the TX application over USB serial, stores it in an 80 KiB RAM buffer, encodes each byte as 4B5B symbols, and outputs the optical waveform through GPIO5.

## Design
Single `.ino` sketch. The stream-based design uses `STREAM_BEGIN`, `STREAM_DATA`, and `STREAM_START` commands to preload a file, validate it with CRC, and transmit the file in chunks with preamble and synchronization. The optical interface uses GPIO5 to drive the LED driver stage. The firmware supports the active-low driver configuration used by the prototype and the configured optical intensity control.

## Flow
`setup()`: initialize serial communication, configure the transmitter output, and set the symbol rate. `loop()`: parse serial commands → handle `STREAM_BEGIN` (metadata), `STREAM_DATA` (hex payload), and `STREAM_START` (begin transmission). Transmission: emit preamble and synchronization → build each framed chunk with metadata and CRC fields → send 4B5B-encoded bits at the configured symbol rate → return to the idle light state between frames.

## Integration
- USB serial (115200 baud) receives commands and stream data from the TX application
- Optical interface: GPIO5 → LED driver → 12 V LED bulb
- Supports the active-low driver configuration used by the prototype
- Accepts serial commands including FREQ, GAP, FGAP, ACTIVE_LOW, IDLE_ON, INTENSITY, STREAM_BEGIN, STREAM_DATA, and STREAM_START

## Thesis Reference
This is the transmitter firmware used by the experimental prototype described in the thesis. Appendix O provides selected code snippets explaining important firmware functions.
