"""Make the store screenshots from the real window, without a display.

    QT_QPA_PLATFORM=offscreen python tools/screenshots.py [lang]

Writes ``flatpak/screenshots/*.png``. The documents are built here, so the
pictures can be made again for every release and in any language Plico speaks
(English by default, the store's language). The window is the real MainWindow
driven through the same commands the user's clicks push; only the window
manager's frame is missing, because offscreen there is none.

Needs the Breeze icon theme and a sans-serif font installed (on Debian/Ubuntu:
``breeze-icon-theme fonts-noto-core``) and ``pyside6-lrelease`` or ``lrelease``
in the PATH.
"""

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pymupdf
from PySide6.QtCore import QLocale, Qt, QTranslator
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "flatpak" / "screenshots"
SIZE = (1280, 800)

REPORT = """
<h1 style="font-family: sans-serif; color: #1d3557;">Annual Report 2026</h1>
<p style="font-family: sans-serif; color: #555;">Northwind Cooperative &middot; Board of Directors</p>
<h2 style="font-family: sans-serif; color: #1d3557;">1. Summary</h2>
<p style="font-family: serif; font-size: 11pt; text-align: justify;">
The cooperative closed the year with revenue of <b>4.2 million</b>, up 12% on the
previous year, driven by the new regional warehouses and by the growth of online
orders. Operating costs rose less than revenue, and the margin improved for the
third year in a row.</p>
<p style="font-family: serif; font-size: 11pt; text-align: justify;">
The board proposes to reinvest most of the result in the energy efficiency plan
approved in March, and to distribute the remainder to members in proportion to
their purchases.</p>
<h2 style="font-family: sans-serif; color: #1d3557;">2. Key figures</h2>
<table style="font-family: sans-serif; font-size: 10pt; border-collapse: collapse; width: 100%;">
<tr style="background: #1d3557; color: white;"><th>Item</th><th>2025</th><th>2026</th></tr>
<tr><td>Revenue</td><td>3.75 M</td><td>4.20 M</td></tr>
<tr style="background: #eef2f7;"><td>Operating costs</td><td>3.31 M</td><td>3.62 M</td></tr>
<tr><td>Members</td><td>1,840</td><td>2,115</td></tr>
<tr style="background: #eef2f7;"><td>Warehouses</td><td>3</td><td>5</td></tr>
</table>
<h2 style="font-family: sans-serif; color: #1d3557;">3. Contact</h2>
<p style="font-family: serif; font-size: 11pt;">
Treasurer: Jane Holloway &middot; jane.holloway@northwind.example<br/>
Bank account: IBAN GB33 BUKB 2020 1555 5555 55</p>
"""

PAGES = [
    REPORT,
    """<h2 style="font-family: sans-serif; color: #1d3557;">4. Warehouses</h2>
    <p style="font-family: serif; font-size: 11pt; text-align: justify;">
    The two new warehouses in Leeds and Bristol opened in May and September. Both run
    on rooftop solar panels and share the routing system introduced last year, which
    cut the average delivery time from three days to two.</p>
    <p style="font-family: serif; font-size: 11pt; text-align: justify;">
    The Manchester site will be renovated in the spring; during the works its orders
    will be served from Leeds.</p>""",
    """<h2 style="font-family: sans-serif; color: #1d3557;">5. Outlook</h2>
    <p style="font-family: serif; font-size: 11pt; text-align: justify;">
    For next year the board expects moderate growth, with the energy plan reducing
    costs from the second half. Membership is expected to pass 2,400.</p>""",
]


def _chart(page: pymupdf.Page, top: float) -> None:
    """A small bar chart, drawn as vectors like an office suite would."""
    bars = [(0.55, "#a8c5e2"), (0.68, "#7aa6d1"), (0.74, "#4f86c0"), (0.9, "#1d3557")]
    for i, (height, colour) in enumerate(bars):
        x = 90 + i * 110
        rect = pymupdf.Rect(x, top + 150 * (1 - height), x + 70, top + 150)
        page.draw_rect(rect, color=None, fill=pymupdf.utils.getColor("white"))
        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(fill=tuple(int(colour[k : k + 2], 16) / 255 for k in (1, 3, 5)), color=None)
        shape.commit()
        page.insert_text((x + 18, top + 168), str(2023 + i), fontsize=9, fontname="helv")


def report(path: Path) -> None:
    with pymupdf.open() as doc:
        for index, html in enumerate(PAGES):
            page = doc.new_page(width=595, height=842)
            page.insert_htmlbox(pymupdf.Rect(60, 60, 535, 790), html)
            if index == 1:
                _chart(page, 330)
        doc.save(path)


def form(path: Path) -> None:
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_htmlbox(
            pymupdf.Rect(60, 50, 535, 140),
            '<h1 style="font-family: sans-serif; color: #1d3557;">Membership application</h1>'
            '<p style="font-family: sans-serif; color: #555;">Please fill in every field.</p>',
        )
        rows = [("Full name", "name", 160), ("Address", "address", 215), ("Email", "email", 270)]
        for label, name, y in rows:
            page.insert_text((60, y), label, fontsize=11, fontname="helv")
            widget = pymupdf.Widget()
            widget.field_name = name
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            widget.rect = pymupdf.Rect(60, y + 8, 535, y + 32)
            page.add_widget(widget)
        page.insert_text((60, 330), "Membership", fontsize=11, fontname="helv")
        choice = pymupdf.Widget()
        choice.field_name = "membership"
        choice.field_type = pymupdf.PDF_WIDGET_TYPE_COMBOBOX
        choice.choice_values = ["Individual", "Family", "Business"]
        choice.field_value = "Individual"
        choice.rect = pymupdf.Rect(60, 338, 300, 362)
        page.add_widget(choice)
        tick = pymupdf.Widget()
        tick.field_name = "consent"
        tick.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
        tick.rect = pymupdf.Rect(60, 392, 76, 408)
        page.add_widget(tick)
        page.insert_text((86, 405), "I agree to the cooperative's statute", fontsize=11)
        doc.save(path)


def pump(app: QApplication, seconds: float = 1.2) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def translator(app: QApplication, language: str, scratch: Path) -> None:
    from plico import i18n

    i18n.install_qt_translator(app, QLocale(language))
    if language == "it":
        return
    tool = shutil.which("lrelease") or shutil.which("pyside6-lrelease")
    if tool is None:
        sys.exit("serve lrelease o pyside6-lrelease nel PATH")
    compiled = scratch / f"plico_{language}.qm"
    subprocess.run(
        [tool, str(ROOT / "src/plico/translations" / f"plico_{language}.ts"), "-qm", str(compiled)],
        check=True,
        capture_output=True,
    )
    loaded = QTranslator(app)
    if not loaded.load(str(compiled)):
        sys.exit(f"catalogo illeggibile: {compiled}")
    app.installTranslator(loaded)


def ready(mw) -> None:
    """The status bar as the user sees it, not the scratch path of this script."""
    from PySide6.QtCore import QCoreApplication

    mw._status.setText(QCoreApplication.translate("MainWindow", "Pronto"))


def window(app: QApplication, settings_dir: Path, form_dock: bool = False):
    from PySide6.QtCore import QSettings

    from plico.main_window import MainWindow

    # Never the user's own window layout: a fresh, throw-away settings file.
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(settings_dir))
    mw = MainWindow()
    mw.resize(*SIZE)
    mw.findChild(object, "undo_dock").hide()  # a developer's tool, not the app
    if not form_dock:
        mw._form_dock.hide()
    mw.show()
    return mw


def main() -> None:
    language = sys.argv[1] if len(sys.argv) > 1 else "en"
    app = QApplication.instance() or QApplication([])
    # The desktop gives Qt its icon directories; offscreen nobody does.
    QIcon.setThemeSearchPaths([*QIcon.themeSearchPaths(), "/usr/share/icons"])
    QIcon.setThemeName("breeze")
    app.setFont(QFont("Noto Sans", 10))
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        translator(app, language, scratch)
        report(scratch / "annual-report-2026.pdf")
        form(scratch / "membership-application.pdf")
        shots: list[str] = []

        # 1. The document, its pages, fit to width.
        mw = window(app, scratch / "settings")
        mw.open_document(str(scratch / "annual-report-2026.pdf"))
        mw._page_view.set_zoom_fit_width()
        pump(app)
        ready(mw)
        shots.append(_save(mw, "main"))

        # 2. Erasing what must not leave the office: marks on the private data.
        from plico.model.commands import AddRedaction

        for word in ("Jane Holloway", "jane.holloway@northwind.example", "GB33 BUKB 2020 1555 5555 55"):
            for index, rects in mw._doc_model.find_text(word).items():
                for rect in rects:
                    mw._undo_stack.push(AddRedaction(mw._doc_model, index, rect))
        mw._select_act.setChecked(True)
        mw._on_selection_toggled(True)
        mw._page_view.set_zoom_fit_width()
        pump(app, 0.3)
        mw._page_view.verticalScrollBar().setValue(330)
        pump(app)
        shots.append(_save(mw, "redact"))
        mw.shutdown_worker()
        mw.deleteLater()

        # 3. A form, filled in on the page.
        mw = window(app, scratch / "settings", form_dock=True)
        mw.open_document(str(scratch / "membership-application.pdf"))
        for name, value in (
            ("name", "Jane Holloway"),
            ("address", "14 Mill Lane, Leeds LS1 4AB"),
            ("email", "jane.holloway@northwind.example"),
            ("membership", "Family"),
            ("consent", "Yes"),
        ):
            mw._set_field_value(0, name, value)
        mw._refresh_form_panel(0)
        mw._form_dock.show()
        mw.resizeDocks([mw._form_dock], [330], Qt.Orientation.Horizontal)
        pump(app, 0.3)
        mw._page_view.set_zoom_fit_width()
        pump(app)
        ready(mw)
        shots.append(_save(mw, "form"))
        mw.shutdown_worker()
        mw.deleteLater()

        # 4. Correcting a line where it stands.
        mw = window(app, scratch / "settings")
        mw.open_document(str(scratch / "annual-report-2026.pdf"))
        mw._page_view.set_zoom(1.5)
        pump(app, 0.4)
        mw._text_act.setChecked(True)
        mw._on_text_mode_toggled(True)
        canvas = mw._page_view._canvases[0]
        hit = mw._doc_model.find_text("4.2 million")[0][0]
        mw._page_view.begin_text_edit(canvas, (hit.x0 + hit.x1) / 2, (hit.y0 + hit.y1) / 2)
        editor = mw._page_view.text_editor()
        if editor is not None:
            editor.setText(editor.text().replace("4.2 million", "4.3 million"))
        pump(app)
        ready(mw)
        shots.append(_save(mw, "edit"))
        mw.shutdown_worker()
        mw.deleteLater()
        pump(app, 0.2)
    print("\n".join(shots))


def _save(mw, name: str) -> str:
    path = OUT / f"{name}.png"
    if not mw.grab().save(str(path)):
        sys.exit(f"impossibile scrivere {path}")
    return str(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
