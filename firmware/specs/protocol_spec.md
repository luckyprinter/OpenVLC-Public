# Firmware Protocol Specification

## Packet Format

Each transmitted frame contains:

| Field | Description |
|---|---|
| Start-of-frame byte | Frame delimiter |
| Version | Protocol version |
| Transfer ID | 16-bit firmware identifier. Host captures use a separate identity because firmware IDs can recur. |
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

Method 2 uses a bit-by-bit comparison of the reconstructed file and an operator-selected copy of the original. The strict comparison counts each missing or extra byte as eight bit errors. A CRC result reports frame or file integrity independently of BER. When there is no reconstructed payload or no usable reference, Method 2 is unavailable. The current receiver reports chunk counts at timeout and discards partial RAM data, so there is no partial payload to compare in that case.

## Timing and telemetry

The shipped transmitter uses an initial edge, 64 alternating preamble symbols and a 16-symbol sync word, followed by ten 4B5B symbols per frame byte. It sends one notice and then the data frames. An optional pad fills the final payload chunk. The configured frame gap precedes and follows each frame. Final-frame idle adds another delay after the last frame. `TX_STREAM_DONE` means the TX emitted an optical round. It conveys no receiver acknowledgment.

RX link-quality messages report low-rate PVo and Vref voltages and their margin. The shipped firmware does not stream symbol-rate comparator samples, so these messages support a voltage trend and no raw OOK waveform or calibrated lux measurement.

## Batched Transfer Format

When a file requires more than 80 KiB or 512 chunks in one stream, TX adds batch metadata to each part's filename:

```
VLCB1~<group-id-hex>~<part-index>~<part-count>~<whole-file-crc-hex>~<original-filename>
```

Part indexes start at one. The full metadata and original filename must fit in 80 UTF-8 bytes. The receiver validates each part and verifies the whole-file CRC before publishing the reconstructed file.
