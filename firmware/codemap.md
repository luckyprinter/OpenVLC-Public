# esp32-lifi-io/firmware/

## Responsibility
Documentation and specification root for the esp32-lifi-io firmware. Provides a stable reference for the ESP32 TX/RX firmware used in the VLC/LiFi prototype. Does not contain source code — points to `../../vlc/firmware/` as the read-only original.

## Design
Two-document structure: a top-level README.md with pin maps, buffer limits, serial command references, and firmware status; and a `specs/` subdirectory containing the protocol specification. README also documents the Vref control system (PWM, ADC scaling, mode commands).

## Flow
Referenced by developers and the GUI to understand firmware capabilities, pin assignments, serial protocol, and Vref tuning parameters. The spec in `specs/` defines the frame/packet format used by both TX and RX.

## Integration
- References `firmware/README.md` and `firmware/specs/protocol_spec.md`
- Links to the canonical firmware at `../../vlc/firmware/` (read-only, do not modify)
- Protocol spec is shared between TX GUI, RX GUI, TX firmware, and RX firmware

