# OpenVLC Academy

An interactive, mobile-first engineering course for understanding the physical ESP32 visible-light communication prototype, from the optical hardware and protocol to the firmware and desktop application code.

## Source provenance

- **Academy source:** imported from [luckyprinter/lifi](https://github.com/luckyprinter/lifi/tree/99f8fc6d1159101c3aa459b45deca8da28f1eba6).
- **Lesson snapshot:** the running Academy pins firmware and application source to OpenVLC-Public commit `411f183a8592d8285118f613bb4909c5bbd9d3cc`, preserved on `archive/legacy-main`. Keep that pin until the linked code excerpts and file index are reviewed together.
- Consult the [OpenVLC documentation hub](../README.md) for current setup and validation evidence.
- The physical architecture is the teaching focus. Conceptual animations explain the signal path; they are not live hardware telemetry or measured oscilloscope captures.

## Learning experiences

- Six progressive learning paths from project orientation to coding practice.
- An eight-stage animated physical signal journey.
- Responsive, stage-specific visual models rather than one cropped desktop diagram.
- Source code studio with pinned commit links, exact line ranges, syntax highlighting, and selectable line-by-line explanations.
- Initial guided examples for TX application state, USB serial handshake, 4B5B encoding, GPIO symbol output, frame construction, RX majority sampling, byte decoding, and frame validation.
- A short knowledge-check interaction.
- Playwright responsive smoke tests covering the home, signal journey, code studio, and focused lessons at 320, 360, 390, 430, 768, 1024, and 1366 CSS-pixel widths; CI stores screenshots as workflow artifacts.

## Accuracy and teaching policy

The website distinguishes the physical prototype from explanatory models. It does not present a simulation backend as the experimental system, invent live optical telemetry, or imply that CI proves ESP32/USB/optical performance. Source excerpts must match the pinned repository commit and displayed line numbers. The thesis remains authoritative for experimental methodology and measured results.

## Local development

Run from `docs/academy` with Node.js 22 and npm.

```bash
npm ci
npm run dev
npm run build
```

The visual test command expects Chromium installed through `npx playwright install --with-deps chromium`.

## Deployment

The [existing public Academy](https://openvlc-academy-preview.awareclock514.chatgpt.site) is linked from the repository. The Academy workflow builds and tests the in-repository copy. To serve it from this repository, a maintainer can select GitHub Actions as the Pages source in repository settings and run **Build OpenVLC Academy** from `main` with **Deploy to GitHub Pages** selected.
