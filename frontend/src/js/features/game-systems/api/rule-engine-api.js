// frontend/src/js/features/game-systems/api/rule-engine-api.js

import {readProfileResources} from '../editor/shared/resource-contract.js';

function ensure(condition, message) {
    if (!condition) throw new Error(message);
}

function identifier(value) {
    ensure(
        typeof value === 'string' && value.length > 0,
        'Не указан идентификатор движка.'
    );

    return encodeURIComponent(value);
}

function revision(value) {
    ensure(
        Number.isSafeInteger(value) && value >= 1,
        'Некорректная ревизия черновика.'
    );

    return value;
}

function engineCard(value) {
    ensure(
        typeof value?.id === 'string' &&
        value.id.length > 0 &&
        typeof value.name === 'string' &&
        typeof value.slug === 'string' &&
        ['private', 'public'].includes(value.visibility),
        'Сервер вернул некорректную карточку движка.'
    );

    return value;
}

function engineDraft(value, engineId) {
    ensure(
        value?.engine_id === engineId &&
        typeof value.id === 'string' &&
        value.id.length > 0 &&
        typeof value.rules_engine_version === 'string' &&
        [3, 4].includes(value.rules_json?.schema_version),
        'Сервер вернул неподдерживаемый черновик движка.'
    );
    readProfileResources(value.rules_json);
    revision(value.revision);
    return value;
}

function publication(value, engineId, expectedRevision) {
    ensure(
        value?.engine_id === engineId &&
        typeof value.id === 'string' &&
        value.id.length > 0 &&
        Number.isSafeInteger(value.version_number) &&
        value.version_number >= 1 &&
        value.source_draft_revision === expectedRevision &&
        [3, 4].includes(value.rules_json?.schema_version),
        'Ответ публикации не удалось проверить.'
    );
    readProfileResources(value.rules_json);
    return value;
}

export function blocksEngineMutation(error, editing = true) {
    const status = Number(error?.status) || 0;

    return (
        status === 0 ||
        status >= 500 ||
        status === 401 ||
        status === 403 ||
        (editing && status === 409)
    );
}

export function createRuleEngineApi(request) {
    async function pages(path, query = '') {
        const result = [];
        const ids = new Set();
        let offset = 0;

        while (true) {
            const page = await request(
                `${path}?${query}limit=100&offset=${offset}`
            );

            ensure(
                Array.isArray(page?.items),
                'Сервер вернул некорректный список.'
            );

            for (const item of page.items) {
                ensure(
                    typeof item?.id === 'string' &&
                    item.id.length > 0 &&
                    !ids.has(item.id),
                    'Каталог изменился или содержит повторные записи. ' +
                    'Загрузите его заново.'
                );

                ids.add(item.id);
                result.push(item);
            }

            if (page.next_offset === null) return result;

            ensure(
                Number.isSafeInteger(page.next_offset) &&
                page.next_offset > offset &&
                page.items.length > 0,
                'Некорректное продолжение списка.'
            );

            offset = page.next_offset;
        }
    }

    function path(engineId) {
        return `/admin/rule-engines/${identifier(engineId)}`;
    }

    return Object.freeze({
        async listOwned() {
            const items = await pages(
                '/admin/rule-engines',
                'owned_only=true&'
            );

            return items.map(engineCard);
        },

        async read(engineId) {
            const draft = engineDraft(
                await request(`${path(engineId)}/draft`),
                engineId
            );

            const versions = await pages(
                `${path(engineId)}/versions`
            );

            for (const item of versions) {
                ensure(
                    item.engine_id === engineId &&
                    Number.isSafeInteger(item.version_number) &&
                    item.version_number >= 1 &&
                    Number.isSafeInteger(item.source_draft_revision) &&
                    item.source_draft_revision >= 1,
                    'Некорректные сведения о публикациях.'
                );
            }

            return {draft, versions};
        },

        async create(data) {
            const result = await request(
                '/admin/rule-engines',
                'POST',
                data
            );

            const engine = engineCard(result?.engine);
            const draft = engineDraft(result?.draft, engine.id);

            return {engine, draft};
        },

        async save(engineId, rules, expectedRevision) {
            return engineDraft(
                await request(
                    `${path(engineId)}/draft`,
                    'PUT',
                    {
                        rules,
                        expected_revision: revision(expectedRevision)
                    }
                ),
                engineId
            );
        },

        async setActive(engineId, isActive, expectedIsActive) {
            ensure(
                typeof isActive === 'boolean' &&
                typeof expectedIsActive === 'boolean',
                'Не указано корректное состояние активности.'
            );

            const saved = engineCard(
                await request(
                    `${path(engineId)}/activity`,
                    'PATCH',
                    {
                        is_active: isActive,
                        expected_is_active: expectedIsActive
                    }
                )
            );

            ensure(
                saved.id === engineId &&
                saved.is_active === isActive,
                'Ответ изменения активности не удалось проверить.'
            );

            return saved;
        },

        async remove(engineId, expectedRevision) {
            const saved = await request(
                path(engineId),
                'DELETE',
                {
                    expected_revision: revision(expectedRevision)
                }
            );

            ensure(
                saved?.deleted === true &&
                saved.engine_id === engineId,
                'Ответ удаления не удалось проверить.'
            );

            return saved;
        },

        async publish(engineId, expectedRevision) {
            revision(expectedRevision);

            return publication(
                await request(
                    `${path(engineId)}/publish`,
                    'POST',
                    {expected_revision: expectedRevision}
                ),
                engineId,
                expectedRevision
            );
        }
    });
}