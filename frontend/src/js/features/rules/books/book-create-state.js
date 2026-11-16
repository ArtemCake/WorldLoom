// frontend/src/js/features/rules/books/book-create-state.js

import { NEW_BOOK_DEFAULTS, createdBookId, newBookPayload } from './book-create-data.js';

export function createBookCreation({ api, openBook, onChange = () => {}, makeSlug = () => `book-${globalThis.crypto.randomUUID()}` }) {
    if (typeof api?.create !== 'function' || typeof openBook !== 'function') {
        throw new TypeError('Не заданы операции создания и открытия книги.');
    }

    let disposed = false;
    let slug = '';
    let baseline = { ...NEW_BOOK_DEFAULTS };
    const state = {
        opened: false,
        busy: false,
        blocked: false,
        completed: false,
        bookId: null,
        error: '',
        values: { ...NEW_BOOK_DEFAULTS }
    };

    function dirty() {
        return Object.keys(NEW_BOOK_DEFAULTS).some((key) => state.values[key] !== baseline[key]);
    }

    function getState() {
        const changed = dirty();
        const needsGuard = state.opened && (state.busy || state.blocked || (!state.bookId && changed));
        return structuredClone({ ...state, dirty: changed, needsGuard });
    }

    function emit() {
        if (!disposed) onChange(getState());
    }

    function reset(systemId = '') {
        baseline = { ...NEW_BOOK_DEFAULTS, system_id: systemId };
        state.values = { ...baseline };
        state.bookId = null;
        state.completed = false;
        state.error = '';
        slug = '';
    }

    function open(systemId = '') {
        if (disposed || state.busy || state.opened) return false;

        if (state.completed || (!state.blocked && !state.bookId && !dirty())) reset(systemId);

        state.opened = true;
        emit();
        return true;
    }

    function close() {
        if (disposed || state.busy) return false;

        state.opened = false;
        if (!state.blocked && !state.bookId) reset();
        emit();
        return true;
    }

    function change(name, value) {
        if (disposed || !state.opened || state.busy || state.blocked || state.bookId) return false;
        if (!Object.hasOwn(NEW_BOOK_DEFAULTS, name) || typeof value !== 'string') {
            throw new TypeError('Некорректное поле новой книги.');
        }

        state.values[name] = value;
        state.error = '';
        emit();
        return true;
    }

    async function submit() {
        if (disposed || !state.opened || state.busy || state.blocked) return null;

        let payload = null;

        if (!state.bookId) {
            try {
                if (!slug) slug = makeSlug();
                payload = newBookPayload(state.values, slug);
            } catch (failure) {
                state.error = failure?.message || 'Проверьте поля новой книги.';
                emit();
                return null;
            }
        }

        state.busy = true;
        state.error = '';
        emit();

        try {
            if (!state.bookId) {
                try {
                    const result = await api.create(payload);
                    if (disposed) return null;
                    state.bookId = createdBookId(result, payload.system_id);
                } catch (failure) {
                    if (disposed) return null;

                    const status = failure?.status;
                    const rejected = Number.isInteger(status) && status >= 400 && status < 500;
                    state.blocked = Boolean(failure?.uncertain) || !rejected;
                    state.error = state.blocked
                        ? 'Результат создания не подтверждён. Проверьте список своих книг перед новой попыткой.'
                        : failure?.message || 'Не удалось создать книгу. Проверьте данные и права доступа.';

                    return null;
                }
            }

            try {
                await openBook(state.bookId);
                if (disposed) return null;

                state.completed = true;
                state.opened = false;
                return state.bookId;
            } catch (failure) {
                if (disposed) return null;

                const detail = failure?.message || 'Не удалось загрузить редактор.';
                state.error = `Книга создана, но её черновик не открыт. ${detail}`;
                return null;
            }
        } finally {
            state.busy = false;
            emit();
        }
    }

    function dispose() {
        disposed = true;
    }

    return Object.freeze({ getState, open, close, change, submit, dispose });
}
