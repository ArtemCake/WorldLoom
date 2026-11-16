// frontend/src/js/features/rules/draft/draft-book-preview-state.js

import { buildDraftBookPreview, draftPreviewVersionIds, readDraftPreviewInput } from './draft-book-preview-data.js';

function emptyState() {
    return { opened: false, loading: false, error: '', book: null };
}

function failureMessage(failure) {
    if (failure?.status === 401) return 'Сессия завершена. Войдите снова, чтобы загрузить внешние разделы.';

    if ([403, 404].includes(failure?.status)) {
        return 'Одна из закреплённых публикаций недоступна. Предпросмотр не собран; локальный черновик не изменён.';
    }

    return 'Не удалось собрать предпросмотр. Проверьте содержание и повторите открытие.';
}

async function loadPublications(ids, loadVersion, signal) {
    const result = new Array(ids.length);
    let cursor = 0;

    async function worker() {
        while (!signal.aborted && cursor < ids.length) {
            const index = cursor++;
            const versionId = ids[index];
            const publication = await loadVersion(versionId, { signal });

            if (signal.aborted) return;

            if (publication?.id !== versionId) {
                throw new TypeError('Сервер вернул другую публикацию раздела.');
            }

            result[index] = publication;
        }
    }

    const workers = Array.from({ length: Math.min(4, ids.length) }, () => worker());
    await Promise.all(workers);
    return result;
}

export function createDraftBookPreview({ loadVersion, onChange = () => {} }) {
    if (typeof loadVersion !== 'function' || typeof onChange !== 'function') {
        throw new TypeError('Требуются загрузчик публикаций и обработчик предпросмотра.');
    }

    let state = emptyState();
    let sequence = 0;
    let pending = null;
    let disposed = false;

    function getState() {
        return structuredClone(state);
    }

    function emit() {
        if (!disposed) onChange(getState());
    }

    async function open(editorState) {
        if (disposed) return;

        const token = ++sequence;
        pending?.abort();

        const request = new AbortController();
        pending = request;
        state = { opened: true, loading: true, error: '', book: null };
        emit();

        try {
            const input = readDraftPreviewInput(editorState);
            const ids = draftPreviewVersionIds(input);
            const publications = await loadPublications(ids, loadVersion, request.signal);

            if (disposed || token !== sequence) return;

            state.book = buildDraftBookPreview(input, publications);
        } catch (failure) {
            request.abort();

            if (disposed || token !== sequence) return;

            state.book = null;
            state.error = failureMessage(failure);
        } finally {
            if (!disposed && token === sequence) {
                state.loading = false;
                pending = null;
                emit();
            }
        }
    }

    function close() {
        if (disposed) return;

        sequence += 1;
        pending?.abort();
        pending = null;
        state = emptyState();
        emit();
    }

    function dispose() {
        if (disposed) return;

        sequence += 1;
        disposed = true;
        pending?.abort();
        pending = null;
        state = emptyState();
    }

    return Object.freeze({ getState, open, close, dispose });
}
