// frontend/src/js/features/rules/draft/draft-book-preview-session.js

import { sameBookValue } from './draft-editor-state.js';
import { createDraftBookPreview } from './draft-book-preview-state.js';

function editorContent(state) {
    return structuredClone({
        schemaVersion: state.schemaVersion,
        values: state.values,
        sources: state.sources,
        toc: state.toc
    });
}

export function createDraftPreviewSession({ loadVersion, onChange = () => {} }) {
    if (typeof onChange !== 'function') {
        throw new TypeError('Требуется обработчик состояния предпросмотра.');
    }

    let current = null;
    let captured = null;
    let busy = false;
    let generation = 0;
    let disposed = false;

    const preview = createDraftBookPreview({ loadVersion, onChange: emit });

    function getState() {
        const state = preview.getState();

        return {
            ...state,
            available: current !== null,
            busy,
            generation,
            stale: state.opened && captured !== null && !sameBookValue(current, captured)
        };
    }

    function emit() {
        if (!disposed) onChange(getState());
    }

    function update(editorState) {
        if (disposed) return;

        current = editorContent(editorState);
        busy = Boolean(editorState.busy);
        emit();
    }

    async function open() {
        if (disposed || !current || busy) return;

        captured = structuredClone(current);
        generation += 1;
        await preview.open(captured);
    }

    function close() {
        if (disposed) return;

        captured = null;
        preview.close();
    }

    function reset() {
        if (disposed) return;

        current = null;
        captured = null;
        busy = false;
        preview.close();
    }

    function dispose() {
        if (disposed) return;

        disposed = true;
        preview.dispose();
        current = null;
        captured = null;
        busy = false;
    }

    return Object.freeze({ getState, update, open, close, reset, dispose });
}
