// frontend/src/js/features/rules/draft/draft-editor-state.js

import { ruleId } from '../rules-http.js';
import { applyChapterCommand, readBookSources, validateBookToc } from './draft-toc-data.js';
import { applySectionCommand } from './draft-section-data.js';
import { readBookPublication } from './draft-publication-data.js';
import { applySectionReplacement } from './draft-section-replacement-data.js';
import { applyBookTextCommand, applyBookTextSourceCommand } from './draft-text-data.js';
import { assertWorkingPublication, readWorkingDraft, readWorkingEditor } from './draft-working-data.js';
import { applyDraftSourceCommand } from './draft-source-data.js';

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
    readBookSources(content.sources);
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

export function createBookDraftEditor({ draft, api, onChange = () => {}, workingState = null }) {
    const bookId = ruleId(draft.book_id);
    const working = draft.content_json?.schema_version === 2;
    const saveMethod = working ? 'saveWorkingDraft' : 'saveDraft';
    const reloadMethod = working ? 'getWorkingEditor' : 'getDraft';
    const publishMethod = working ? 'publishWorkingDraft' : 'publish';

    ensure(typeof api?.[saveMethod] === 'function', 'Не подключено сохранение черновика.');
    ensure(typeof api?.[reloadMethod] === 'function', 'Не подключено чтение состояния черновика.');
    ensure(typeof onChange === 'function', 'Не подключено обновление редактора.');

    function readCurrentDraft(value) {
        const checked = working ? readWorkingDraft(value, bookId) : readDraft(value, bookId);
        validateFields(checked.content_json);
        return checked;
    }

    const initial = working ? readWorkingEditor(workingState, bookId) : null;
    let base = readCurrentDraft(draft);

    if (initial) {
        ensure(sameBookValue(initial.draft, base), 'Начальное состояние не соответствует переданному черновику.');
    }

    let values = editableValues(base.content_json);
    let toc = validateBookToc(base.content_json.toc);
    let sources = readBookSources(base.content_json.sources);
    let busy = '';
    let blocked = false;
    let message = '';
    let error = '';
    let disposed = false;
    let lastPublication = null;
    let publishedDraftRevision = null;
    let publishedContent = initial?.has_unpublished_changes === false
        ? structuredClone(base.content_json)
        : null;

    if (initial?.latest_publication) {
        const publication = initial.latest_publication;

        lastPublication = {
            id: publication.id,
            version_number: publication.version_number,
            source_draft_revision: publication.source_draft_revision
        };
    }

    function dirty() {
        const fieldsChanged = !sameBookValue(values, editableValues(base.content_json));
        const tocChanged = !sameBookValue(toc, base.content_json.toc);
        const sourcesChanged = !sameBookValue(sources, base.content_json.sources);

        return fieldsChanged || tocChanged || sourcesChanged;
    }

    function canPublish() {
        if (disposed || busy || blocked || dirty()) return false;
        if (typeof api[publishMethod] !== 'function') return false;
        if (base.revision === publishedDraftRevision) return false;
        if (working && publishedContent && sameBookValue(base.content_json, publishedContent)) return false;

        return toc.some((node) => node.kind === 'article' || (working && node.kind === 'text'));
    }

    function getState() {
        const changed = dirty();

        return {
            values: structuredClone(values),
            toc: structuredClone(toc),
            revision: base.revision,
            sources: structuredClone(sources),
            busy,
            blocked,
            dirty: changed,
            needsGuard: changed || blocked || Boolean(busy),
            canSave: changed && !blocked && !busy,
            canPublish: canPublish(),
            lastPublication: structuredClone(lastPublication),
            schemaVersion: base.content_json.schema_version,
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

        const updated = command?.type === 'replace'
            ? applySectionReplacement(toc, command)
            : applySectionCommand(toc, command);

        toc = updated;
        message = '';
        error = '';
        emit();
        return true;
    }

    function text(command) {
        if (disposed || busy || blocked) return false;
        ensure(working, 'Собственные тексты доступны только в рабочем формате книги.');

        const updated = applyBookTextCommand(toc, command);
        toc = updated;
        message = '';
        error = '';
        emit();
        return true;
    }

    function textSource(key, command) {
        if (disposed || busy || blocked) return false;
        ensure(working, 'Источники собственных текстов доступны только в рабочем формате книги.');

        toc = applyBookTextSourceCommand(toc, { ...command, key });
        message = '';
        error = '';
        emit();
        return true;
    }

    function bookSource(command) {
        if (disposed || busy || blocked) return false;

        sources = applyDraftSourceCommand(sources, command);
        message = '';
        error = '';
        emit();
        return true;
    }

    function changeText(key, field, value) {
        if (disposed || busy || blocked) return false;
        ensure(working, 'Собственные тексты доступны только в рабочем формате книги.');

        const fields = ['title', 'summary', 'body', 'language', 'edition_key', 'audience', 'rule_kind'];
        ensure(fields.includes(field), 'Это поле собственного текста не редактируется.');
        ensure(typeof value === 'string', 'Значение поля должно быть строкой.');

        const node = toc.find((item) => item.key === key && item.kind === 'text');
        ensure(node, 'Не найден собственный текст для изменения.');

        if (field === 'audience') {
            ensure(['players', 'gm', 'both'].includes(value), 'Неизвестная аудитория текста.');
        }

        if (field === 'rule_kind') {
            ensure(['base', 'optional', 'supplement', 'homebrew'].includes(value), 'Неизвестный вид правила.');
        }

        node.content[field] = field === 'edition_key' && value === '' ? null : value;
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
            sources: readBookSources(sources),
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
            const response = await api[saveMethod](bookId, payload);
            if (disposed) return null;
            responseReceived = true;
            saved = readCurrentDraft(response);

            ensure(saved.id === draftId, 'Сервер вернул другой черновик.');
            ensure(saved.revision === expected + 1, 'Сервер вернул неожиданную ревизию.');
            ensure(sameBookValue(saved.content_json, content), 'Сохранённое содержание отличается от отправленного.');

            base = saved;
            values = editableValues(saved.content_json);
            toc = validateBookToc(saved.content_json.toc);
            sources = readBookSources(saved.content_json.sources);
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

    async function publish() {
        if (!canPublish()) return null;

        validateFields(base.content_json);
        validateBookToc(base.content_json.toc);
        ensure(Number.isSafeInteger(base.revision + 1), 'Ревизия вышла за поддерживаемый диапазон.');

        const expected = base.revision;
        const draftId = base.id;
        const content = structuredClone(base.content_json);
        let confirmed = null;
        let refreshed = null;
        let responseReceived = false;

        busy = 'publish';
        message = '';
        error = '';
        emit();

        try {
            const response = await api[publishMethod](bookId, { expected_revision: expected });
            if (disposed) return null;

            responseReceived = true;
            const checked = readBookPublication(response, bookId, expected);
            if (working) {
                assertWorkingPublication(content, checked.publication.content_json);
            } else {
                ensure(sameBookValue(checked.publication.content_json, content), 'Опубликованное содержание отличается от черновика.');
            }

            confirmed = checked;
            lastPublication = {
                id: checked.publication.id,
                version_number: checked.publication.version_number,
                source_draft_revision: checked.publication.source_draft_revision
            };
            publishedDraftRevision = checked.draft_revision;
            message = `Создана публикация ${checked.publication.version_number}.`;

            const loaded = await api[reloadMethod](bookId);
            if (disposed) return null;

            const state = working ? readWorkingEditor(loaded, bookId) : null;
            const next = readCurrentDraft(state ? state.draft : loaded);

            ensure(next.id === draftId, 'Сервер вернул другой черновик.');
            ensure(next.revision === checked.draft_revision, 'После публикации серверный черновик изменился.');
            ensure(sameBookValue(next.content_json, content), 'После публикации содержание серверного черновика изменилось.');

            if (state) {
                ensure(state.latest_publication?.id === checked.publication.id, 'Последняя публикация книги изменилась.');
                ensure(state.has_unpublished_changes === false, 'Сервер не подтвердил совпадение черновика с публикацией.');
                ensure(sameBookValue(state.latest_publication, checked.publication), 'Данные подтверждённой публикации отличаются.');
                publishedContent = structuredClone(next.content_json);
            }

            base = next;
            values = editableValues(next.content_json);
            toc = validateBookToc(next.content_json.toc);
            sources = readBookSources(next.content_json.sources);
            refreshed = next;
            message += ` Черновик обновлён до ревизии ${next.revision}.`;
        } catch (failure) {
            if (disposed) return null;

            if (confirmed) {
                blocked = true;
                error = 'Публикация создана, но актуальный черновик не подтверждён. Загрузите серверный черновик перед записью.';
            } else {
                const status = Number(failure?.status) || 0;
                const uncertain = responseReceived || failure?.uncertain === true || !status || status >= 500;
                blocked = uncertain || [401, 403, 404, 409].includes(status);

                if (uncertain) {
                    error = 'Результат публикации не подтверждён. Версия могла быть создана. Повторная запись заблокирована.';
                } else if (status === 409) {
                    error = 'Сервер отклонил публикацию. Проверьте актуальный черновик и доступность материалов.';
                } else {
                    error = failure?.message || 'Сервер отклонил публикацию.';
                }
            }
        } finally {
            busy = '';
            emit();
        }

        if (!confirmed) return null;

        return {
            publication: structuredClone(confirmed.publication),
            draft: refreshed ? structuredClone(refreshed) : null
        };
    }

    async function reload() {
        if (disposed || busy) return null;

        busy = 'reload';
        error = '';
        message = '';
        emit();

        let loaded = null;

        try {
            const response = await api[reloadMethod](bookId);
            if (disposed) return null;

            const state = working ? readWorkingEditor(response, bookId) : null;
            loaded = readCurrentDraft(state ? state.draft : response);
            ensure(loaded.id === base.id, 'Сервер вернул другой черновик.');

            if (state) {
                publishedContent = state.has_unpublished_changes === false
                    ? structuredClone(loaded.content_json)
                    : null;

                const publication = state.latest_publication;
                lastPublication = publication ? {
                    id: publication.id,
                    version_number: publication.version_number,
                    source_draft_revision: publication.source_draft_revision
                } : null;

                publishedDraftRevision = null;
            }

            base = loaded;
            values = editableValues(loaded.content_json);
            toc = validateBookToc(loaded.content_json.toc);
            sources = readBookSources(loaded.content_json.sources);
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

    return Object.freeze({
        getState, change, chapter, section, text, changeText, textSource, bookSource,
        save, publish, reload, dispose
    });
}
