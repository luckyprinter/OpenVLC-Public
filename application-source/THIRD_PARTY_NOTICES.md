# Third-Party Notices

This file is an engineering inventory for the direct application dependencies and selected runtime assets. It is not legal advice or a complete substitute for auditing the exact wheels and binaries used in each release.

The PyInstaller specification collects license and notice files found in the installed runtime dependency distributions into the packaged application's `third_party_licenses/` directory and includes this notice file.

## Runtime dependencies

| Component | License / distribution notes |
|---|---|
| PySide6, PySide6 Essentials, PySide6 Addons, Shiboken6 | Qt for Python Community Edition is offered under LGPLv3/GPLv3; Qt also offers commercial packages. See the official [Qt for Python licensing](https://doc.qt.io/qtforpython-6/) and [commercial-use guidance](https://doc.qt.io/qtforpython-6/commercial/index.html). |
| pyserial | BSD license. Preserve the copyright, conditions, and disclaimer in redistributed copies. |
| pyqtgraph | MIT license. Preserve the copyright and permission notice. |
| qtawesome | MIT license for the Python package. Its bundled icon fonts have separate licenses; see the font inventory below. |
| NumPy | BSD 3-Clause for the main project. PyPI wheels may bundle additional libraries, including OpenBLAS and the GNU Fortran runtime, with their own license terms. See the [NumPy license notes](https://numpy.org/doc/stable/license.html). |
| QtPy | MIT license; installed as a QtAwesome compatibility dependency when required. |

## QtAwesome bundled icon fonts

QtAwesome's Python package is MIT-licensed, but its bundled font assets are not all under the same license:

- Font Awesome and Elusive Icons: SIL Open Font License.
- Phosphor: MIT.
- Material Design Icons and Remix Icon: Apache License 2.0.
- Microsoft's Codicons: Creative Commons Attribution 4.0 International.

The upstream [QtAwesome project](https://github.com/spyder-ide/qtawesome) documents these separate font licenses. Preserve the relevant notices and attribution when redistributing the fonts.

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
5. Inspect the final Windows and Linux packages to confirm that the collected `third_party_licenses/` files are present.
