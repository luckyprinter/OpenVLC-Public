# OpenVLC release roadmap

OpenVLC is a two-ESP32 visible light communication prototype for short-range indoor academic experiments. The physical TX, optical link, RX, and saved payload are the basis for release validation. The desktop simulation has its own local transport and records.

## Candidate

Draft PR [#18](https://github.com/luckyprinter/OpenVLC-Public/pull/18), branch `redesign/product-shell-method2`, started at `80ef4afa63a3fe571ffd5026560bf7d7d90fbecc`. The last implementation commit is `acc161e78c56556a126cde7143783cde77f4ff26`. Its exact and PR merge builds passed on Windows and Ubuntu. The [validation matrix](VALIDATION_MATRIX.md) records the commands, run links, coverage, and remaining gates.

## Release sequence

1. **Application baseline.** Local collection, 265 tests, and source smoke passed after recovery. Physical mode remains the default. UDP simulation has separate inputs, outputs, and capture handling.
2. **Physical workflows and measurements.** Host regressions exercise serial framing, interrupted receives, CRC and file publication, and exact capture identity. Method 2 compares actual files. User settings and receiver database updates preserve legacy data and recover from interrupted restore. Hardware verification is still required.
3. **Packaging and UI.** Both sketches compiled. Windows and Linux each passed 322 tests, source and packaged smoke, and a 288-image geometry matrix across four logical viewport sizes and three scale factors. Screenshot review led to corrections in RX Export, TX Connection, and both Diagnostics pages. Packages contain the tested commit, fonts, and available license texts.
4. **Stack integration.** Review #7 → #15 → #16 → #17 → #18. PR #15 starts from `ad465019`, one commit before #7's original `733b802` head. Carry forward #7's validation workflow change and check for patch-equivalent changes before approving each merge. Recheck the integrated candidate and record both the PR merge checkout and the exact implementation SHA.
5. **Prototype and release.** Record the owner-run hardware evidence below. Confirm exact bundled-component notices and the intended academic distribution with the owner before publication. OAEL 1.0 commercial distribution requires separate written permission from the copyright holder.

## Continuation

Run the physical validation checklist below against the candidate packages linked in the [validation matrix](VALIDATION_MATRIX.md). Record firmware SHA, port mappings, reconstructed files, and measurement results. Confirm the intended academic distribution and the bundled component obligations. For software follow-ups, dispatch `build_application.yml` with the full candidate SHA as `source_ref` and an empty `release_tag`, then review both jobs and any updated screenshots. The public `v1.0.0` tag refers to `30c3e682c87755955b6601f0c9cda4c3f8dcf47c`, an earlier implementation. [Application build history](https://github.com/luckyprinter/OpenVLC-Public/actions/workflows/build_application.yml?query=branch%3Aredesign%2Fproduct-shell-method2)

## Physical validation gate

- With the production LED driver, photodiode circuit, and both flashed boards, record OS, USB adapter and port mappings, wiring revision, firmware SHA, and link settings. Test simultaneous TX/RX sessions, swapped roles, busy ports, manual selection, and unplug/replug with a changed port identifier.
- Send a short binary payload, a multipart file that crosses the 512-chunk limit, and a file near the supported limit. Check reconstructed bytes, per-transfer CRC, and Method 2 against the originals. Interrupt a transfer and verify a truthful terminal state and a successful subsequent send.
- Observe Vref calibration and PVo/Vref/margin changes under real optical conditions. Current firmware sends low-rate telemetry and discards incomplete RAM payloads at timeout. Symbol-rate OOK analysis and BER of unsaved partial payloads require additional firmware support.
