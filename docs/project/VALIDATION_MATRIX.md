# OpenVLC validation matrix

Commands use the repository root unless a working directory is given. Use an isolated `VLC_DATA_DIR` and user configuration directory for local application verification.

| Scope | Commit | Command or source | Result |
| --- | --- | --- | --- |
| Original Windows and Ubuntu application CI | Head `80ef4afa`, PR merge checkout `c9cde1c` | [Build Application 43375292023](https://github.com/luckyprinter/OpenVLC-Public/actions/runs/43375292023) | Both jobs failed at collection. Source smoke, screenshots, and packages were skipped. |
| Original local reproduction | `80ef4afa` | `application-source` via `QT_QPA_PLATFORM=offscreen python -m pytest tests -q --collect-only` | 195 collected and four errors from missing `gui_dev_v3.tx.protocol`. |
| Baseline recovery | `ffaa97d` | `application-source` via `QT_QPA_PLATFORM=offscreen python -m pytest tests -q --disable-warnings --tb=short` | 265 passed locally on Python 3.12.14. Existing pyqtgraph/Qt warnings were emitted. |
| Baseline source launcher | `ffaa97d` | `application-source` via `QT_QPA_PLATFORM=offscreen python run_v3.py --smoke-test` | Linux source smoke passed. |
| Stabilization suite | `6902da6` | `application-source` via `QT_QPA_PLATFORM=offscreen python -m pytest tests -q --disable-warnings --tb=short` | 322 passed on Linux. Existing pyqtgraph teardown warnings remain. A separate focused baseline run also observed an intermittent teardown crash after assertions, so the full process exit code matters. |
| Syntax and smoke | `6902da6` | `application-source` via `python -m compileall -q gui_dev_v3 tests run_v3.py` and `QT_QPA_PLATFORM=offscreen python run_v3.py --smoke-test` | Local syntax and source smoke passed. Both TX and RX console initialization are required by smoke mode. |
| Linux screenshots | `6902da6` | `application-source` via `QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=<scale> OPENVLC_SCREENSHOT_SCALE=<scale> python tests/capture_ui_screenshots.py` at `1.0`, `1.25`, `1.5` | 288 PNGs and geometry checks. Reviewed overview sheets and individual compact Export, diagnostics, and connection images. |
| Firmware compile | Sketch sources unchanged from `80ef4afa` through `6902da6` | `arduino-cli compile --jobs 2 --fqbn esp32:esp32:esp32 --build-path <scratch-path> firmware/tx/tx.ino` and the corresponding `firmware/rx/rx.ino` command | Arduino CLI 1.6.0, ESP32 core 4.0.0. TX 310,915 bytes program and 107,604 bytes RAM. RX 334,575 bytes program and 107,340 bytes RAM. Only the required toolchain dependencies for this FQBN were installed locally. |
| Release workflow syntax and citation | `6902da6` | `actionlint` and CFF schema 1.2.0 validation | Both passed locally. |
| Exact branch and PR integration builds | Check commit in run | [Build Application runs for the target branch](https://github.com/luckyprinter/OpenVLC-Public/actions/workflows/build_application.yml?query=branch%3Aredesign%2Fproduct-shell-method2) | The checkout step and archive `BUILD_COMMIT.txt` report the exact tested revision. Separately identify the PR synthetic merge SHA. |
| Physical prototype | Open | [Physical validation gate](ROADMAP.md#physical-validation-gate) | Requires the owner's two boards and optical setup. |

## Implementation evidence

- `serial/`, `tx/`, and `rx/backends/physical.py` now correlate STREAM replies with the current transaction, bound framing and multipart staging, and preserve session ownership across interruption. RX saves a verified file under a non-clobbering destination and records terminal errors when USB or storage interrupts delivery. POSIX publication needs hard-link support in the destination filesystem. Windows uses a non-overwriting same-directory rename.
- `app_state.py`, `data/records.py`, and the Inspect, Analyzer, and Export pages give each physical receipt its own capture ID. They persist CRC and measured telemetry independently of reference comparison and protect historical files and experiments during restoration.
- `OpenVLC-v3.spec`, the GitHub workflows, and `THIRD_PARTY_NOTICES.md` add build provenance, truthful smoke checks, real fonts, and license material. Exact dependency and icon attribution audit and the owner's Qt distribution choice remain release gates.
