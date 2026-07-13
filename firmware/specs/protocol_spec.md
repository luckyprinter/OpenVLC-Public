# Firmware Protocol Specification

## Packet Format

Each transmitted frame contains:

| Field | Description |
|---|---|
| Start-of-frame byte | Frame delimiter |
| Version | Protocol version |
| Transfer ID | Unique transfer identifier |
| Frame type | Data, control, or end marker |
| Total size | Total payload size in bytes |
| Total chunks | Number of chunks for the transfer |
| Chunk index | Current chunk number |
| Payload length | Bytes in this chunk's payload |
| File CRC | CRC of the complete file |
| Chunk CRC | CRC of this chunk |
| File name | Transfer filename (or `VLCB1~...` for batched) |
| Payload data | Actual chunk data |
| Frame CRC | CRC of the frame |

## Transmission Flow

1. TX GUI preloads stream data to TX ESP32 via USB serial
2. TX ESP32 encodes each byte as 4B5B symbols
3. TX ESP32 outputs NRZ/OOK optical symbols through GPIO5
4. LED driver (2N3904 + IRF540N) switches 12V LED bulb
5. Chunks are repeated for selected carousel rounds
6. RX ESP32 decodes 4B5B symbols, validates CRC, stores valid chunks
7. RX GUI reconstructs the complete file after all chunks received

## Bit Error Rate (BER) Testing

For BER testing, the system does not use deterministic seeded payloads. Instead, the RX GUI compares the received data (whether complete or incomplete) directly against a local copy of the original data file stored on the receiver laptop to perform a bit-by-bit comparison and compute the BER value.

## Batched Transfer Format

For files exceeding the 80 KiB firmware buffer:

```
VLCB1~<original_filename>.<ext>
```

The TX GUI splits the file into 80 KiB parts, each transmitted as a separate
stream. The RX GUI reassembles the complete file after all parts pass CRC.