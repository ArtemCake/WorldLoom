// frontend/src/js/features/game-systems/editor/split-editor-session.js

// Раздельная редакторская сессия: единый документ книги правил
// отображается на два независимых серверных черновика (текст и механику)
// с собственными ревизиями, и на один комплект при публикации.
//
// Публикация комплекта на сервере сама создаёт версии текста и механики
// из переданных ревизий черновиков, поэтому отдельная публикация блоков
// здесь не вызывается.
//
// Модуль не трогает DOM и не проверяет права: работает через переданные
// API-фабрики и документные преобразователи split-document.js.

import { joinBlocks, splitRules } from '../api/split-document.js';

const BLOCKS = Object.freeze(['text', 'mechanic']);

function isRecord(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;

    const prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
}

function checkRevision(value) {
    if (value === null || value === undefined) return null;

    if (!Number.isSafeInteger(value) || value < 1) {
        throw new TypeError('Некорректная ревизия черновика.');
    }

    return value;
}

function draftState(response, block) {
    const draft = response?.draft;

    if (draft === null || draft === undefined) {
        return { revision: null, isPublished: false, content: null };
    }

    if (!isRecord(draft)) {
        throw new TypeError(`Сервер вернул неожиданный черновик ${block}.`);
    }

    return {
        revision: checkRevision(draft.revision),
        isPublished: draft.is_published === true,
        content: draft[block] ?? null
    };
}

/**
 * Создать раздельную сессию редактирования.
 *
 * @param {object} options
 * @param {string} options.systemId
 * @param {{getDraft, createDraft, updateDraft}} options.textApi
 * @param {{getDraft, createDraft, updateDraft}} options.mechanicApi
 * @param {{publish}} [options.versionApi]
 */
export function createSplitEditorSession({ systemId, textApi, mechanicApi, versionApi }) {
    if (typeof systemId !== 'string' || !systemId) {
        throw new TypeError('Не указан идентификатор игровой системы.');
    }

    for (const [name, api] of [['textApi', textApi], ['mechanicApi', mechanicApi]]) {
        if (!isRecord(api) || typeof api.getDraft !== 'function'
            || typeof api.createDraft !== 'function' || typeof api.updateDraft !== 'function') {
            throw new TypeError(`Требуется API-фабрика черновика: ${name}.`);
        }
    }

    if (!isRecord(versionApi) || typeof versionApi.publish !== 'function') {
        throw new TypeError('Требуется API-фабрика комплекта с публикацией.');
    }

    const apis = { text: textApi, mechanic: mechanicApi };

    // ── Загрузка ──────────────────────────────────────────────────────
    // Читает оба черновика и собирает единый документ книги.
    // Механика задаёт числовую основу; текст дополняет главами.
    async function load() {
        const [textResponse, mechanicResponse] = await Promise.all([
            apis.text.getDraft(systemId),
            apis.mechanic.getDraft(systemId)
        ]);
        const text = draftState(textResponse, 'text');
        const mechanic = draftState(mechanicResponse, 'mechanic');

        return Object.freeze({
            document: joinBlocks({ text: text.content, mechanic: mechanic.content }),
            revisions: Object.freeze({ text: text.revision, mechanic: mechanic.revision }),
            published: Object.freeze({ text: text.isPublished, mechanic: mechanic.isPublished }),
            hasDraft: text.content !== null || mechanic.content !== null
        });
    }

    // ── Отправка одного блока ─────────────────────────────────────────
    // Ревизия есть — PATCH с expected_revision; ревизии нет — POST create.
    async function saveBlock(block, content, revision) {
        if (revision === null) {
            const created = await apis[block].createDraft(systemId, { [block]: content });

            return checkRevision(created?.revision);
        }

        const updated = await apis[block].updateDraft(systemId, {
            expected_revision: revision,
            [block]: content
        });

        return checkRevision(updated?.revision);
    }

    // ── Сохранение документа ──────────────────────────────────────────
    // Разделяет документ и отправляет каждый черновик по своей ревизии.
    // Возвращает актуальные ревизии обоих черновиков после записи.
    //
    // Блоки отправляются последовательно, чтобы конфликт ревизии одного
    // блока не маскировался параллельной операцией другого.
    async function save(document, revisions) {
        const split = splitRules(document);

        if (split === null) {
            throw new TypeError('Нечего сохранять: документ правил пуст.');
        }

        const given = isRecord(revisions) ? revisions : {};
        const current = Object.freeze({
            text: checkRevision(given.text),
            mechanic: checkRevision(given.mechanic)
        });
        const next = { ...current };

        for (const block of BLOCKS) {
            next[block] = await saveBlock(block, split[block], current[block]);
        }

        return Object.freeze(next);
    }

    // ── Публикация комплекта ──────────────────────────────────────────
    // Собирает версию системы из переданных ревизий обоих черновиков.
    // Текст необязателен: если черновика текста нет, комплект берёт
    // последнюю опубликованную версию текста.
    async function publish(revisions) {
        const given = isRecord(revisions) ? revisions : {};
        const mechanicRevision = checkRevision(given.mechanic);
        const textRevision = checkRevision(given.text);

        if (mechanicRevision === null) {
            throw new TypeError('Для публикации комплекта нужна ревизия механики.');
        }

        return versionApi.publish(systemId, {
            expected_mechanic_revision: mechanicRevision,
            expected_text_revision: textRevision
        });
    }

    return Object.freeze({ load, save, publish });
}
