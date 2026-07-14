const assert = require("assert");
const wheelZoom = require("../src/image_occlusion_enhanced/svg-edit/editor/wheel-zoom.js");

assert.strictEqual(wheelZoom.deltaInPixels(5, 0, 800), 5);
assert.strictEqual(wheelZoom.deltaInPixels(5, 1, 800), 80);
assert.strictEqual(wheelZoom.deltaInPixels(2, 2, 800), 1600);

const zoomIn = wheelZoom.factorForDelta(-100);
const zoomOut = wheelZoom.factorForDelta(100);
assert.ok(Math.abs(zoomIn - 1.1) < 1e-12);
assert.ok(Math.abs(zoomIn * zoomOut - 1) < 1e-12);
assert.ok(wheelZoom.factorForDelta(-1) > 1);
assert.ok(wheelZoom.factorForDelta(1) < 1);

const nativeZoomIn = wheelZoom.factorForNativeGesture(0.1);
const nativeZoomOut = wheelZoom.factorForNativeGesture(-0.1);
assert.ok(Math.abs(nativeZoomIn * nativeZoomOut - 1) < 1e-12);
assert.ok(nativeZoomIn > 1.2 && nativeZoomIn < 1.23);
assert.ok(wheelZoom.factorForNativeGesture(0) === 1);

assert.strictEqual(wheelZoom.scrollPositionForAnchor(640, 240), 400);
assert.strictEqual(wheelZoom.scrollPositionForAnchor(125, 125), 0);
