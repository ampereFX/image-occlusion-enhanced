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
Handles the IO note type and card template
"""

from .config import *

# DEFAULT CARD TEMPLATES

io_stage_script = """\
<script>
(function () {
  var wrapper = document.getElementById('io-wrapper');
  var stage = document.getElementById('io-stage');
  var original = document.querySelector('#io-original img');
  var mask = document.querySelector('#io-overlay img');

  if (!wrapper || !stage || !original) return;

  function reservedHeightBelowWrapper() {
    var height = 0;
    var sibling = wrapper.nextElementSibling;
    while (sibling && !sibling.classList.contains('io-extra-entry')) {
      var style = window.getComputedStyle(sibling);
      if (style.display !== 'none') {
        height += sibling.getBoundingClientRect().height;
        height += parseFloat(style.marginTop) + parseFloat(style.marginBottom);
      }
      sibling = sibling.nextElementSibling;
    }
    return height;
  }

  function fitStage() {
    var naturalWidth = original.naturalWidth;
    var naturalHeight = original.naturalHeight;
    if (!naturalWidth || !naturalHeight) return;

    var viewportHeight = document.documentElement.clientHeight || window.innerHeight;
    var wrapperStyle = window.getComputedStyle(wrapper);
    var horizontalPadding = parseFloat(wrapperStyle.paddingLeft) + parseFloat(wrapperStyle.paddingRight);
    var verticalPadding = parseFloat(wrapperStyle.paddingTop) + parseFloat(wrapperStyle.paddingBottom);
    var availableWidth = wrapper.clientWidth - horizontalPadding;
    var availableHeight = Math.max(
      1,
      viewportHeight
        - wrapper.getBoundingClientRect().top
        - verticalPadding
        - reservedHeightBelowWrapper()
    );
    var scale = Math.min(1, availableWidth / naturalWidth, availableHeight / naturalHeight);

    stage.style.width = (naturalWidth * scale) + 'px';
    stage.style.height = (naturalHeight * scale) + 'px';
    stage.classList.add('io-stage-ready');
  }

  function revealOriginal() {
    document.getElementById('io-original').style.visibility = 'visible';
  }

  if (mask === null || mask.complete) revealOriginal();
  else mask.addEventListener('load', revealOriginal, {once: true});

  if (original.complete) fitStage();
  else original.addEventListener('load', fitStage, {once: true});

  window.addEventListener('resize', fitStage);
  if (window.ResizeObserver) {
    new ResizeObserver(fitStage).observe(wrapper);
  }
  requestAnimationFrame(function () { requestAnimationFrame(fitStage); });
})();
</script>\
"""

iocard_front = """\
<!-- image-occlusion-enhanced-template-revision: 4 -->
{{#%(src_img)s}}
<div class="notion-card card-image-occlusion">
  <div class="title-header"><div class="content-frame"><div class="title-label">{{%(title)s}}</div></div></div>
  <div class="front-wrapper"><div class="content-frame"><div class="question-content">{{%(header)s}}</div></div></div>
  <div id="io-wrapper">
    <div id="io-stage">
      <div id="io-original">{{%(src_img)s}}</div>
      <div id="io-overlay">{{%(que)s}}</div>
    </div>
  </div>
  {{#%(footer)s}}<div id="io-footer">{{%(footer)s}}</div>{{/%(footer)s}}
</div>
%(stage_script)s
{{/%(src_img)s}}
""" % {
    "que": IO_FLDS["qm"],
    "ans": IO_FLDS["am"],
    "svg": IO_FLDS["om"],
    "src_img": IO_FLDS["im"],
    "title": IO_FLDS["tl"],
    "header": IO_FLDS["hd"],
    "footer": IO_FLDS["ft"],
    "remarks": IO_FLDS["rk"],
    "sources": IO_FLDS["sc"],
    "extraone": IO_FLDS["e1"],
    "extratwo": IO_FLDS["e2"],
    "stage_script": io_stage_script,
}

iocard_back = """\
<!-- image-occlusion-enhanced-template-revision: 4 -->
{{#%(src_img)s}}
<div class="notion-card card-image-occlusion">
  <div class="title-header"><div class="content-frame"><div class="title-label">{{%(title)s}}</div></div></div>
  <div class="front-wrapper"><div class="content-frame"><div class="question-content">{{%(header)s}}</div></div></div>
  <div id="io-wrapper">
    <div id="io-stage">
      <div id="io-original">{{%(src_img)s}}</div>
      <div id="io-overlay">{{%(ans)s}}</div>
    </div>
  </div>
  {{#%(footer)s}}<div id="io-footer">{{%(footer)s}}</div>{{/%(footer)s}}
  <button id="io-revl-btn" onclick="toggle();">Toggle Masks</button>
    {{#%(remarks)s}}
      <div class="io-extra-entry">
        <div class="io-field-descr">%(remarks)s</div>{{%(remarks)s}}
      </div>
    {{/%(remarks)s}}
    {{#%(sources)s}}
      <div class="io-extra-entry">
        <div class="io-field-descr">%(sources)s</div>{{%(sources)s}}
      </div>
    {{/%(sources)s}}
    {{#%(extraone)s}}
      <div class="io-extra-entry">
        <div class="io-field-descr">%(extraone)s</div>{{%(extraone)s}}
      </div>
    {{/%(extraone)s}}
    {{#%(extratwo)s}}
      <div class="io-extra-entry">
        <div class="io-field-descr">%(extratwo)s</div>{{%(extratwo)s}}
      </div>
    {{/%(extratwo)s}}
</div>

<script>
// Toggle answer mask on clicking the image
var toggle = function() {
  var amask = document.getElementById('io-overlay');
  if (amask.style.display === 'block' || amask.style.display === '')
    amask.style.display = 'none';
  else
    amask.style.display = 'block'
}

</script>
%(stage_script)s
{{/%(src_img)s}}
""" % {
    "que": IO_FLDS["qm"],
    "ans": IO_FLDS["am"],
    "svg": IO_FLDS["om"],
    "src_img": IO_FLDS["im"],
    "title": IO_FLDS["tl"],
    "header": IO_FLDS["hd"],
    "footer": IO_FLDS["ft"],
    "remarks": IO_FLDS["rk"],
    "sources": IO_FLDS["sc"],
    "extraone": IO_FLDS["e1"],
    "extratwo": IO_FLDS["e2"],
    "stage_script": io_stage_script,
}

iocard_css = """\
/* image-occlusion-enhanced-template-revision: 4 */
/* GENERAL CARD STYLE */
:root {
  --bg-color: #000000;
  --surface-color: #000000;
  --text-color: #f5f5f2;
  --title-color: #f5ce94;
  --divider-color: #2d2d2a;
  --secondary-bg: #171716;
  --question-text-color: #ffffff;
  --question-text-shadow: 0 1.5px 2px rgba(248, 106, 255, .567);
  --content-width: 38ch;
  --content-padding: 20px;
}

.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 18px;
  text-align: left;
  color: var(--text-color);
  background-color: var(--bg-color);
  line-height: 1.65;
  padding: 0;
  margin: 0;
}

.card-image-occlusion {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  min-height: 0;
  background: var(--surface-color);
}

.title-header {
  box-sizing: border-box;
  width: 100%;
  padding: 18px 0 16px;
  border-bottom: 1px solid var(--divider-color);
  background: var(--secondary-bg);
}

.content-frame {
  box-sizing: border-box;
  width: min(100%, calc(var(--content-width) + (var(--content-padding) * 2)));
  margin: 0 auto;
  padding-left: var(--content-padding);
  padding-right: var(--content-padding);
}

.title-label {
  position: static !important;
  display: block;
  width: 100%;
  margin: 0;
  color: var(--title-color);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .14em;
  text-align: center;
  text-transform: uppercase;
}

.front-wrapper {
  box-sizing: border-box;
  width: 100%;
  padding: 26px 0 22px;
  color: var(--question-text-color);
  text-shadow: var(--question-text-shadow);
}

.question-content {
  width: 100%;
  display: block;
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -.02em;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

/* OCCLUSION CSS START - don't edit this */
#io-overlay {
  position: absolute;
  inset: 0;
  z-index: 3;
}

#io-original {
  position: absolute;
  inset: 0;
  z-index: 2;
  visibility: hidden;
}

#io-wrapper {
  box-sizing: border-box;
  position: relative;
  width: 100%;
  padding: 0 var(--content-padding) var(--content-padding);
}

#io-stage {
  position: relative;
  max-width: 100%;
  margin: 0 auto;
  opacity: 0;
}

#io-stage.io-stage-ready {
  opacity: 1;
}

#io-stage.io-stage-ready #io-overlay,
#io-stage.io-stage-ready #io-original,
#io-stage.io-stage-ready #io-overlay > *,
#io-stage.io-stage-ready #io-original > *,
#io-stage.io-stage-ready #io-overlay img,
#io-stage.io-stage-ready #io-original img {
  box-sizing: border-box !important;
  width: 100% !important;
  min-width: 0 !important;
  max-width: none !important;
  height: 100% !important;
  min-height: 0 !important;
  max-height: none !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  transform: none !important;
}

#io-stage.io-stage-ready #io-overlay img,
#io-stage.io-stage-ready #io-original img {
  display: block !important;
  object-fit: fill !important;
}
/* OCCLUSION CSS END */

/* OTHER STYLES */
#io-header{
  font-size: 1.1em;
  margin-bottom: 0.2em;
}

#io-footer,
.io-extra-entry {
  width: min(calc(100% - 40px), 760px);
  margin: 20px auto 0;
  color: #b7b7b0;
}

#io-footer {
  font-style: italic;
}

.io-extra-entry {
  font-size: 0.9em;
  text-align: left;
}

.io-field-descr{
  margin-bottom: 0.2em;
  font-weight: bold;
  font-size: 1em;
}

#io-revl-btn {
  display: block;
  margin: 18px auto var(--content-padding);
  padding: 7px 12px;
  border: 1px solid var(--divider-color);
  border-radius: 6px;
  color: var(--text-color);
  background: var(--secondary-bg);
  font-size: 0.75em;
}

/* ADJUSTMENTS FOR MOBILE DEVICES */

.mobile .card, .mobile #content {
  font-size: 120%;
  margin: 0;
}

.mobile #io-revl-btn {
  font-size: 0.8em;
}
"""

# INCREMENTAL UPDATES

html_overlay_onload = """\
<script>
// Prevent original image from loading before mask
aFade = 50, qFade = 0;
var mask = document.querySelector('#io-overlay>img');
function loaded() {
    var original = document.querySelector('#io-original');
    original.style.visibility = "visible";
}
if (mask.complete) {
    loaded();
} else {
    mask.addEventListener('load', loaded);
}
</script>\
"""

css_original_hide = """\
/* Anki 2.1 additions */
#io-original {
   visibility: hidden;
}\
"""

# List structure:
# (<version addition was introduced in>,
# (<qfmt_addition>, <afmt_addition>, <css_addition>))
# versions need to be ordered by semantic versioning
additions_by_version = [
    (1.30, (html_overlay_onload, html_overlay_onload, css_original_hide)),
]


def add_io_model(col):
    models = col.models
    io_model = models.new(IO_MODEL_NAME)
    # Add fields:
    for i in IO_FLDS_IDS:
        fld = models.newField(IO_FLDS[i])
        if i == "note_id":
            fld["size"] = 0
        models.addField(io_model, fld)
    # Add template
    template = models.newTemplate(IO_CARD_NAME)
    template["qfmt"] = iocard_front
    template["afmt"] = iocard_back
    io_model["css"] = iocard_css
    io_model["sortf"] = 1  # set sortfield to header
    models.addTemplate(io_model, template)
    models.add(io_model)
    return io_model


def reset_template(col):
    print("Resetting IO Enhanced card template to defaults")
    io_model = col.models.byName(IO_MODEL_NAME)
    template = io_model["tmpls"][0]
    template["qfmt"] = iocard_front
    template["afmt"] = iocard_back
    io_model["css"] = iocard_css
    col.models.save(io_model)
    return io_model


def update_template(col, old_version):
    print("Updating IO Enhanced card template")

    additions = [[], [], []]

    for version, components in additions_by_version:
        if old_version >= version:
            continue
        for lst, addition in zip(additions, components):
            lst.append(addition)

    io_model = col.models.byName(IO_MODEL_NAME)

    if not io_model:
        return add_io_model(col)

    template = io_model["tmpls"][0]
    template["qfmt"] += "\n".join(additions[0])
    template["afmt"] += "\n".join(additions[1])
    io_model["css"] += "\n".join(additions[2])
    col.models.save()
    return io_model
