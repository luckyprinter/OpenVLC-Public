# logic/ — Business Logic Layer

## Responsibility
Contains pure computation logic isolated from UI and I/O. Currently provides a single function for calculating BER (Bit Error Rate) and transfer quality metrics from chunk-level data. The module exists to keep BER math separate and testable independent of the GUI.

## Design
- **Single entry point**: `transfer_quality_from_chunks(chunks, label, crc_status) → TransferQuality`
- **Pure function**: No side effects, no I/O, no state. All inputs are `list[ChunkRecord]` with `status`, `expected`, and `received` fields.
- **Computed metrics**:
  - `total_bits` = sum of all chunk expected sizes × 8
  - `bit_errors` = sum of `different_bytes × 8` across all chunks
  - `strict_ber` = bit_errors / total_bits
  - `bit_accuracy` = 100% - (bit_errors / total_bits × 100)
  - `recovery_rate` = matched_chunks / total_chunks × 100
  - `first_issue` = description of first non-matching chunk
- **Module docstring**: Indicates the code was ported from `vlc_migration`.

## Flow
```
caller (mock_data.py, simulation backend)
  → transfer_quality_from_chunks(chunks, label, crc_status)
    → iterates ChunkRecord list
    → computes aggregate metrics
    → returns frozen TransferQuality dataclass
```

## Integration
- **Depends on**: `models.py` (`ChunkRecord`, `ChunkStatus`, `TransferQuality`).
- **Depended by**: `mock_data.py` (builds mock quality from chunks), `rx/backends/simulation.py` (computes quality from simulated chunks).
- **External**: None (pure Python standard library).
