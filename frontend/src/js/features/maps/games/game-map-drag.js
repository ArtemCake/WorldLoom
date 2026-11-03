// frontend/src/js/features/maps/games/game-map-drag.js

const DRAG_THRESHOLD = 6;

export function createMapDrag(canvas, callbacks) {
    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    let gesture = null;
    let suppressClick = false;
    let disposed = false;

    function releaseCapture(pointerId) {
        if (canvas.hasPointerCapture(pointerId)) {
            canvas.releasePointerCapture(pointerId);
        }
    }

    function cancel() {
        if (!gesture) return;

        const current = gesture;
        gesture = null;
        suppressClick = current.moved;
        releaseCapture(current.pointerId);
        callbacks.cancel(current.context, current.moved);
    }

    canvas.addEventListener('pointerdown', (event) => {
        if (disposed || gesture || !event.isPrimary || event.button !== 0) return;

        suppressClick = false;
        const context = callbacks.begin(event);

        if (!context) return;

        gesture = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            moved: false,
            context
        };

        try {
            canvas.setPointerCapture(event.pointerId);
        } catch {
            cancel();
        }
    }, options);

    canvas.addEventListener('pointermove', (event) => {
        if (!gesture || event.pointerId !== gesture.pointerId) return;

        const dx = event.clientX - gesture.startX;
        const dy = event.clientY - gesture.startY;

        if (!gesture.moved && dx * dx + dy * dy < DRAG_THRESHOLD * DRAG_THRESHOLD) return;

        gesture.moved = true;
        event.preventDefault();
        callbacks.update(event, gesture.context);
    }, options);

    canvas.addEventListener('pointerup', (event) => {
        if (!gesture || event.pointerId !== gesture.pointerId) return;

        const current = gesture;
        gesture = null;
        suppressClick = current.moved;
        releaseCapture(current.pointerId);

        if (current.moved) {
            callbacks.finish(event, current.context);
        } else {
            callbacks.cancel(current.context, false);
        }
    }, options);

    for (const type of ['pointercancel', 'lostpointercapture']) {
        canvas.addEventListener(type, (event) => {
            if (gesture?.pointerId === event.pointerId) cancel();
        }, options);
    }

    canvas.addEventListener('click', (event) => {
        if (!suppressClick || event.detail === 0) return;

        suppressClick = false;
        event.preventDefault();
        event.stopImmediatePropagation();
    }, { capture: true, signal: listeners.signal });

    canvas.ownerDocument.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape' || !gesture) return;

        event.preventDefault();
        cancel();
    }, options);

    canvas.ownerDocument.addEventListener('visibilitychange', () => {
        if (canvas.ownerDocument.hidden) cancel();
    }, options);

    window.addEventListener('blur', cancel, options);

    return {
        cancel,

        destroy() {
            if (disposed) return;

            disposed = true;
            cancel();
            listeners.abort();
        }
    };
}
