// frontend/src/js/features/rules/draft/draft-editor-state.js

import { ruleId } from '../rules-http.js';
import { applyChapterCommand, validateBookToc } from './draft-toc-data.js';
import { applySectionCommand } from './draft-section-data.js';

const FIELDS = ['title', 'summary', 'language', 'edition_key', 'introduction'];
const LIMITS = { title: 200, summary: 5000, language: 20, edition_key: 100, introduction: 300000 };

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);

    if (value !== null && typeof value === 'object') {
        return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
    }

    return value;
}

export function sameBookValue(left, right) {
    return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}

function validateFields(content) {
    for (const field of FIELDS) {
        const value = content[field];

        if (field === 'edition_key' && value === null) continue;

        ensure(typeof value === 'string', `Некорректное значение поля: ${field}.`);
        ensure([...value].length <= LIMITS[field], `Превышена длина поля: ${field}.`);
    }

    ensure(content.title.trim().length > 0, 'Укажите название книги.');
    ensure(content.language.trim().length > 0, 'Укажите код языка.');
    ensure([...content.language].length >= 2, 'Код языка должен содержать не меньше двух символов.');
    ensure(content.edition_key === null || content.edition_key.trim().length > 0, 'Укажите код редакции или очистите поле.');
}

function readDraft(draft, bookId) {
    ensure(draft && typeof draft === 'object', 'В ответе отсутствует черновик.');
    ruleId(draft.id);
    ensure(draft.book_id === bookId, 'Ответ относится к другой книге.');
    ensure(Number.isSafeInteger(draft.revision) && draft.revision > 0, 'Некорректная ревизия черновика.');

    const content = draft.content_json;

    ensure(content && content.schema_version === 1, 'Неподдерживаемое содержание книги.');
    ensure(Array.isArray(content.toc) && Array.isArray(content.sources), 'Отсутствует структура книги.');
    validateFields(content);
    validateBookToc(content.toc);

    return structuredClone(draft);
}

function editableValues(content) {
    return Object.fromEntries(FIELDS.map((field) => [field, content[field]]));
}

export function createBookDraftEditor({ draft, api, onChange = () => {} }) {
    const bookId = ruleId(draft.book_id);
    ensure(typeof api?.saveDraft === 'function' && typeof api?.getDraft === 'function', 'Не подключён API черновика.');
    ensure(typeof onChange === 'function', 'Не подключено обновление редактора.');

    let base = readDraft(draft, bookId);
    let values = editableValues(base.content_json);
    let toc = validateBookToc(base.content_json.toc);
    let busy = '';
    let blocked = false;
    let message = '';
    let error = '';
    let disposed = false;

    function dirty() {
        const fieldsChanged = !sameBookValue(values, editableValues(base.content_json));
        return fieldsChanged || !sameBookValue(toc, base.content_json.toc);
    }

    function getState() {
        const changed = dirty();

        return {
            values: structuredClone(values),
            toc: structuredClone(toc),
            revision: base.revision,
            busy,
            blocked,
            dirty: changed,
            needsGuard: changed || blocked || Boolean(busy),
            canSave: changed && !blocked && !busy,
            message,
            error
        };
    }

    function emit() {
        if (!disposed) onChange(getState());
    }

    function change(field, value) {
        if (disposed || busy || blocked) return;
        ensure(FIELDS.includes(field), 'Это поле не редактируется в данной форме.');
        ensure(typeof value === 'string', 'Значение поля должно быть строкой.');

        values[field] = field === 'edition_key' && value === '' ? null : value;
        message = '';
        error = '';
        emit();
    }

    function section(command) {
        if (disposed || busy || blocked) return false;

        const updated = applySectionCommand(toc, command);
        toc = updated;
        message = '';
        error = '';
        emit();
        return true;
    }

    function chapter(command) {
        if (disposed || busy || blocked) return;

        const updated = applyChapterCommand(toc, command);
        toc = updated;
        message = '';
        error = '';
        emit();
    }

    async function save() {
        if (disposed || busy || blocked || !dirty()) return null;

        const content = {
            ...structuredClone(base.content_json),
            ...structuredClone(values),
            toc: validateBookToc(toc)
        };
        validateFields(content);
        ensure(Number.isSafeInteger(base.revision + 1), 'Ревизия вышла за поддерживаемый диапазон.');

        const expected = base.revision;
        const draftId = base.id;
        busy = 'save';
        message = '';
        error = '';
        emit();

        let saved = null;
        let responseReceived = false;

        try {
            const payload = { expected_revision: expected, content: structuredClone(content) };
            const response = await api.saveDraft(bookId, payload);
            responseReceived = true;
            saved = readDraft(response, bookId);

            ensure(saved.id === draftId, 'Сервер вернул другой черновик.');
            ensure(saved.revision === expected + 1, 'Сервер вернул неожиданную ревизию.');
            ensure(sameBookValue(saved.content_json, content), 'Сохранённое содержание отличается от отправленного.');

            base = saved;
            values = editableValues(saved.content_json);
            toc = validateBookToc(saved.content_json.toc);
            message = `Черновик сохранён. Ревизия ${saved.revision}.`;
        } catch (failure) {
            saved = null;
            const status = Number(failure?.status) || 0;
            const uncertain = responseReceived || failure?.uncertain === true || !status || status >= 500;

            blocked = uncertain || [401, 403, 404, 409].includes(status);

            if (uncertain) {
                error = 'Результат сохранения не подтверждён. Запись могла выполниться. Локальный текст сохранён в форме.';
            } else if (status === 409) {
                error = 'Серверный черновик изменился. Локальные правки оставлены в форме; повторная запись заблокирована.';
            } else {
                error = failure?.message || 'Сервер отклонил сохранение.';
            }
        } finally {
            busy = '';
            emit();
        }

        return saved ? structuredClone(saved) : null;
    }

    async function reload() {
        if (disposed || busy) return null;

        busy = 'reload';
        error = '';
        message = '';
        emit();

        let loaded = null;

        try {
            const response = await api.getDraft(bookId);
            loaded = readDraft(response, bookId);
            ensure(loaded.id === base.id, 'Сервер вернул другой черновик.');

            base = loaded;
            values = editableValues(loaded.content_json);
            toc = validateBookToc(loaded.content_json.toc);
            blocked = false;
            message = 'Загружено состояние с сервера. Локальная форма заменена серверным черновиком.';
        } catch (failure) {
            loaded = null;
            error = failure?.message || 'Не удалось загрузить серверный черновик. Локальный текст оставлен в форме.';
        } finally {
            busy = '';
            emit();
        }

        return loaded ? structuredClone(loaded) : null;
    }

    function dispose() {
        disposed = true;
    }

    return Object.freeze({ getState, change, chapter, section, save, reload, dispose });
}
