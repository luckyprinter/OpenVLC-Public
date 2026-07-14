# OpenVLC — Firmware

ESP32 firmware for the VLC/LiFi prototype transmitter and receiver.

## Status

Firmware is **working and stable**. No changes are planned unless explicitly
approved. Changes require prior discussion.

## Current Firmware

| File | Role | Key Features |
|---|---|---|
| `tx_dma.ino` | TX ESP32 (DMA) | 4B5B encoding, NRZ/OOK output using DMA, chunk carousel, USB serial preloading |
| `tx_non_dma.ino` | TX ESP32 (Non-DMA) | 4B5B encoding, NRZ/OOK output, chunk carousel, USB serial preloading |
| `rx.ino` | RX ESP32 | 4B5B decoding, CRC validation, chunk assembly, Vref PWM commands |

## TX Pin Configuration

| Pin | Function |
|---|---|
| GPIO5 | 4B5B + NRZ/OOK output (active-low for IRLZ44N/IRF540N driver) |

## RX Pin Configuration

| Pin | Function |
|---|---|
| GPIO5 | LM393 Channel A digital output (RX data, 10kΩ pull-up to 3.3V) |
| GPIO25 | PWM output for automated Vref control (Level-shifted by LM393 Channel B) |
| GPIO34 | ADC — scaled PVo monitor (22k/8.2k divider) |
| GPIO35 | ADC — scaled Vref monitor (22k/8.2k divider) |

## RX Serial Commands (Vref Control)

```
VREF_MODE=AUTO|MANUAL
VREF_PWM=<gpio25_pwm_percent>
VREF_SET=<target_mV>
VREF_PWM_FS=<gpio35_full_scale_mV>
VREF_SETTLE_MS=<delay_ms>
VREF_GET
VREF_MARGIN=<target_margin_mV>
VREF_CAL
VREF_CAL_SWING
VREF_SWEEP=<start_mV>,<end_mV>,<step_mV>
```

## Buffer Limits

- TX stream buffer: 80 KiB
- RX stream buffer: 80 KiB
- GUI batching: files >80 KiB split into `VLCB1~...` parts
