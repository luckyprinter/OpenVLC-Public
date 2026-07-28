# OpenVLC/firmware/

## Responsibility
Documentation and specification root for the OpenVLC firmware. Provides a stable reference and source code for the ESP32 TX/RX firmware used in the VLC/LiFi prototype.

## Design
Two-document structure: a top-level README.md with pin maps, buffer limits, serial command references, and firmware status; and a `specs/` subdirectory containing the protocol specification. README also documents the Vref control system (PWM, ADC scaling, mode commands).

## Flow
Referenced by developers and the GUI to understand firmware capabilities, pin assignments, serial protocol, and Vref tuning parameters. The spec in `specs/` defines the frame/packet format used by both TX and RX.

## Integration
- References `firmware/README.md` and `firmware/specs/protocol_spec.md`
- Contains the canonical firmware source code in `rx/`, `tx_dma/`, and `tx_non_dma/`
- Protocol spec is shared between TX GUI, RX GUI, TX firmware, and RX firmware

