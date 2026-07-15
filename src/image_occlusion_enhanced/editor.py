# -*- coding: utf-8 -*-

# Image Occlusion Enhanced Add-on for Anki
#
# Copyright (C) 2016-2020  Aristotelis P. <https://glutanimate.com/>
# Copyright (C) 2012-2015  Tiago Barroso <tmbb@campus.ul.pt>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version, with the additions
# listed at the end of the license file that accompanied this program.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# NOTE: This program is subject to certain additional terms pursuant to
# Section 7 of the GNU Affero General Public License.  You should have
# received a copy of these additional terms immediately following the
# terms and conditions of the GNU Affero General Public License that
# accompanied this program.
#
# If not, please request a copy through one of the means of contact
# listed here: <https://glutanimate.com/contact/>.
#
# Any modifications to this file must keep this entire header intact.

"""
Image Occlusion editor dialog
"""

import json
import os

from anki.hooks import addHook, remHook
from aqt import deckchooser, mw, webview
from aqt.editor import Editor, EditorMode
from aqt.qt import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QEvent,
    QHBoxLayout,
    QIcon,
    QKeySequence,
    QLabel,
    QMovie,
    QPushButton,
    QShortcut,
    QSize,
    QSizePolicy,
    QTabBar,
    QTimer,
    Qt,
    QVBoxLayout,
    QWIDGETSIZE_MAX,
    QWidget,
    sip,
    pyqtSignal,
)
from aqt.utils import restoreGeom, saveGeom, askUser

from .config import *
from .compact_ui import (
    ADD_BUTTON_LABELS,
    TAB_LABELS,
    TAB_NAMES,
    bounded_default_editor_height,
)
from .consts import *
from .dialogs import ioHelp
from .lang import _


class ImgOccWebPage(webview.AnkiWebPage):
    def acceptNavigationRequest(self, url, navType, isMainFrame):
        return True


class ImgOccWebView(webview.AnkiWebView):

    escape_pressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._domDone = False
        self._native_zoom_anchor = None
        self.setZoomFactor(1.0)
        QApplication.instance().installEventFilter(self)

    def _keep_editor_zoom_fixed(self, zoom_factor):
        """Prevent Chromium from scaling the complete SVG editor interface"""
        if zoom_factor != 1.0:
            self.setZoomFactor(1.0)

    def eventFilter(self, watched, event):
        """Route native gestures from WebEngine's child widget to the SVG canvas."""
        if event.type() != QEvent.Type.NativeGesture:
            return super().eventFilter(watched, event)

        target = watched
        while target is not None and target is not self:
            target = target.parent()
        if target is not self:
            return super().eventFilter(watched, event)

        global_position = event.globalPosition().toPoint()
        position = self.mapFromGlobal(global_position)

        gesture_type = event.gestureType()
        if gesture_type == Qt.NativeGestureType.BeginNativeGesture:
            self._native_zoom_anchor = (position.x(), position.y())
            event.accept()
            return True

        if gesture_type == Qt.NativeGestureType.ZoomNativeGesture:
            if self._native_zoom_anchor is None:
                self._native_zoom_anchor = (position.x(), position.y())
            anchor_x, anchor_y = self._native_zoom_anchor
            self.eval(
                "window.ioNativeGestureZoom && "
                f"window.ioNativeGestureZoom({float(event.value())!r}, "
                f"{float(anchor_x)!r}, {float(anchor_y)!r});"
            )
            event.accept()
            return True

        if gesture_type == Qt.NativeGestureType.EndNativeGesture:
            self._native_zoom_anchor = None
            event.accept()
            return True

        if gesture_type == Qt.NativeGestureType.RotateNativeGesture:
            # Pinch streams may interleave rotation events. Do not let Chromium
            # reinterpret them as page-level navigation or scaling.
            event.accept()
            return True

        return super().eventFilter(watched, event)

    def _onBridgeCmd(self, cmd):
        # ignore webchannel messages that arrive after underlying webview
        # deleted
        if sip.isdeleted(self):
            return

        if cmd == "domDone":
            return

        if cmd == "svgEditDone":
            self._domDone = True
            self._maybeRunActions()
        else:
            return self.onBridgeCmd(cmd)

    def runOnLoaded(self, callback):
        self._domDone = False
        self._queueAction("callback", callback)

    def _maybeRunActions(self):
        while self._pendingActions and self._domDone:
            name, args = self._pendingActions.pop(0)

            if name == "eval":
                self._evalWithCallback(*args)
            elif name == "setHtml":
                self._setHtml(*args)
            elif name == "callback":
                callback = args[0]
                callback()
            else:
                raise Exception(
                    _("unknown action: {action_name}").format(action_name=name)
                )

    def onEsc(self):
        self.escape_pressed.emit()


class ImgOccFieldEditor(Editor):
    """Anki's real field editor, isolated from its built-in IO workflow."""

    is_imgocc_embedded_editor = True

    def current_notetype_is_image_occlusion(self):
        # Image Occlusion Enhanced keeps its own SVG editor below this field
        # area, even if a user has based the note type on Anki's stock IO type.
        return False

    def onBridgeCmd(self, cmd):
        if cmd.startswith("imgoccEditorHeight:"):
            try:
                natural_height = int(cmd.split(":", 1)[1])
            except ValueError:
                return None
            self.parentWindow.queueFieldEditorHeight(natural_height)
            return None
        return super().onBridgeCmd(cmd)


class ImgOccEdit(QDialog):
    """Main Image Occlusion Editor dialog"""

    def __init__(self, imgoccadd, parent):
        QDialog.__init__(self)
        mw.setupDialogGC(self)
        self.setWindowFlags(Qt.WindowType.Window)
        self.visible = False
        self.imgoccadd = imgoccadd
        self.parent = parent
        self.mode = "add"
        self.card_creation_integration = None
        self.field_editor = None
        self.field_note = None
        self._initial_input_state = None
        self._close_check_pending = False
        self._closing = False
        # Give Anki's web editor enough room for its first render. Once loaded,
        # the DOM observer replaces this bootstrap value with the natural size.
        self._field_editor_natural_height = 120
        self._svg_ready = False
        self._field_height_timer = QTimer(self)
        self._field_height_timer.setSingleShot(True)
        self._field_height_timer.timeout.connect(self._applyQueuedFieldEditorHeight)
        loadConfig(self)
        self.setupUi()
        restoreGeom(self, "imgoccedit")
        try:
            from aqt.gui_hooks import profile_will_close

            profile_will_close.append(self.onProfileUnload)
        except (ImportError, ModuleNotFoundError):
            addHook("unloadProfile", self.onProfileUnload)

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        event.ignore()
        self.reject()

    def _on_close(self):
        if self._closing:
            return
        self._closing = True
        if mw.pm.profile is not None:
            self.deckChooser.cleanup()
            saveGeom(self, "imgoccedit")
        self.visible = False
        if self.field_editor is not None:
            self.field_editor.cleanup()
            self.field_editor = None
            self.field_note = None
        if hasattr(self.svg_edit, "cleanup"):  # 2.1.50+
            self.svg_edit.cleanup()  # type: ignore
        self.svg_edit = None
        del self.svg_edit_anim  # might not be gc'd
        try:
            from aqt.gui_hooks import profile_will_close

            profile_will_close.remove(self.onProfileUnload)
        except (ImportError, ModuleNotFoundError):
            remHook("unloadProfile", self.onProfileUnload)
        QDialog.reject(self)

    def onProfileUnload(self):
        if not sip.isdeleted(self):
            self._on_close()

    def reject(self):
        if not self.svg_edit:
            return super().reject()
        if self._close_check_pending:
            return
        self._close_check_pending = True

        def check_svg_changes():
            if not self.svg_edit:
                self._close_check_pending = False
                return
            self.svg_edit.evalWithCallback(
                "svgCanvas.undoMgr.getUndoStackSize() == 0",
                self._on_reject_callback,
            )

        self.flushFieldEditor(check_svg_changes)

    def _on_reject_callback(self, undo_stack_empty: bool):
        self._close_check_pending = False
        if (undo_stack_empty and not self._input_modified()) or askUser(
            "Are you sure you want to close the window? This will discard any unsaved"
            " changes.",
            title="Exit Image Occlusion?",
        ):
            self._on_close()

    def _input_modified(self) -> bool:
        if self.field_note is None or self._initial_input_state is None:
            return False
        return self._current_input_state() != self._initial_input_state

    def setupUi(self):
        """Set up ImgOccEdit UI"""
        # Main widgets aside from fields
        self.svg_edit = ImgOccWebView(parent=self)
        self.svg_edit._page = ImgOccWebPage(self.svg_edit._onBridgeCmd)
        self.svg_edit.setPage(self.svg_edit._page)
        self.svg_edit._page.zoomFactorChanged.connect(
            self.svg_edit._keep_editor_zoom_fixed
        )

        self.svg_edit.escape_pressed.connect(self.reject)

        self.deck_container = QWidget()
        self.deckChooser = deckchooser.DeckChooser(mw, self.deck_container, label=True)
        self.deckChooser.deck.setAutoDefault(False)

        # workaround for tab focus order issue of the tags entry
        # (this particular section is only needed when the quick deck
        # buttons add-on is installed)
        if self.deck_container.layout().children():  # multiple deck buttons
            for i in range(self.deck_container.layout().children()[0].count()):
                try:
                    item = self.deck_container.layout().children()[0].itemAt(i)
                    # remove Tab focus manually:
                    item.widget().setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                    item.widget().setAutoDefault(False)
                except AttributeError:
                    pass

        # Button row widgets
        button_box = QDialogButtonBox(Qt.Orientation.Horizontal, self)
        button_box.setCenterButtons(False)

        image_btn = QPushButton()
        image_btn.clicked.connect(self.changeImage)
        image_btn.setIcon(QIcon(os.path.join(ICONS_PATH, "add.png")))
        image_btn.setIconSize(QSize(16, 16))
        image_btn.setAutoDefault(False)
        image_btn.setAccessibleName(_("Change Image"))
        self.image_btn = image_btn

        self.occl_tp_select = QComboBox()
        self.occl_tp_select.addItem(_("Don't Change"), "Don't Change")
        self.occl_tp_select.addItem(_("Hide All, Guess One"), "Hide All, Guess One")
        self.occl_tp_select.addItem(_("Hide One, Guess One"), "Hide One, Guess One")

        self.edit_btn = button_box.addButton(
            _("&Edit Cards"), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.new_btn = button_box.addButton(
            _("&Add New Cards"), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.ao_btn = button_box.addButton(
            _(ADD_BUTTON_LABELS[0]), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.oa_btn = button_box.addButton(
            _(ADD_BUTTON_LABELS[1]), QDialogButtonBox.ButtonRole.ActionRole
        )
        close_button = button_box.addButton(
            _(ADD_BUTTON_LABELS[2]), QDialogButtonBox.ButtonRole.RejectRole
        )
        close_button.setAccessibleName(_("Close"))

        image_tt = _(
            "Switch to a different image while preserving all of the shapes and fields"
        )
        dc_tt = _("Preserve existing occlusion type")
        edit_tt = _("Edit all cards using current mask shapes and field entries")
        new_tt = _("Create new batch of cards without editing existing ones")
        ao_tt = _(
            "Generate cards with nonoverlapping information, where all"
            "<br>labels are hidden on the front and one revealed on the"
            " back"
        )
        oa_tt = _(
            "Generate cards with overlapping information, where one<br>"
            "label is hidden on the front and revealed on the back"
        )
        close_tt = _("Close Image Occlusion Editor without generating cards")

        image_btn.setToolTip(image_tt)
        self.edit_btn.setToolTip(edit_tt)
        self.new_btn.setToolTip(new_tt)
        self.ao_btn.setToolTip(ao_tt)
        self.oa_btn.setToolTip(oa_tt)
        close_button.setToolTip(close_tt)
        self.occl_tp_select.setItemData(0, dc_tt, Qt.ItemDataRole.ToolTipRole)
        self.occl_tp_select.setItemData(1, ao_tt, Qt.ItemDataRole.ToolTipRole)
        self.occl_tp_select.setItemData(2, oa_tt, Qt.ItemDataRole.ToolTipRole)

        for btn in [
            image_btn,
            self.edit_btn,
            self.new_btn,
            self.ao_btn,
            self.oa_btn,
            close_button,
        ]:
            btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            btn.setDefault(False)
            btn.setAutoDefault(False)

        # self.ao_btn.setDefault(True)

        self.edit_btn.clicked.connect(self.editNote)
        self.new_btn.clicked.connect(self.new)
        self.ao_btn.clicked.connect(self.addAO)
        self.oa_btn.clicked.connect(self.addOA)
        close_button.clicked.connect(self.reject)

        # Set basic layout up

        # Button row
        bottom_hbox = QHBoxLayout()
        bottom_hbox.setContentsMargins(10, 0, 10, 10)
        bottom_hbox.addWidget(image_btn)
        self.position_layout = QHBoxLayout()
        self.position_layout.setContentsMargins(0, 0, 0, 0)
        bottom_hbox.addLayout(self.position_layout, stretch=1)
        bottom_hbox.addWidget(self.occl_tp_select)
        bottom_hbox.addWidget(button_box)

        editor_layout = QVBoxLayout()
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_layout = editor_layout

        self.primary_fields_layout = QVBoxLayout()
        self.primary_fields_layout.setContentsMargins(10, 0, 10, 0)
        editor_layout.addLayout(self.primary_fields_layout, stretch=0)

        svg_edit_loader = QLabel(_("Loading..."))
        svg_edit_loader.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loader_icon = os.path.join(ICONS_PATH, "loader.gif")
        anim = QMovie(loader_icon)
        svg_edit_loader.setMovie(anim)
        anim.start()
        self.svg_edit_loader = svg_edit_loader
        self.svg_edit_anim = anim

        editor_layout.addWidget(self.svg_edit, stretch=1)
        editor_layout.addWidget(self.svg_edit_loader, stretch=1)

        # Main Window
        vbox_main = QVBoxLayout()
        vbox_main.setContentsMargins(0, 5, 0, 5)
        vbox_main.addLayout(editor_layout)
        vbox_main.addLayout(bottom_hbox)
        self.setLayout(vbox_main)
        self.setMinimumWidth(640)
        self.svg_edit.setFocus()
        self.showSvgEdit(False)

        # Define and connect key bindings

        # Field focus hotkeys
        for i in range(1, 10):
            QShortcut(QKeySequence("Ctrl+%i" % i), self).activated.connect(
                lambda f=i - 1: self.focusField(f)
            )
        # Other hotkeys
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(
            lambda: self.defaultAction(True)
        )
        QShortcut(QKeySequence("Ctrl+Shift+Return"), self).activated.connect(
            lambda: self.addOA(True)
        )
        QShortcut(QKeySequence("Ctrl+r"), self).activated.connect(self.resetMainFields)
        QShortcut(QKeySequence("Ctrl+Shift+r"), self).activated.connect(
            self.resetAllFields
        )
        QShortcut(QKeySequence("Ctrl+Shift+t"), self).activated.connect(self.focusTags)
        QShortcut(QKeySequence("Ctrl+f"), self).activated.connect(self.fitImageCanvas)

    # Various actions that act on / interact with the ImgOccEdit UI:

    # Note actions

    def changeImage(self):
        self.imgoccadd.onChangeImage()
        self.fitImageCanvas()
        self.fitImageCanvas(delay=100)

    def defaultAction(self, close):
        if self.mode == "add":
            self.addAO(close)
        else:
            self.editNote()

    def addAO(self, close=False):
        self.flushFieldEditor(
            lambda: self.imgoccadd.onAddNotesButton("ao", close)
        )

    def addOA(self, close=False):
        self.flushFieldEditor(
            lambda: self.imgoccadd.onAddNotesButton("oa", close)
        )

    def new(self, close=False):
        choice = self.occl_tp_select.currentData()
        self.flushFieldEditor(
            lambda: self.imgoccadd.onAddNotesButton(choice, close)
        )

    def editNote(self):
        choice = self.occl_tp_select.currentData()
        self.flushFieldEditor(
            lambda: self.imgoccadd.onEditNotesButton(choice)
        )

    def onHelp(self):
        if self.mode == "add":
            ioHelp("add", parent=self)
        else:
            ioHelp("edit", parent=self)

    # Window state

    def resetFields(self):
        """Reset all widgets. Needed for changes to the note type"""
        if self.field_editor is not None:
            self.field_editor.cleanup()
            self.field_editor = None
        self.field_note = None
        for layout in [self.primary_fields_layout, self.position_layout]:
            for index in reversed(range(layout.count())):
                item = layout.takeAt(index)
                if item.widget():
                    item.widget().setParent(None)
                elif item.layout():
                    sublayout = item.layout()
                    while sublayout.count():
                        subitem = sublayout.takeAt(0)
                        if subitem.widget():
                            subitem.widget().setParent(None)
        self.card_creation_integration = None
        self._initial_input_state = None

    def setupFields(self, flds):
        """Set up Anki's native HTML field editor around a temporary note."""
        self.flds = flds
        self.field_note = mw.col.new_note(self.model)
        self._field_ord_by_name = {
            field["name"]: index for index, field in enumerate(flds)
        }
        self._title_field_name = self.ioflds["tl"]
        self._front_field_name = self.ioflds["hd"]
        self._title_field_ord = self._field_ord_by_name[self._title_field_name]
        self._front_field_ord = self._field_ord_by_name[self._front_field_name]
        self._inline_title_active = False
        self._initial_title_focus_pending = True

        self.field_tabs = QTabBar(self)
        self.field_tabs.setDocumentMode(True)
        self.field_tabs.setExpanding(False)
        self.field_tabs.setAccessibleName(_("Editor views"))
        for label, name in zip(TAB_LABELS, TAB_NAMES):
            index = self.field_tabs.addTab(label)
            self.field_tabs.setTabToolTip(index, _(name))
        self.field_tabs.setCurrentIndex(0)
        self.field_tabs.currentChanged.connect(self._apply_field_tab)

        try:
            import custom_shortcuts

            try:
                custom_shortcuts.setup_card_creation_controls(
                    self,
                    self.primary_fields_layout,
                    initial_host=self.imgoccadd.ed.parentWindow,
                    position_layout=self.position_layout,
                    inline_title_entry=True,
                    save_control="context_menu",
                    position_trailing_widget=self.field_tabs,
                    position_style="compact",
                )
                self._inline_title_active = True
            except TypeError:
                # Older custom_shortcuts releases remain usable. In that case
                # the native Title field stays visible as the safe fallback.
                custom_shortcuts.setup_card_creation_controls(
                    self,
                    self.primary_fields_layout,
                    initial_host=self.imgoccadd.ed.parentWindow,
                    position_layout=self.position_layout,
                )
                self._add_standalone_tab_row()
            self.card_creation_integration = custom_shortcuts
        except (ImportError, AttributeError):
            self.card_creation_integration = None
            self._add_standalone_tab_row()

        self.field_editor_container = QWidget(self)
        self.field_editor_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.field_editor = ImgOccFieldEditor(
            mw,
            self.field_editor_container,
            self,
            editor_mode=EditorMode.ADD_CARDS,
        )
        self.primary_fields_layout.addWidget(self.field_editor_container)
        self.primary_fields_layout.addWidget(self.deck_container)
        self.deck_container.hide()

        # callImgOccEdit() fills initial values immediately after setupFields().
        # Deferring the first load coalesces them into one native editor render.
        mw.progress.single_shot(0, self._finalize_field_setup)

    def _add_standalone_tab_row(self):
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.field_tabs)
        self.position_layout.addLayout(row)

    def _finalize_field_setup(self):
        if self.field_editor is None or self.field_note is None:
            return
        self.field_editor.set_note(self.field_note)
        self._initial_input_state = self._current_input_state()
        self._apply_field_tab(self.field_tabs.currentIndex())
        if self._inline_title_active:
            # Title is the first logical input in Default mode.  Restoring
            # focus after the asynchronous native-editor load also gives
            # keyboard users a predictable F2/type-to-edit entry point.
            self.saved_titles_list.setFocus(Qt.FocusReason.OtherFocusReason)

    def _current_input_state(self):
        if self.field_note is None:
            return None
        fields = list(self.field_note.fields)
        if self._inline_title_active:
            fields[self._title_field_ord] = self.fieldText(self._title_field_name)
        return (tuple(fields), tuple(self.field_note.tags))

    def _visible_field_ords(self, tab_index):
        if tab_index == 0:
            ords = [self._front_field_ord]
            if not self._inline_title_active:
                ords.insert(0, self._title_field_ord)
            return ords

        excluded = set(self.ioflds_priv)
        excluded.update((self._title_field_name, self._front_field_name))
        if self.mode != "add":
            excluded.update(self.sconf["skip"])
        return [
            index
            for index, field in enumerate(self.flds)
            if field["name"] not in excluded
        ]

    def _apply_field_tab(self, tab_index):
        if not hasattr(self, "field_editor_container"):
            return
        default_tab = tab_index == 0
        title_container = getattr(self, "saved_titles_container", None)
        if title_container is not None:
            title_container.setVisible(default_tab)
            if default_tab and self._inline_title_active:
                mw.progress.single_shot(
                    0,
                    lambda: self.saved_titles_list.setFocus(
                        Qt.FocusReason.OtherFocusReason
                    ),
                )
        self.deck_container.setVisible(not default_tab)
        if default_tab:
            self.field_editor_container.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self.editor_layout.setStretch(0, 0)
            self.editor_layout.setStretch(1, 1)
            self.editor_layout.setStretch(2, 1)
            self.queueFieldEditorHeight(self._field_editor_natural_height)
        else:
            self._field_height_timer.stop()
            self.field_editor_container.setMinimumHeight(0)
            self.field_editor_container.setMaximumHeight(QWIDGETSIZE_MAX)
            self.field_editor_container.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.editor_layout.setStretch(0, 1)
            self.editor_layout.setStretch(1, 0)
            self.editor_layout.setStretch(2, 0)
        self._syncSvgVisibility()

        if self.field_editor is None or self.field_note is None:
            return
        visible = self._visible_field_ords(tab_index)
        show_tags = not default_tab
        expected_fields = len(self.field_note.fields)
        view_name = json.dumps("default" if default_tab else "fields")
        script = f"""
(function () {{
  const visible = new Set({json.dumps(visible)});
  const showTags = {json.dumps(show_tags)};
  const expectedFields = {expected_fields};
  function apply(attempt) {{
    require("anki/ui").loaded.then(async function () {{
      const editors = require("anki/NoteEditor").instances;
      const editor = editors && editors[0];
      if (!editor || editor.fields.length < expectedFields) {{
        if (attempt < 30) setTimeout(function () {{ apply(attempt + 1); }}, 20);
        return;
      }}
      const toolbar = editor.toolbar && editor.toolbar.toolbar;
      if (toolbar) {{
        [
          "notetype", "settings", "inlineFormatting", "blockFormatting",
          "template", "cloze", "image-occlusion-button", "addons"
        ].forEach(function (id) {{
          try {{ toolbar.hide(id); }} catch (error) {{ /* older Anki */ }}
        }});
      }}
      await Promise.all(editor.fields.map(async function (field, index) {{
        const element = await field.element;
        if (!element) return;
        const container = element.closest(".field-container");
        if (container) container.style.display = visible.has(index) ? "" : "none";
      }}));
      const noteEditor = document.querySelector(".note-editor");
      if (!noteEditor) return;
      let style = document.getElementById("imgocc-embedded-editor-style");
      if (!style) {{
        style = document.createElement("style");
        style.id = "imgocc-embedded-editor-style";
        style.textContent = `
          html, body {{ margin: 0; overflow-x: hidden; }}
          body.imgocc-embedded-editor .editor-toolbar {{ display: none !important; }}
          body[data-imgocc-view="default"] {{ overflow-y: auto; }}
          body[data-imgocc-view="default"] .note-editor {{ height: auto !important; }}
          body[data-imgocc-view="default"] .fields {{
            flex-grow: 0 !important;
            overflow-y: visible !important;
          }}
          body[data-imgocc-view="default"] .scroll-area-relative {{
            height: auto !important;
            flex-grow: 0 !important;
          }}
          body[data-imgocc-view="default"] .scroll-area {{
            position: relative !important;
            height: auto !important;
            overflow: visible !important;
          }}
          body[data-imgocc-view="fields"] {{ overflow: hidden; }}
          body[data-imgocc-view="fields"] .note-editor {{ height: 100% !important; }}
        `;
        document.head.appendChild(style);
      }}
      document.body.classList.add("imgocc-embedded-editor");
      document.body.dataset.imgoccView = {view_name};
      const tagLabel = noteEditor.querySelector(":scope > .collapse-label");
      const tagEditor = noteEditor.querySelector(".tag-editor");
      let tagBlock = tagEditor;
      while (tagBlock && tagBlock.parentElement !== noteEditor) {{
        tagBlock = tagBlock.parentElement;
      }}
      if (tagLabel) tagLabel.style.display = showTags ? "" : "none";
      if (tagBlock) tagBlock.style.display = showTags ? "" : "none";

      if (window.imgOccHeightObserver) window.imgOccHeightObserver.disconnect();
      let framePending = false;
      function reportHeight() {{
        if (document.body.dataset.imgoccView !== "default" || framePending) return;
        framePending = true;
        requestAnimationFrame(function () {{
          framePending = false;
          const naturalHeight = Math.max(
            1, noteEditor.scrollHeight, noteEditor.offsetHeight
          );
          pycmd("imgoccEditorHeight:" + Math.ceil(naturalHeight));
        }});
      }}
      window.imgOccHeightObserver = new ResizeObserver(reportHeight);
      window.imgOccHeightObserver.observe(noteEditor);
      reportHeight();
    }});
  }}
  apply(0);
}})();
"""
        self.field_editor.web.eval(script)

    def queueFieldEditorHeight(self, natural_height):
        self._field_editor_natural_height = max(1, int(natural_height))
        if (
            hasattr(self, "field_tabs")
            and self.field_tabs.currentIndex() == 0
            and hasattr(self, "field_editor_container")
        ):
            self._field_height_timer.start(16)

    def _applyQueuedFieldEditorHeight(self):
        if (
            not hasattr(self, "field_tabs")
            or self.field_tabs.currentIndex() != 0
            or not hasattr(self, "field_editor_container")
        ):
            return
        height = bounded_default_editor_height(
            self._field_editor_natural_height, self.height()
        )
        self.field_editor_container.setMinimumHeight(height)
        self.field_editor_container.setMaximumHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "field_editor_container"):
            self.queueFieldEditorHeight(self._field_editor_natural_height)

    def _reload_field_editor(self):
        if self.field_editor is None or self.field_note is None:
            return
        self.field_editor.set_note(self.field_note)
        self._apply_field_tab(self.field_tabs.currentIndex())

    def setFieldText(self, field_name, text):
        if self.field_note is None or field_name not in self.field_note:
            return
        self.field_note[field_name] = text
        if field_name == self._title_field_name and self._inline_title_active:
            self.card_creation_integration.set_inline_title(self, text)

    def fieldText(self, field_name):
        if self.field_note is None:
            return ""
        value = self.field_note[field_name]
        if field_name == self._title_field_name and self._inline_title_active:
            return self.card_creation_integration.selected_title_text(self, value)
        return value

    def on_inline_title_changed(self, title):
        if self.field_note is not None:
            self.field_note[self._title_field_name] = title

    def setTags(self, tags):
        if self.field_note is not None:
            self.field_note.tags = list(tags)

    def tags(self):
        return list(self.field_note.tags) if self.field_note is not None else []

    def flushFieldEditor(self, callback):
        if self.field_editor is None:
            callback()
            return
        self.field_editor.call_after_note_saved(callback, keepFocus=False)

    def resolveCardCreationOptions(self, typed_title):
        if self.card_creation_integration is None:
            return {
                "title": typed_title.strip(),
                "save_title": False,
                "position_mode": "end",
                "position": None,
            }, None
        return self.card_creation_integration.resolve_card_creation_options(
            self, typed_title
        )

    def applyCreatedNotesOptions(self, notes, options):
        if self.card_creation_integration is None:
            return
        self.card_creation_integration.apply_created_notes(self, notes, options)

    def switchToMode(self, mode):
        """Toggle between add and edit layouts"""
        hide_on_add = [self.occl_tp_select, self.edit_btn, self.new_btn]
        hide_on_edit = [self.ao_btn, self.oa_btn]
        self.mode = mode
        if mode == "add":
            for i in hide_on_add:
                i.hide()
            for i in hide_on_edit:
                i.show()
            dl_txt = _("Deck")
            ttl = _("Image Occlusion Enhanced - Add Mode")
        else:
            for i in hide_on_add:
                i.show()
            for i in hide_on_edit:
                i.hide()
            dl_txt = _("Deck for <i>Add new cards</i>")
            ttl = _("Image Occlusion Enhanced - Editing Mode")
        self.deckChooser.deckLabel.setText(dl_txt)
        self.setWindowTitle(ttl)
        if hasattr(self, "field_tabs"):
            self._apply_field_tab(self.field_tabs.currentIndex())

    def showSvgEdit(self, state):
        self._svg_ready = bool(state)
        if state:
            self.svg_edit_anim.stop()
        else:
            self.svg_edit_anim.start()
        self._syncSvgVisibility()
        if (
            state
            and getattr(self, "_initial_title_focus_pending", False)
            and self._inline_title_active
            and self.field_tabs.currentIndex() == 0
        ):
            # Chromium takes focus as its page finishes loading. Reassert the
            # logical first input once, after that load, so keyboard users can
            # immediately type or press F2 to edit the selected title row.
            self._initial_title_focus_pending = False
            mw.progress.single_shot(
                0,
                lambda: self.saved_titles_list.setFocus(
                    Qt.FocusReason.OtherFocusReason
                ),
            )

    def _syncSvgVisibility(self):
        if self.svg_edit is None:
            return
        default_tab = (
            not hasattr(self, "field_tabs")
            or self.field_tabs.currentIndex() == 0
        )
        self.svg_edit.setVisible(default_tab and self._svg_ready)
        self.svg_edit_loader.setVisible(default_tab and not self._svg_ready)

    # Other actions

    def focusField(self, idx):
        """Focus an editable native field, changing tabs when necessary."""
        editable_fields = [
            field
            for field in self.flds
            if field["name"] not in self.ioflds_priv
        ]
        if idx >= len(editable_fields):
            return
        field_name = editable_fields[idx]["name"]
        if field_name == self._title_field_name and self._inline_title_active:
            self.field_tabs.setCurrentIndex(0)
            special = self.saved_titles_list.item(0)
            self.saved_titles_list.setCurrentItem(special)
            self.saved_titles_list.editItem(special)
            return
        target_tab = 0 if field_name in (
            self._title_field_name,
            self._front_field_name,
        ) else 1
        self.field_tabs.setCurrentIndex(target_tab)
        field_ord = self._field_ord_by_name[field_name]
        mw.progress.single_shot(
            0, lambda: self.field_editor.web.eval(f"focusField({field_ord});")
        )

    def focusTags(self):
        self.field_tabs.setCurrentIndex(1)
        if self.field_editor is not None:
            self.field_editor.web.eval(
                "setTagsCollapsed(false); "
                "setTimeout(function(){ "
                "const input = document.querySelector('.tag-input input'); "
                "if (input) input.focus(); }, 0);"
            )

    def resetMainFields(self):
        """Reset all fields aside from sticky ones"""
        if self.field_note is None:
            return
        for i in self.flds:
            fn = i["name"]
            if fn in self.ioflds_priv or fn in self.ioflds_prsv:
                continue
            self.field_note[fn] = ""
        if self._inline_title_active:
            self.card_creation_integration.set_inline_title(self, "")
        self._reload_field_editor()

    def resetAllFields(self):
        """Reset all fields"""
        self.resetMainFields()
        if self.field_note is None:
            return
        for i in self.ioflds_prsv:
            self.field_note[i] = ""
        self._reload_field_editor()

    def fitImageCanvas(self, delay: int = 5):
        self.svg_edit.eval(
            f"""
setTimeout(function(){{
    svgCanvas.zoomChanged('', 'canvas');
}}, {delay})
"""
        )
