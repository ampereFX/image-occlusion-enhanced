/* 
Image Occlusion Enhanced Add-on for Anki

Copyright (C) 2016-2022  Aristotelis P. <https://glutanimate.com/>
Copyright (C) 2012-2015  Tiago Barroso <tmbb@campus.ul.pt>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version, with the additions
listed at the end of the license file that accompanied this program.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

NOTE: This program is subject to certain additional terms pursuant to
Section 7 of the GNU Affero General Public License.  You should have
received a copy of these additional terms immediately following the
terms and conditions of the GNU Affero General Public License that
accompanied this program.

If not, please request a copy through one of the means of contact
listed here: <https://glutanimate.com/contact/>.

Any modifications to this file must keep this entire header intact.
*/

const NoteEditor = require("anki/NoteEditor");

class ImageOcclusionEditorAdapter {
  markIdField(index, attempt = 0) {
    const idField = NoteEditor.instances[0].fields[index];
    if (!idField) {
      return;
    }
    // Anki exposed this as a Promise in older releases and as the resolved
    // element in newer editor builds.  Normalize both forms so embedding the
    // native editor does not produce an unhandled TypeError.
    const elementOrPromise = idField.element;
    if (!elementOrPromise) {
      if (attempt < 50) {
        setTimeout(() => this.markIdField(index, attempt + 1), 20);
      }
      return;
    }
    Promise.resolve(elementOrPromise).then((element) => {
      if (element) {
        element.classList.add("ionote-field-id");
      }
    });
  }
}

globalThis.imageOcclusion = new ImageOcclusionEditorAdapter();
