# OpenVLC Academy

An interactive, mobile-first engineering course for understanding the physical ESP32 visible-light communication prototype, from the optical hardware and protocol to the firmware and desktop application code.

## Source provenance

- **Academy source:** synchronized from hosted Academy version 5, source commit `1c0b64dda5a221630081b21f9e2fdb0bb3d90f39`.
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
- An interactive transfer lab with a teaching model for frames, noise, CRC, and reconstruction.
- Playwright responsive smoke tests covering the home, signal journey, code studio, and focused lessons at 320, 360, 390, 430, 768, 1024, and 1366 CSS-pixel widths; CI stores screenshots as workflow artifacts.

## Accuracy and teaching policy

The website distinguishes the physical prototype from explanatory models. It does not present a simulation backend as the experimental system, invent live optical telemetry, or imply that CI proves ESP32/USB/optical performance. Source excerpts must match the pinned repository commit and displayed line numbers. The thesis remains authoritative for experimental methodology and measured results.

## Local development

Run from `docs/academy` with Node.js 22 and npm.

```bash
npm ci
npm run dev
npm run build
npm test
npm run test:source -- ../..
```

The visual test command expects Chromium installed through `npx playwright install --with-deps chromium`.

## Deployment

The public [Academy on GitHub Pages](https://luckyprinter.github.io/lifi/academy/) serves the same build as the [hosted Academy](https://openvlc-academy-preview.awareclock514.chatgpt.site). It is published from the `academy/` directory of `luckyprinter/lifi`'s `gh-pages` branch. The Academy workflow builds and tests the in-repository copy.
