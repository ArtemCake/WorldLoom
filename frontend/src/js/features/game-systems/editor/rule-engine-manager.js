// frontend/src/js/features/game-systems/editor/rule-engine-manager.js

import {createEngineRulesEditor} from './engine-rules-editor.js';
import {mountEngineEditorLayout} from './engine-editor-layout.js';
import {blocksEngineMutation, createRuleEngineApi} from '../api/rule-engine-api.js';
import {element as node} from './shared/editor-dom.js';

export function mountRuleEngineManager(host, { request, isAllowed }) {
    if (!host) {
        return null;
    }

    const api = createRuleEngineApi(request);

    // Только постоянная разметка.
    // Данные сервера вставляются через textContent и value.
    host.innerHTML = `
        <details class="system-editor__details">
            <summary>Мои движки правил</summary>

            <p class="profile-note">
                Здесь находятся ваши движки, включая неопубликованные.
                Создание движка не создаёт игровую систему.
            </p>

            <button type="button" class="btn btn-outline-primary"
                    data-engines-refresh>
                Загрузить мои движки
            </button>

            <button type="button" class="btn btn-primary"
                    data-engine-new>
                Новый движок
            </button>

            <p data-engines-message role="status"
               aria-live="polite"></p>

            <div class="admin-sections" data-engines-list></div>
            <div data-engine-editor></div>
        </details>
    `;

    const status = host.querySelector('[data-engines-message]');
    const list = host.querySelector('[data-engines-list]');
    const area = host.querySelector('[data-engine-editor]');
    const refresh = host.querySelector('[data-engines-refresh]');
    const newButton = host.querySelector('[data-engine-new]');

    let engines = [];
    let engine = null;
    let draft = null;
    let versions = [];
    let editor = null;
    let form = null;
    let layout = null;
    let busy = false;
    let editorBusy = false;
    let loaded = false;
    let blocked = false;
    let metadataDirty = false;

    function working() {
        return busy || editorBusy;
    }

    function unsaved() {
        return metadataDirty || Boolean(editor?.hasUnsaved());
    }

    function canDiscard() {
        return !unsaved() || window.confirm(
            'Перейти к другому черновику? ' +
            'Несохранённые изменения движка будут потеряны.'
        );
    }

    function alreadyPublished() {
        return Boolean(draft) && versions.some(
            (item) =>
            item.source_draft_revision + 1 === draft.revision
        );
    }

    function sync() {
        const disabled = working() || !isAllowed();

        refresh.disabled = disabled;
        newButton.disabled = disabled || blocked;

        list.querySelectorAll('button').forEach((button) => {
            button.disabled = disabled;
        });

        if (!form) {
            return;
        }

        form.querySelector('[data-engine-metadata]').disabled =
        disabled;

        form.querySelector('[data-engine-save]').disabled =
        disabled || !loaded || blocked;

        form.querySelector('[data-engine-publish]').disabled =
        disabled ||
        !loaded ||
        blocked ||
        !engine ||
        engine.is_active !== true ||
        unsaved() ||
        Boolean(alreadyPublished());

        const activity = form.querySelector('[data-engine-activity]');
        const remove = form.querySelector('[data-engine-delete]');

        activity.hidden = !engine;
        activity.textContent = engine?.is_active === false
        ? 'Активировать игровую систему'
        : 'Деактивировать игровую систему';

        activity.disabled =
        disabled || !loaded || blocked || !engine;

        remove.hidden = !engine || versions.length > 0;
        remove.disabled =
        disabled || !loaded || blocked || !engine;

        editor?.setParentBusy(disabled || !loaded);
        layout?.sync({
            disabled: disabled || !loaded,
            busy: working(),
            dirty: unsaved(),
            blocked,
            existing: Boolean(engine)
        });
    }

    async function run(action, mutation = false, editing = true) {
        if (working() || !isAllowed()) {
            return;
        }

        if (mutation && blocked) {
            return;
        }

        busy = true;
        let actionStarted = false;

        try {
            sync();
            actionStarted = true;
            await action();
        } catch (error) {
            if (
            mutation &&
            actionStarted &&
            blocksEngineMutation(error, editing)
            ) {
                blocked = true;
            }

            console.error(error);

            status.textContent =
            (error.message || 'Не удалось выполнить действие.') +
            (blocked
            ? ' Повторная запись заблокирована. ' +
            'Обновите страницу и загрузите список движков ' +
            'для сверки. До перезагрузки введённые данные ' +
            'остаются в форме.'
            : '');
        } finally {
            busy = false;

            try {
                sync();
            } catch (error) {
                console.error(error);

                status.textContent =
                'Не удалось обновить состояние элементов формы. ' +
                'Проверьте разметку кнопок в buildForm(). ' +
                'Если выполнялась запись, перед повтором ' +
                'сверьте сохранённые данные после перезагрузки.';
            }
        }
    }

    function renderList() {
        list.replaceChildren();

        for (const item of engines) {
            const card = node('article', undefined, 'admin-card');
            const open = node(
                'button',
                'Открыть черновик',
                'btn btn-outline-primary'
            );

            open.type = 'button';
            open.addEventListener('click', () => {
                if (working() || !isAllowed() || !canDiscard()) {
                    return;
                }

                void run(async () => {
                    // Старую форму не заменяем до успешного чтения.
                    const state = await api.read(item.id);

                    if (state.draft.rules_engine_version !== '1.0') {
                        throw new Error(
                            'Этот интерфейс поддерживает ' +
                            'исполнитель версии 1.0.'
                        );
                    }

                    if (state.draft.rules_json?.schema_version !== 3) {
                        throw new Error(
                            'Этот редактор движка поддерживает ' +
                            'числовую схему правил 3. Старые черновики ' +
                            'автоматически не преобразуются.'
                        );
                    }

                    buildForm(item, state.draft, state.versions);
                    blocked = false;

                    status.textContent =
                    `Загружен черновик, ревизия ${draft.revision}.`;
                });
            });

            card.append(
                node('h3', item.name),
                node(
                    'p',
                    `${item.slug} · ` +
                    (item.visibility === 'public'
                    ? 'Публичный'
                    : 'Приватный') +
                    (item.is_active === false ? ' · Неактивный' : '')
                ),
                node('p', item.description || 'Без описания'),
                open
            );

            list.append(card);
        }

        if (!engines.length) {
            list.append(node('p', 'Ваших движков пока нет.'));
        }

        sync();
    }

    function showVersionState() {
        const info = form?.querySelector('[data-engine-version-state]');

        if (!info) {
            return;
        }

        const numbers = versions
            .map((item) => item.version_number)
            .sort((a, b) => a - b);

        info.textContent = [
            draft
            ? `Ревизия черновика: ${draft.revision}.`
            : 'Новая игровая система.',
            numbers.length
            ? `Публикации: ${numbers.join(', ')}.`
            : 'Публикаций пока нет.',
            alreadyPublished()
            ? 'Текущая ревизия уже опубликована.'
            : '',
            unsaved()
            ? 'Есть несохранённые изменения.'
            : ''
        ].filter(Boolean).join(' ');
    }

    function buildForm(nextEngine, nextDraft, nextVersions = []) {
        engine = nextEngine;
        draft = nextDraft;
        versions = nextVersions;
        loaded = false;
        metadataDirty = false;
        editor = null;
        layout = null;

        area.innerHTML = `
            <form class="system-editor" novalidate>
                <h3 data-engine-heading></h3>

                <fieldset data-engine-metadata>
                    <legend>Карточка движка</legend>

                    <label class="system-editor__field">
                        Название
                        <input name="name" required maxlength="100">
                    </label>

                    <label class="system-editor__field">
                        Код
                        <input name="slug" required maxlength="100"
                               pattern="[a-z0-9]+((_|-)[a-z0-9]+)*"
                               autocomplete="off" spellcheck="false">
                    </label>

                    <label class="system-editor__field">
                        Описание
                        <textarea name="description" rows="3"></textarea>
                    </label>

                    <label class="system-editor__field">
                        Видимость
                        <select name="visibility">
                            <option value="private">Приватный</option>
                            <option value="public">Публичный</option>
                        </select>
                    </label>

                    <p class="profile-note">
                        Видимость задаётся при создании.
                        Публичная публикация может использоваться
                        другими администраторами в рамках текущего доступа.
                    </p>
                </fieldset>

                <p data-engine-card-note class="profile-note"></p>

                <div data-engine-rules>
                    <div data-rules-basis></div>

                    <p data-rules-message role="status"
                       aria-live="polite"></p>

                    <fieldset data-rules-controls disabled>
                        <legend>Правила движка</legend>
                        <div data-rules-body></div>
                    </fieldset>
                </div>

                <p data-engine-version-state role="status"
                   aria-live="polite"></p>

                <button type="submit" class="btn btn-primary"
                        data-engine-save>
                    Сохранить черновик
                </button>

                <button type="button" class="btn btn-outline-primary"
                        data-engine-publish>
                    Опубликовать сохранённую ревизию
                </button>

                <hr>

                <p class="profile-note">
                    Деактивация запрещает новый выбор этого движка
                    как основы. Существующие системы сохраняют
                    связь с выбранной публикацией.
                    Удаление доступно только без публикаций.
                </p>

                <button type="button" class="btn btn-outline-primary"
                        data-engine-activity>
                    Изменить активность
                </button>

                <button type="button" class="btn btn-outline-primary"
                        data-engine-delete>
                    Удалить игровую систему
                </button>
            </form>
        `;

        form = area.querySelector('form');
        form.querySelector('[data-engine-heading]').textContent =
        engine ? engine.name : 'Новые правила игровой системы';

        const values = engine || {
            name: '',
            slug: `engine-${Date.now().toString(36)}-` +
            Math.random().toString(36).slice(2, 8),
            description: '',
            visibility: 'private'
        };

        for (const name of ['name', 'slug', 'description', 'visibility']) {
            const input = form.elements.namedItem(name);
            input.value = values[name] ?? '';

            if (engine) {
                if (input instanceof HTMLSelectElement) {
                    input.disabled = true;
                } else {
                    input.readOnly = true;
                }
            }
        }

        form.querySelector('[data-engine-card-note]').textContent =
        engine
        ? 'Карточка показана только для чтения: текущий API ' +
        'сохраняет правила, но не изменяет название и видимость.'
        : 'Начните с пустых правил или загрузите числовую основу. ' +
        'Затем настройте показатели, формулы и начальные значения. ' +
        'Это не полная реализация D&D или Pathfinder.';

        editor = createEngineRulesEditor(
            form.querySelector('[data-engine-rules]'),
            {
                request,
                getExecutorVersion: () =>
                draft?.rules_engine_version || '1.0',
                onBusy(value) {
                    editorBusy = value;
                    sync();
                },
                onChange() {
                    showVersionState();
                    sync();
                }
            }
        );

        layout = mountEngineEditorLayout(form, {
            onClose() {
                if (working() || !canDiscard()) {
                    return;
                }

                engine = null;
                draft = null;
                versions = [];
                editor = null;
                layout = null;
                form = null;
                loaded = false;
                metadataDirty = false;

                area.replaceChildren();

                status.textContent =
                'Редактор закрыт. Сохранённые данные не изменены.';

                sync();
            }
        });

        form.addEventListener('input', (event) => {
            if (!(event.target instanceof HTMLElement)) {
                return;
            }

            if (event.target.dataset.sample === 'true') {
                return;
            }

            if (event.target.closest('[data-engine-metadata]')) {
                metadataDirty = true;
            }

            showVersionState();
            sync();
        });

        form.addEventListener('change', () => {
            showVersionState();
            sync();
        });

        form.addEventListener('submit', save);

        form.querySelector('[data-engine-publish]')
            .addEventListener('click', publish);

        form.querySelector('[data-engine-activity]')
            .addEventListener('click', changeActivity);

        form.querySelector('[data-engine-delete]')
            .addEventListener('click', removeEngine);

        if (draft) {
            editor.acceptEngineDraft(draft);
            loaded = true;
        }

        showVersionState();
        sync();
    }

    function save(event) {
        event.preventDefault();

        if (working() || !loaded || blocked || !isAllowed()) {
            return;
        }

        let rules;
        let data;

        // Локальная валидация до начала записывающего запроса.
        try {
            if (!form.reportValidity()) {
                return;
            }

            rules = editor.collect();

            if (!engine) {
                const name = form.elements.namedItem('name').value.trim();
                const slug = form.elements.namedItem('slug').value.trim();

                if (!name || !slug) {
                    throw new Error(
                        'Название и код не должны состоять из пробелов.'
                    );
                }

                data = {
                    name,
                    slug,
                    description:
                    form.elements.namedItem('description')
                        .value.trim() || null,
                    visibility:
                    form.elements.namedItem('visibility').value,
                    rules_engine_version: '1.0',
                    rules
                };
            }
        } catch (error) {
            status.textContent = error.message;
            return;
        }

        const editing = Boolean(engine);

        void run(async () => {
            if (editing) {
                const saved = await api.save(
                    engine.id,
                    rules,
                    draft.revision
                );

                editor.acceptEngineDraft(saved);
                draft = saved;
            } else {
                const saved = await api.create(data);

                // Сначала проверяем совместимость ответа с редактором.
                editor.acceptEngineDraft(saved.draft);

                engines = [...engines, saved.engine];
                buildForm(saved.engine, saved.draft);
                renderList();
            }

            metadataDirty = false;
            showVersionState();

            status.textContent =
            'Черновик движка сохранён. Публикация не выполнялась.';
        }, true, editing);
    }

    function changeActivity() {
        if (
        working() ||
        !isAllowed() ||
        !loaded ||
        blocked ||
        !engine
        ) {
            return;
        }

        const selected = engine;
        const nextActive = !selected.is_active;

        const question = nextActive
        ? `Активировать игровую систему «${selected.name}»?`
        : `Деактивировать игровую систему «${selected.name}»? ` +
        'Его нельзя будет выбрать для новой основы. ' +
        'Уже связанные системы продолжат работать.';

        if (!window.confirm(question)) {
            return;
        }

        void run(async () => {
            const saved = await api.setActive(
                selected.id,
                nextActive,
                selected.is_active
            );

            engine = saved;
            engines = engines.map((item) =>
            item.id === saved.id ? saved : item
            );

            // Форму не пересоздаём: несохранённые правила остаются.
            renderList();
            showVersionState();

            status.textContent = saved.is_active
            ? 'Игровая система активирована.'
            : 'Игровая система деактивирована. Сохранённые связи не изменены.';
        }, true);
    }

    function removeEngine() {
        if (
        working() ||
        !isAllowed() ||
        !loaded ||
        blocked ||
        !engine ||
        versions.length > 0
        ) {
            return;
        }

        const selected = engine;
        const expectedRevision = draft.revision;

        const warning = unsaved()
        ? '\nНесохранённые изменения формы также будут потеряны.\n'
        : '\n';

        const confirmation = window.prompt(
            `Удалить игровую систему «${selected.name}» и его черновик?\n` +
            'Действие нельзя отменить. При наличии публикаций ' +
            'сервер запретит удаление.\n' +
            warning +
            '\nДля подтверждения введите название игровой системы:',
            ''
        );

        if (confirmation === null) {
            return;
        }

        if (confirmation !== selected.name) {
            status.textContent =
            'Название не совпало. Удаление не выполнялось.';
            return;
        }

        void run(async () => {
            await api.remove(selected.id, expectedRevision);

            engines = engines.filter(
                (item) => item.id !== selected.id
            );

            engine = null;
            draft = null;
            versions = [];
            editor = null;
            form = null;
            layout = null;
            loaded = false;
            metadataDirty = false;
            area.replaceChildren();

            renderList();

            status.textContent =
            `Игровая система «${selected.name}» и её черновик удалены.`;
        }, true);
    }

    function publish() {
        if (
        working() ||
        !isAllowed() ||
        !loaded ||
        blocked ||
        !engine ||
        engine.is_active !== true ||
        unsaved() ||
        alreadyPublished()
        ) {
            return;
        }

        if (!window.confirm(
            `Опубликовать ревизию ${draft.revision} ` +
            `движка «${engine.name}»? ` +
            'Опубликованный снимок нельзя будет редактировать. ' +
            'Существующие системы автоматически не обновятся.'
        )) {
            return;
        }

        const engineId = engine.id;
        const expectedRevision = draft.revision;

        void run(async () => {
            const saved = await api.publish(
                engineId,
                expectedRevision
            );

            // Сервер публикует expectedRevision и в той же
            // транзакции увеличивает ревизию черновика на один.
            const nextDraft = {
                ...draft,
                revision: expectedRevision + 1
            };

            editor.acceptEngineDraft(nextDraft);
            draft = nextDraft;
            versions = [...versions, saved];

            showVersionState();

            status.textContent =
            `Опубликована версия №${saved.version_number}. ` +
            'Существующие системы автоматически не обновляются.';
        }, true);
    }

    refresh.addEventListener('click', () => {
        void run(async () => {
            engines = await api.listOwned();
            renderList();

            status.textContent = blocked
            ? 'Список обновлён. Откройте сохранённую игровую систему ' +
            'и сверьте состояние перед новой записью.'
            : `Загружено ваших игровых систем: ${engines.length}.`;
        });
    });

    newButton.addEventListener('click', () => {
        if (
        working() ||
        blocked ||
        !isAllowed() ||
        !canDiscard()
        ) {
            return;
        }

        void run(async () => {
            buildForm(null, null);
            await editor.load();

            loaded = true;
            showVersionState();

            status.textContent =
            'Заполните карточку движка и настройте числовые правила. ' +
            'Можно начать с нуля или загрузить готовую основу.';
        });
    });

    window.addEventListener('beforeunload', (event) => {
        if (!working() && !unsaved()) {
            return;
        }

        event.preventDefault();
        event.returnValue = '';
    });

    sync();

    return {
        isBusy: working,
        sync
    };
}