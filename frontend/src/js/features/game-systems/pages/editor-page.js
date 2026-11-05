// frontend/src/js/features/game-systems/pages/editor-page.js

import {requestGameSystem} from '../api/game-system-api.js';
import {createRulesBookState} from '../book/book-state.js';
import {mountRulesBook} from '../book/book-view.js';
import {collectEngineOverrides, readEngineOverrides} from '../editor/game-system-engine-origin.js';

const initializedRoots = new WeakSet();
const MODES = new Set(['create', 'edit', 'view']);

function ensure(condition, message) {
    if (!condition) throw new Error(message);
}

function cardValues(system) {
    ensure(system && typeof system.name === 'string', 'Не удалось прочитать карточку системы.');
    ensure(typeof system.slug === 'string', 'В карточке отсутствует код системы.');
    ensure(typeof system.rules_engine_version === 'string', 'В карточке отсутствует версия исполнителя.');
    ensure(typeof system.is_active === 'boolean', 'В карточке отсутствует состояние активности.');

    return {
        name: system.name,
        slug: system.slug,
        description: system.description ?? '',
        rules_engine_version: system.rules_engine_version,
        is_active: system.is_active
    };
}

function checkSnapshot(snapshot, id, kind) {
    ensure(snapshot?.system_id === id, 'Ответ относится к другой игровой системе.');
    ensure(snapshot.rules && typeof snapshot.rules === 'object', 'В ответе отсутствуют правила.');

    const number = kind === 'draft' ? snapshot.revision : snapshot.version_number;

    ensure(Number.isSafeInteger(number) && number >= 1, 'Некорректный номер ревизии или публикации.');
}

function validateCard(system) {
    const values = cardValues(system);

    values.name = values.name.trim();
    values.slug = values.slug.trim();
    values.description = values.description.trim() || null;
    values.rules_engine_version = values.rules_engine_version.trim();

    ensure(values.name && [...values.name].length <= 100, 'Укажите название системы длиной до 100 символов.');
    ensure(values.slug.length <= 100 && /^[a-z0-9]+([_-][a-z0-9]+)*$/.test(values.slug), 'Проверьте код системы.');
    ensure(values.rules_engine_version.length > 0, 'Не указана версия исполнителя.');

    return values;
}

function mustReload(error) {
    const status = Number(error?.status) || 0;

    return error?.uncertain === true || !status || status >= 500 || [401, 403, 409].includes(status);
}

function mountBookPage(root) {
    if (initializedRoots.has(root)) return;
    initializedRoots.add(root);

    let mode = root.dataset.pageMode;
    const host = root.querySelector('[data-book-host]');
    const message = root.querySelector('[data-book-message]');
    const login = root.querySelector('[data-book-login]');
    const reload = root.querySelector('[data-book-reload]');
    const save = root.querySelector('[data-book-save]');
    const edit = root.querySelector('[data-book-edit]');
    const sourceField = root.querySelector('[data-book-source-field]');
    const source = root.querySelector('[data-book-source]');

    if (!host || !message || !login || !reload || !save || !edit || !sourceField || !source) {
        initializedRoots.delete(root);
        return;
    }

    let systemId = root.dataset.systemId || null;
    let access = null;
    let state = null;
    let book = null;
    let busy = false;
    let sourceInitialized = false;

    const controller = new AbortController();
    const {signal} = controller;

    function sync() {
        const snapshot = state?.read();

        host.inert = busy;
        host.setAttribute('aria-busy', String(busy));
        reload.disabled = busy;
        source.disabled = busy;

        save.hidden = mode === 'view' || !(access?.can_create === true || access?.can_edit === true);
        save.disabled = busy || !snapshot || snapshot.blocked || snapshot.writePending !== null;

        if (snapshot?.mode === 'create' && access?.can_create !== true) save.disabled = true;
        if (snapshot?.mode === 'edit' && access?.can_edit !== true) save.disabled = true;

        save.textContent = snapshot?.mode === 'create' ? 'Создать систему и черновик' : 'Сохранить изменения';

        edit.hidden = mode !== 'view' || access?.can_edit !== true || !systemId;

        if (systemId) {
            edit.href = `/game-systems/catalog/${encodeURIComponent(systemId)}/edit`;
        }
    }

    function showError(error) {
        message.textContent = error instanceof Error ? error.message : 'Не удалось выполнить действие.';
        login.hidden = error?.status !== 401;
    }

    async function loadOrigin(snapshot, adminPath) {
        if (snapshot.engine_version_id == null) {
            ensure(snapshot.rules_overrides == null, 'Переопределения получены без опубликованной основы.');
            return null;
        }

        const origin = await requestGameSystem(`${adminPath}/editor/engine`);

        ensure(origin?.draft_revision === snapshot.revision, 'Черновик изменился во время загрузки основы.');
        readEngineOverrides(snapshot, origin.engine_version);

        return {
            engine_version: origin.engine_version,
            rules_overrides: snapshot.rules_overrides
        };
    }

    function replaceBook(document, revision) {
        const nextState = createRulesBookState({document, mode, revision});
        const chapter = state?.read().chapter ?? 'main';

        nextState.selectChapter(chapter);
        book?.destroy();
        state = nextState;
        book = mountRulesBook(host, {state});
    }

    async function load() {
        if (busy) return;

        if (book?.hasChanges() && !window.confirm('Загрузить данные заново? Несохранённые изменения будут потеряны.')) {
            return;
        }

        busy = true;
        login.hidden = true;
        sync();
        message.textContent = 'Загрузка…';

        try {
            access = await requestGameSystem('/game-systems/access');

            if (mode === 'create') {
                ensure(access.can_create === true, 'Создание игровых систем недоступно.');

                const system = {
                    name: '',
                    slug: `system-${crypto.randomUUID()}`,
                    description: '',
                    is_active: true,
                    rules_engine_version: '1.0'
                };

                replaceBook({system, rules: null, origin: null}, null);
                message.textContent = 'Новая книга. Запись на сервер выполняется кнопкой сохранения.';
                return;
            }

            if (mode === 'edit') {
                ensure(access.can_edit === true, 'Редактирование игровых систем недоступно.');
            }

            ensure(systemId, 'Не указана игровая система.');

            const id = encodeURIComponent(systemId);
            const adminPath = `/admin/game-systems/${id}`;
            const manager = access.can_edit === true;
            const systemPath = manager ? adminPath : `/game-systems/items/${id}`;
            const system = await requestGameSystem(systemPath);

            ensure(system?.id === systemId, 'Сервер вернул другую игровую систему.');

            if (!sourceInitialized) {
                source.value = manager ? 'draft' : 'published';
                sourceInitialized = true;
            }

            sourceField.hidden = mode !== 'view' || !manager;

            const draftMode = mode === 'edit' || (manager && source.value === 'draft');
            const path = draftMode
            ? `${adminPath}/rules/draft`
            : `${manager ? adminPath : `/game-systems/items/${id}`}/rules/latest`;

            const result = await requestGameSystem(path);
            const key = draftMode ? 'draft' : 'version';

            ensure(result && Object.hasOwn(result, key), 'Не удалось проверить ответ с правилами.');

            const snapshot = result[key];

            if (snapshot === null) {
                replaceBook({system: cardValues(system), rules: null, origin: null}, null);
                message.textContent = draftMode ? 'Сохранённого черновика нет.' : 'Правила ещё не опубликованы.';
                return;
            }

            checkSnapshot(snapshot, systemId, key);

            const origin = mode === 'edit' ? await loadOrigin(snapshot, adminPath) : null;
            const revision = draftMode ? snapshot.revision : null;

            replaceBook({system: cardValues(system), rules: snapshot.rules, origin}, revision);

            message.textContent = draftMode
            ? `Сохранённый черновик · ревизия ${snapshot.revision}.`
            : `Опубликованная версия №${snapshot.version_number}. Карточка системы показана в текущем состоянии.`;
        } catch (error) {
            showError(error);
        } finally {
            busy = false;
            sync();
        }
    }

    async function saveBook() {
        if (busy || !state || !book) return;

        login.hidden = true;

        if (book.hasPendingChanges()) {
            message.textContent = 'Сначала нажмите «Применить к книге» или отмените правки открытого элемента.';
            return;
        }

        let ticket = null;

        try {
            const snapshot = state.read();
            const creating = snapshot.mode === 'create';

            ensure(!snapshot.blocked, 'Сначала загрузите и сверьте сохранённые данные.');
            ensure(creating ? access?.can_create === true : access?.can_edit === true, 'Сохранение недоступно.');

            const system = validateCard(snapshot.document.system);
            const origin = snapshot.document.origin;
            const linked = origin !== null;

            let rulesPayload = {rules: snapshot.document.rules};

            if (linked) {
                const version = origin.engine_version;

                ensure(version?.rules_engine_version === system.rules_engine_version, 'Версия основы не совпадает с системой.');

                rulesPayload = {
                    engine_id: version.engine_id,
                    engine_version_id: version.id,
                    rules_overrides: collectEngineOverrides(
                        version.rules_json,
                        snapshot.document.rules,
                        origin.rules_overrides
                    )
                };
            }

            ticket = state.beginSave();

            const payload = {system, ...rulesPayload};

            if (!creating) payload.expected_revision = ticket.expectedRevision;

            const id = systemId ? encodeURIComponent(systemId) : null;
            const path = linked
            ? creating ? '/admin/game-systems/from-engine' : `/admin/game-systems/${id}/editor/engine`
            : creating ? '/admin/game-systems/editor/create' : `/admin/game-systems/${id}/editor`;

            busy = true;
            sync();
            message.textContent = 'Сохранение системы и черновика…';

            const result = await requestGameSystem(path, creating ? 'POST' : 'PUT', payload);
            const savedId = result?.system?.id;

            ensure(typeof savedId === 'string' && savedId.length > 0, 'Не удалось проверить ответ сохранения.');
            ensure(creating || savedId === systemId, 'Ответ сохранения относится к другой системе.');
            checkSnapshot(result.draft, savedId, 'draft');

            let savedOrigin = null;

            if (linked) {
                readEngineOverrides(result.draft, origin.engine_version);

                savedOrigin = {
                    engine_version: origin.engine_version,
                    rules_overrides: result.draft.rules_overrides
                };
            } else {
                ensure(result.draft.engine_version_id == null, 'Сервер вернул неожиданную связь с основой.');
                ensure(result.draft.rules_overrides == null, 'Сервер вернул неожиданные переопределения.');
            }

            const savedDocument = {
                system: cardValues(result.system),
                rules: result.draft.rules,
                origin: savedOrigin
            };

            state.acceptSave(ticket, savedDocument, result.draft.revision);
            ticket = null;
            systemId = savedId;
            root.dataset.systemId = savedId;

            book.refresh();

            if (creating) {
                mode = 'edit';
                const path = `/game-systems/catalog/${encodeURIComponent(savedId)}/edit`;

                history.replaceState(null, '', path);
                root.dataset.pageMode = 'edit';
            }

            message.textContent = 'Система и черновик сохранены. Публикация не выполнялась.';
        } catch (error) {
            if (ticket) {
                state.failWrite(ticket, {mustReload: mustReload(error)});
                book.refresh();
            }

            showError(error);
        } finally {
            busy = false;
            sync();
        }
    }

    save.addEventListener('click', () => void saveBook(), {signal});
    reload.addEventListener('click', () => void load(), {signal});
    source.addEventListener('change', () => void load(), {signal});

    root.addEventListener('input', sync, {signal});
    root.addEventListener('change', sync, {signal});

    document.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt !== root && !event.detail?.elt?.contains(root)) return;

        book?.destroy();
        controller.abort();
    }, {signal});

    void load();
}

export function initGameSystemEditor() {
    for (const root of document.querySelectorAll('[data-game-systems-page]')) {
        if (MODES.has(root.dataset.pageMode)) mountBookPage(root);
    }
}