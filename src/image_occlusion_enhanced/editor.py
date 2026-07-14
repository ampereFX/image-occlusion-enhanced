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

import os

from anki.hooks import addHook, remHook
from aqt import deckchooser, mw, tagedit, webview
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
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QSize,
    Qt,
    QVBoxLayout,
    QWidget,
    sip,
    pyqtSignal,
)
from aqt.utils import restoreGeom, saveGeom, askUser

from .config import *
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
        loadConfig(self)
        self.setupUi()
        restoreGeom(self, "imgoccedit")
        try:
            from aqt.gui_hooks import profile_will_close

            profile_will_close.append(self.onProfileUnload)
        except (ImportError, ModuleNotFoundError):
            addHook("unloadProfile", self.onProfileUnload)

    def closeEvent(self, event):
        self._on_close()

    def _on_close(self):
        if mw.pm.profile is not None:
            self.deckChooser.cleanup()
            saveGeom(self, "imgoccedit")
        self.visible = False
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
            self.close()

    def reject(self):
        if not self.svg_edit:
            return super().reject()
        self.svg_edit.evalWithCallback(
            "svgCanvas.undoMgr.getUndoStackSize() == 0", self._on_reject_callback
        )

    def _on_reject_callback(self, undo_stack_empty: bool):
        if (undo_stack_empty and not self._input_modified()) or askUser(
            "Are you sure you want to close the window? This will discard any unsaved"
            " changes.",
            title="Exit Image Occlusion?",
        ):
            self._on_close()

    def _input_modified(self) -> bool:
        tags_modified = self.tags_edit.isModified()
        fields_modified = any(
            plain_text_edit.document().isModified()  # type: ignore
            for plain_text_edit in self.findChildren(QPlainTextEdit)
        )
        return tags_modified or fields_modified

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

        self.tags_hbox = QHBoxLayout()
        self.tags_edit = tagedit.TagEdit(self)
        self.tags_label = QLabel(_("Tags"))
        self.tags_label.setFixedWidth(70)
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
        self.bottom_label = QLabel()
        button_box = QDialogButtonBox(Qt.Orientation.Horizontal, self)
        button_box.setCenterButtons(False)

        image_btn = QPushButton(_("Change &Image"))
        image_btn.clicked.connect(self.changeImage)
        image_btn.setIcon(QIcon(os.path.join(ICONS_PATH, "add.png")))
        image_btn.setIconSize(QSize(16, 16))
        image_btn.setAutoDefault(False)

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
            _("Hide &All, Guess One"), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.oa_btn = button_box.addButton(
            _("Hide &One, Guess One"), QDialogButtonBox.ButtonRole.ActionRole
        )
        help_button = button_box.addButton(
            _("&?"), QDialogButtonBox.ButtonRole.ActionRole
        )
        close_button = button_box.addButton(
            _("&Close"), QDialogButtonBox.ButtonRole.RejectRole
        )

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
            help_button,
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
        help_button.clicked.connect(self.onHelp)
        close_button.clicked.connect(self.close)

        # Set basic layout up

        # Button row
        bottom_hbox = QHBoxLayout()
        bottom_hbox.setContentsMargins(10, 0, 10, 10)
        bottom_hbox.addWidget(image_btn)
        bottom_hbox.insertStretch(1, stretch=1)
        bottom_hbox.addWidget(self.bottom_label)
        bottom_hbox.addWidget(self.occl_tp_select)
        bottom_hbox.addWidget(button_box)

        editor_layout = QVBoxLayout()
        editor_layout.setContentsMargins(0, 0, 0, 0)

        self.primary_fields_layout = QVBoxLayout()
        self.primary_fields_layout.setContentsMargins(10, 0, 10, 0)
        editor_layout.addLayout(self.primary_fields_layout)

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

        self.position_layout = QVBoxLayout()
        self.position_layout.setContentsMargins(10, 0, 10, 0)
        editor_layout.addLayout(self.position_layout)

        self.advanced_fields_button = QPushButton(_("More Fields"))
        self.advanced_fields_button.setCheckable(True)
        self.advanced_fields_button.setChecked(False)
        self.advanced_fields_button.setAutoDefault(False)
        editor_layout.addWidget(self.advanced_fields_button)

        self.vbox2 = QVBoxLayout()
        self.advanced_fields_widget = QWidget()
        self.advanced_fields_widget.setLayout(self.vbox2)
        self.advanced_fields_widget.hide()
        self.advanced_fields_button.toggled.connect(
            self.advanced_fields_widget.setVisible
        )
        editor_layout.addWidget(self.advanced_fields_widget)

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
        self.imgoccadd.onAddNotesButton("ao", close)

    def addOA(self, close=False):
        self.imgoccadd.onAddNotesButton("oa", close)

    def new(self, close=False):
        choice = self.occl_tp_select.currentData()
        self.imgoccadd.onAddNotesButton(choice, close)

    def editNote(self):
        choice = self.occl_tp_select.currentData()
        self.imgoccadd.onEditNotesButton(choice)

    def onHelp(self):
        if self.mode == "add":
            ioHelp("add", parent=self)
        else:
            ioHelp("edit", parent=self)

    # Window state

    def resetFields(self):
        """Reset all widgets. Needed for changes to the note type"""
        for layout in [
            self.primary_fields_layout,
            self.position_layout,
            self.vbox2,
        ]:
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
        self.tags_hbox.setParent(None)

    def setupFields(self, flds):
        """Setup dialog text edits based on note type fields"""
        self.tedit = {}
        self.tlabel = {}
        self.flds = flds

        editable_fields = [
            field for field in flds if field["name"] not in self.ioflds_priv
        ]
        primary_names = [self.ioflds["tl"], self.ioflds["hd"]]

        def add_field(field, layout, minimum_height=40, maximum_height=None):
            hbox = QHBoxLayout()
            tedit = QPlainTextEdit()
            label = QLabel(field["name"])
            hbox.addWidget(label)
            hbox.addWidget(tedit)
            tedit.setTabChangesFocus(True)
            tedit.setMinimumHeight(minimum_height)
            if maximum_height is not None:
                tedit.setMaximumHeight(maximum_height)
            label.setFixedWidth(70)
            self.tedit[field["name"]] = tedit
            self.tlabel[field["name"]] = label
            layout.addLayout(hbox)

        title_field = next(
            field for field in editable_fields if field["name"] == primary_names[0]
        )
        front_field = next(
            field for field in editable_fields if field["name"] == primary_names[1]
        )
        add_field(title_field, self.primary_fields_layout, 34, 34)

        try:
            import custom_shortcuts

            custom_shortcuts.setup_card_creation_controls(
                self,
                self.primary_fields_layout,
                initial_host=self.imgoccadd.ed.parentWindow,
                position_layout=self.position_layout,
            )
            self.card_creation_integration = custom_shortcuts
        except (ImportError, AttributeError):
            self.card_creation_integration = None

        add_field(front_field, self.primary_fields_layout, 54, 90)

        for field in editable_fields:
            if field["name"] in primary_names:
                continue
            add_field(field, self.vbox2)

        self.tags_hbox.addWidget(self.tags_label)
        self.tags_hbox.addWidget(self.tags_edit)
        self.vbox2.addLayout(self.tags_hbox)
        self.vbox2.addWidget(self.deck_container)
        self.setTabOrder(self.tags_edit, self.deckChooser.deck)

    def setFieldText(self, field_name, text):
        if field_name in self.tedit:
            self.tedit[field_name].setPlainText(text)

    def fieldText(self, field_name):
        return self.tedit[field_name].toPlainText()

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
        for i in list(self.tedit.values()):
            i.show()
        for i in list(self.tlabel.values()):
            i.show()
        if mode == "add":
            for i in hide_on_add:
                i.hide()
            for i in hide_on_edit:
                i.show()
            dl_txt = _("Deck")
            ttl = _("Image Occlusion Enhanced - Add Mode")
            bl_txt = _("Add Cards:")
        else:
            for i in hide_on_add:
                i.show()
            for i in hide_on_edit:
                i.hide()
            for i in self.sconf["skip"]:
                if i in list(self.tedit.keys()):
                    self.tedit[i].hide()
                    self.tlabel[i].hide()
            dl_txt = _("Deck for <i>Add new cards</i>")
            ttl = _("Image Occlusion Enhanced - Editing Mode")
            bl_txt = _("Type:")
        self.deckChooser.deckLabel.setText(dl_txt)
        self.setWindowTitle(ttl)
        self.bottom_label.setText(bl_txt)

    def showSvgEdit(self, state):
        if not state:
            self.svg_edit.hide()
            self.svg_edit_anim.start()
            self.svg_edit_loader.show()
        else:
            self.svg_edit_anim.stop()
            self.svg_edit_loader.hide()
            self.svg_edit.show()

    # Other actions

    def focusField(self, idx):
        """Focus field in vbox2 layout by index number"""
        editable_fields = [
            field
            for field in self.flds
            if field["name"] not in self.ioflds_priv
        ]
        if idx >= len(editable_fields):
            return
        field_name = editable_fields[idx]["name"]
        if field_name not in [self.ioflds["tl"], self.ioflds["hd"]]:
            self.advanced_fields_button.setChecked(True)
        self.tedit[field_name].setFocus()

    def focusTags(self):
        self.advanced_fields_button.setChecked(True)
        self.tags_edit.setFocus()

    def resetMainFields(self):
        """Reset all fields aside from sticky ones"""
        for i in self.flds:
            fn = i["name"]
            if fn in self.ioflds_priv or fn in self.ioflds_prsv:
                continue
            self.tedit[fn].setPlainText("")

    def resetAllFields(self):
        """Reset all fields"""
        self.resetMainFields()
        for i in self.ioflds_prsv:
            self.tedit[i].setPlainText("")

    def fitImageCanvas(self, delay: int = 5):
        self.svg_edit.eval(
            f"""
setTimeout(function(){{
    svgCanvas.zoomChanged('', 'canvas');
}}, {delay})
"""
        )
