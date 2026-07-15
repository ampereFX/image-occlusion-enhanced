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
Sets up configuration, including constants
"""

# TODO: move constants to consts.py

import copy
import os
import sys

from aqt import mw

global IO_FLDS, IO_FLDS_IDS
global IO_MODEL_NAME, IO_CARD_NAME, IO_HOME, IO_HOTKEY

IO_MODEL_NAME = "Image Occlusion Enhanced"
IO_CARD_NAME = "IO Card"

IO_FLDS = {
    "id": "ID (hidden)",
    "tl": "Title",
    "hd": "Front",
    "im": "Image",
    "ft": "Footer",
    "rk": "Remarks",
    "sc": "Sources",
    "e1": "Extra 1",
    "e2": "Extra 2",
    "qm": "Question Mask",
    "am": "Answer Mask",
    "om": "Original Mask",
}

IO_FLDS_IDS = [
    "id",
    "tl",
    "hd",
    "im",
    "qm",
    "ft",
    "rk",
    "sc",
    "e1",
    "e2",
    "am",
    "om",
]

# TODO: Use IDs instead of names to make these compatible with self.ioflds

# fields that aren't user-editable
IO_FIDS_PRIV = ["id", "im", "qm", "am", "om"]

# fields that are synced between an IO Editor session and Anki's Editor
IO_FIDS_PRSV = ["sc"]

# variables for local preference handling
sys_encoding = sys.getfilesystemencoding()
IO_HOME = os.path.expanduser("~")
IO_HOTKEY = "Ctrl+Shift+O"
IO_TEMPLATE_VERSION = 3

# default configurations
# TODO: update version number before release
default_conf_local = {"version": 1.26, "dir": IO_HOME, "hotkey": IO_HOTKEY}
default_conf_syncd = {
    "version": 1.26,
    "template_version": IO_TEMPLATE_VERSION,
    "ofill": "FFEBA2",
    "qfill": "FF7E7E",
    "scol": "2D2D2D",
    "swidth": 3,
    "font": "Arial",
    "fsize": 24,
    "skip": [IO_FLDS["e1"], IO_FLDS["e2"]],
    "flds": IO_FLDS,
}

from . import template


def getSyncedConfig():
    """Load and migrate the collection-wide configuration"""
    config = mw.col.conf.get("imgocc")
    config_changed = False

    if config is None:
        # Eine eigene Kopie verhindert Änderungen an den Standardwerten
        config = copy.deepcopy(default_conf_syncd)
        config_changed = True

        # upgrade from IO 2.0:
        if "image_occlusion_conf" in mw.col.conf:
            old_conf = mw.col.conf["image_occlusion_conf"]
            config["ofill"] = old_conf["initFill[color]"]
            config["qfill"] = old_conf["mask_fill_color"]
            # insert other upgrade actions here

    elif config.get("version", 0) < default_conf_syncd["version"]:
        print("Updating config DB from earlier IO release")
        for key in list(default_conf_syncd.keys()):
            if key not in config:
                config[key] = copy.deepcopy(default_conf_syncd[key])
        config["version"] = default_conf_syncd["version"]
        config_changed = True

    # Feldzuordnungen auch reparieren, wenn eine frühere Migration bereits
    # die Versionsnummer gespeichert hat
    configured_fields = config.setdefault("flds", {})
    if configured_fields.get("hd") == "Header":
        configured_fields["hd"] = IO_FLDS["hd"]
        config_changed = True
    for field_id, field_name in IO_FLDS.items():
        if field_id not in configured_fields:
            configured_fields[field_id] = field_name
            config_changed = True

    if config_changed:
        # Moderne Anki-Versionen erfordern das Zurückschreiben des ganzen Objekts
        mw.col.conf["imgocc"] = config
        mw.col.setMod()

    return config


def getLocalConfig():
    # Local preferences
    if "imgocc" not in mw.pm.profile:
        mw.pm.profile["imgocc"] = default_conf_local
    elif mw.pm.profile["imgocc"].get("version", 0) < default_conf_syncd["version"]:
        for key in list(default_conf_local.keys()):
            if key not in mw.col.conf["imgocc"]:
                mw.pm.profile["imgocc"][key] = default_conf_local[key]
        mw.pm.profile["imgocc"]["version"] = default_conf_local["version"]

    return mw.pm.profile["imgocc"]


def getOrCreateModel():
    model = mw.col.models.by_name(IO_MODEL_NAME)
    if not model:
        # create model and set up default field name config
        model = template.add_io_model(mw.col)
        config = mw.col.conf["imgocc"]
        config["flds"] = copy.deepcopy(default_conf_syncd["flds"])
        mw.col.conf["imgocc"] = config
        return model
    model = ensure_custom_model_fields(model)
    config = mw.col.conf["imgocc"]
    if config.get("template_version", 0) < template.IO_TEMPLATE_VERSION:
        # Notion2Anki and users may deliberately manage a custom IO card
        # template. Only migrate layouts that still use this add-on's
        # characteristic io-wrapper structure.
        question_format = model["tmpls"][0].get("qfmt", "")
        if 'id="io-wrapper"' in question_format:
            model = template.reset_template(mw.col)
        config["template_version"] = template.IO_TEMPLATE_VERSION
        mw.col.conf["imgocc"] = config
        mw.col.setMod()
        return model
    model_version = mw.col.conf["imgocc"]["version"]
    if model_version < default_conf_syncd["version"]:
        return template.update_template(mw.col, model_version)
    return model


def ensure_custom_model_fields(model):
    """Migrate the existing model without replacing notes or templates"""
    models = mw.col.models
    field_names = models.fieldNames(model)

    if IO_FLDS["hd"] not in field_names and "Header" in field_names:
        header_field = next(field for field in model["flds"] if field["name"] == "Header")
        models.renameField(model, header_field, IO_FLDS["hd"])
        field_names = models.fieldNames(model)

    if IO_FLDS["tl"] not in field_names:
        title_field = models.newField(IO_FLDS["tl"])
        models.addField(model, title_field)

    config = mw.col.conf["imgocc"]
    configured_fields = config.setdefault("flds", {})
    configured_fields["hd"] = IO_FLDS["hd"]
    configured_fields["tl"] = IO_FLDS["tl"]
    mw.col.conf["imgocc"] = config
    mw.col.setMod()
    return model


def getModelConfig():
    model = getOrCreateModel()
    mflds = model["flds"]
    ioflds = mw.col.conf["imgocc"]["flds"]
    ioflds_priv = []
    for i in IO_FIDS_PRIV:
        ioflds_priv.append(ioflds[i])
    # preserve fields if they are marked as sticky in the IO note type:
    ioflds_prsv = []
    for fld in mflds:
        fname = fld["name"]
        if fld["sticky"] and fname not in ioflds_priv:
            ioflds_prsv.append(fname)

    return model, mflds, ioflds, ioflds_priv, ioflds_prsv


def loadConfig(self):
    """load and/or create add-on preferences"""
    # FIXME: return config dictionary instead of this hacky
    # instantiation of instance variables
    self.sconf_dflt = default_conf_syncd
    self.lconf_dflt = default_conf_local
    self.sconf = getSyncedConfig()
    self.lconf = getLocalConfig()

    (
        self.model,
        self.mflds,
        self.ioflds,
        self.ioflds_priv,
        self.ioflds_prsv,
    ) = getModelConfig()
