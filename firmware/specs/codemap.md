# esp32-lifi-io/firmware/specs/

## Responsibility
Defines the wire-level protocol for the VLC/LiFi optical link. The single document `protocol_spec.md` describes packet framing, transmission flow, BER test payload format, and batched transfer format shared by both TX and RX firmware.

## Design
Single Markdown document with a field table for the frame format (SOF byte, version, transfer ID, frame type, total size/chunks, chunk index, payload length, file CRC, chunk CRC, file name, payload data, frame CRC). Also documents the BER test (`BERTEST~<size>~<seed>.bin`) and batched transfer (`VLCB1~...`) conventions.

## Flow
1. TX GUI preloads stream data → TX ESP32 encodes as 4B5B → LED driver → optical free space → TIA → LM393 (Level Shifter & Comparator) → RX ESP32 decodes → RX GUI reconstructs. The spec defines every field and CRC at each layer.

## Integration
- Consumed by both the TX and RX firmware implementations (validated against it)
- Consumed by the TX GUI and RX GUI Python code for frame construction/parsing
- BER test format enables deterministic bit-level comparison between TX and RX sides

