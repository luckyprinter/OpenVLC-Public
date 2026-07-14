# firmware/rx_esp32_lifi_dual_mode/

## Responsibility
ESP32 Arduino firmware that receives and decodes 4B5B + NRZ/OOK optical frames from an LM393 photodiode module. Buffers and validates incoming file chunks via CRC, then dumps the reconstructed file over USB serial to the RX GUI.

## Design
Single `.ino` sketch (~1042 lines). State-machine frame parser (WAIT_SOF → READ_FIXED_HEADER → READ_VARIABLE). Line decoder with preamble sync (0xD5B7), 4B5B symbol table lookup, majority-3 sampling for noise immunity, and automatic polarity detection. Hardware interfaces: GPIO5 (RX data input), GPIO34 (scaled PVo ADC monitor), GPIO35 (scaled Vref ADC feedback), GPIO25 (PWM output for automated Vref control via LM393).

## Flow
`setup()`: init serial at 460800, configure ADC, start Vref PWM, set symbol rate. `loop()`: read optical bytes → decode 4B5B → parse frame fields → validate chunk CRC → store in RAM buffer → dump via `RX_FILE_HEX` when complete. Idle reporting of link quality (margin, swing, pass rate) every 1 s.

## Integration
- USB serial (460800 baud) communicates with the RX GUI
- Optical interface: GPIO5 reads LM393 digital output (3.3V pull-up)
- Vref control: GPIO25 PWM (30 kHz, 8-bit) drives LM393 comparator reference via RC filter
- ADC feedback: GPIO34/35 read scaled PVo/Vref through 22k/8.2k dividers
- Accepts serial commands: FREQ, PHASE, MAJ, VREF_MODE, VREF_SET, VREF_CAL, VREF_SWEEP, etc.
