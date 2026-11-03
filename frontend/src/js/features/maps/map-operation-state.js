// frontend/src/js/features/maps/map-operation-state.js

const runningRoots = new WeakSet();
const CONTROL_SELECTOR = '[data-map-action], [data-map-delete], [data-map-destination], #map-destination-game, [data-map-controls], [data-preview-generate]';

export function acquireMapOperation(root = document) {
    if (runningRoots.has(root)) return null;

    runningRoots.add(root);

    const previousBusy = root.getAttribute?.('aria-busy');
    const controls = Array.from(root.querySelectorAll(CONTROL_SELECTOR));
    const previousStates = controls.map((control) => ({ control, disabled: control.disabled }));

    root.setAttribute?.('aria-busy', 'true');

    for (const { control } of previousStates) {
        control.disabled = true;
    }

    let released = false;

    return function releaseMapOperation() {
        if (released) return;

        released = true;

        for (const { control, disabled } of previousStates) {
            control.disabled = disabled;
        }

        if (previousBusy === null) {
            root.removeAttribute?.('aria-busy');
        } else if (previousBusy !== undefined) {
            root.setAttribute?.('aria-busy', previousBusy);
        }

        runningRoots.delete(root);
    };
}
