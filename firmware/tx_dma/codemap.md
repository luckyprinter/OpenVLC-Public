# firmware/tx_esp32_lifi_dual_mode/

## Responsibility
ESP32 Arduino firmware that transmits 4B5B + NRZ/OOK optical frames over an LED driver. Receives preloaded file data from the TX GUI over USB serial, stores it in an 80 KiB RAM buffer, encodes each byte as 4B5B symbols, and outputs the optical waveform through GPIO5.

## Design
Single `.ino` sketch (~329 lines). Stream-based design: STREAM_BEGIN / STREAM_DATA / STREAM_START serial protocol preloads a file, validates with CRC, then transmits all chunks with preamble+sync (0xD5B7), 4B5B encoding, and configurable frame gaps. Hardware interface: GPIO5 drives an IRLZ44N/IRF540N MOSFET gate (with active-low option). Uses `analogWrite` at 30 kHz PWM carrier for intensity calibration.

## Flow
`setup()`: init serial at 115200, configure PWM, set symbol rate. `loop()`: parse serial commands → handle STREAM_BEGIN (metadata), STREAM_DATA (hex payload), STREAM_START (begin transmit). Transmission: emit preamble (64 alternating bits + sync word) → for each chunk, build framed packet (SOF, header, name, payload, CRC) → send 4B5B-encoded bits at symbol rate → idle between frames.

## Integration
- USB serial (115200 baud) receives commands and stream data from TX GUI
- Optical interface: GPIO5 → gate of IRLZ44N/IRF540N → 12V LED bulb
- Supports ACTIVE_LOW toggle for different driver circuits
- Accepts serial commands: FREQ, GAP, FGAP, ACTIVE_LOW, IDLE_ON, INTENSITY, STREAM_BEGIN/DATA/START
