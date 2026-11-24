# Third-Party Notices

This file is an engineering inventory for the direct application dependencies and selected runtime assets. It is not legal advice or a complete substitute for auditing the exact wheels and binaries used in each release.

The PyInstaller specification collects licenses and notices from installed runtime dependencies into `_internal/third_party_licenses/`. It also includes `third-party-licenses/` from this source tree in `_internal/third_party_licenses/upstream/` and includes this notice and the project `LICENSE` in `_internal/`.

## Runtime dependencies

| Component | License / distribution notes |
|---|---|
| PySide6, PySide6 Essentials, PySide6 Addons, Shiboken6 | The 6.10.1 Python wheels identify LGPL-3.0-only, GPL-2.0-only, or GPL-3.0-only alternatives. The corresponding upstream texts accompany this package. Verify the licensing of the exact Qt binaries and modules as part of distribution review. [Qt for Python 6.10.1 source](https://github.com/pyside/pyside-setup/tree/v6.10.1) |
| pyserial | BSD license. The copyright, conditions, and disclaimer accompany this package. [pyserial 3.5 license](https://github.com/pyserial/pyserial/blob/v3.5/LICENSE.txt) |
| pyqtgraph | MIT license. Preserve the copyright and permission notice. |
| qtawesome | MIT license for the Python package. Its bundled icon fonts have separate licenses; see the font inventory below. |
| NumPy | BSD 3-Clause for the main project. The pinned 2.5.1 release requires Python 3.12 or newer. PyPI wheels may bundle additional libraries, including OpenBLAS and the GNU Fortran runtime, with their own license terms. See the [NumPy license notes](https://numpy.org/doc/stable/license.html). |
| QtPy | MIT license; installed as a QtAwesome compatibility dependency when required. |

## QtAwesome bundled icon fonts

QtAwesome's Python package is MIT-licensed, but its bundled font assets are not all under the same license:

- Font Awesome and Elusive Icons: SIL Open Font License.
- Phosphor: MIT.
- Material Design Icons and Remix Icon: Apache License 2.0.
- Microsoft's Codicons: Creative Commons Attribution 4.0 International.

The upstream notice folder includes pinned notices for Codicons 0.0.36, Font Awesome 5.15.4 and 6.7.2, Material Design Icons 5.9.55 and 6.9.96, Phosphor 1.3.0, and Remix Icon 2.5.0. Refer to the upstream licensing of Elusive Icons for its font attribution. [QtAwesome 1.4.2](https://github.com/spyder-ide/qtawesome/tree/v1.4.2) · [Elusive Icons font licensing](https://github.com/dovy/elusive-icons/blob/master/src/license.html)

## OpenVLC interface fonts

The application bundles the following font files and their SIL Open Font License 1.1 texts in `gui_dev_v3/assets/fonts/`.

| Font file | License text | Source |
|---|---|---|
| `FiraCode-Regular.ttf` | `FiraCode-OFL.txt` | [Google Fonts Fira Code variable font](https://github.com/google/fonts/tree/30485dad1f47216a16c95042e455d0a3105e031c/ofl/firacode) |
| `Inter-Regular.ttf` | `Inter-OFL.txt` | [Inter 4.1 release archive](https://github.com/rsms/inter/releases/tag/v4.1) |
| `JetBrainsMono-Regular.ttf` | `JetBrainsMono-OFL.txt` | [JetBrains Mono upstream build](https://github.com/JetBrains/JetBrainsMono/tree/02bb50b082dad9ef8a0f33ac393839202b760223) |
| `PlusJakartaSans-Regular.ttf` | `PlusJakartaSans-OFL.txt` | [Plus Jakarta Sans upstream build](https://github.com/tokotype/PlusJakartaSans/tree/18d1cd2f7ea10481919d2f05c1f7064b7307fc26) |
| `SpaceMono-Regular.ttf` | `SpaceMono-OFL.txt` | [Space Mono upstream build](https://github.com/googlefonts/spacemono/tree/329858c2c4dbd3476f972a4ae00624b018cf4b81) |

## Build and test tools

- **PyInstaller** is a build-time dependency, not an application runtime dependency. It uses GPL-2.0 with an exception and Apache-2.0 for certain files. Its published exception permits distributing applications bundled from your own source under another license, provided the bundled dependencies' licenses are respected. See the [PyInstaller license](https://www.pyinstaller.org/en/stable/license.html).
- **pytest** is used for development and automated testing; it is not required by the installed application.

## Project license

The repository's `LICENSE` is the project-authored OpenVLC Academic Evaluation License (OAEL) 1.0. It restricts commercial use of the project materials unless the copyright holder grants separate written permission. A commercial product release therefore requires a deliberate project-license decision in addition to third-party dependency compliance.

## Release checklist

Before distributing a commercial or public binary:

1. Audit the exact dependency lock and platform-specific wheels used for that release.
2. Verify that every runtime library and bundled asset has its applicable license text and attribution in the package.
3. Choose and document a Qt licensing route: comply with all LGPLv3 requirements for the exact bundled Qt components, or use the appropriate Qt commercial package/license.
4. Confirm that the project license grants the intended distribution and commercial rights.
5. Inspect the final Windows and Linux packages for the collected runtime licenses, bundled font licenses, notices, and project `LICENSE`.
