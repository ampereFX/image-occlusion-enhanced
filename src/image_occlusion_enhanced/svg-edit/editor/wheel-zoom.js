(function(root, factory) {
	var api = factory();
	if(typeof module === 'object' && module.exports) {
		module.exports = api;
	} else {
		root.svgeditWheelZoom = api;
	}
}(this, function() {
	var PIXELS_PER_LINE = 16;
	var PIXELS_PER_ZOOM_STEP = 100;
	var ZOOM_PER_STEP = 1.1;
	var NATIVE_GESTURE_SENSITIVITY = 2;

	return {
		deltaInPixels: function(deltaY, deltaMode, pageHeight) {
			if(deltaMode === 1) {
				return deltaY * PIXELS_PER_LINE;
			}
			if(deltaMode === 2) {
				return deltaY * pageHeight;
			}
			return deltaY;
		},

		factorForDelta: function(pixelDelta) {
			return Math.pow(ZOOM_PER_STEP, -pixelDelta / PIXELS_PER_ZOOM_STEP);
		},

		factorForNativeGesture: function(magnificationDelta) {
			return Math.exp(magnificationDelta * NATIVE_GESTURE_SENSITIVITY);
		},

		scrollPositionForAnchor: function(anchorPosition, viewportPosition) {
			return anchorPosition - viewportPosition;
		}
	};
}));
