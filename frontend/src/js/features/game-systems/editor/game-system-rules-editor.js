// frontend/src/js/features/game-systems/editor/game-system-rules-editor.js

import {collectEngineOverrides, readEngineOverrides} from './game-system-engine-origin.js';

const OPERATIONS = [
    ['sum', 'Сложить'],
    ['subtract', 'Из первого значения вычесть второе'],
    ['multiply', 'Перемножить'],
    ['floor_div', 'Разделить с округлением вниз'],
    ['ceil_div', 'Разделить с округлением вверх'],
    ['min', 'Выбрать наименьшее'],
    ['max', 'Выбрать наибольшее']
];

const LABELS = {
    str: 'Сила',
    dex: 'Ловкость',
    con: 'Телосложение',
    int: 'Интеллект',
    wis: 'Мудрость',
    cha: 'Харизма'
};

const clone = (value) => JSON.parse(JSON.stringify(value));

const own = (object, key) =>
    Object.prototype.hasOwnProperty.call(object, key);

const FORMULA_MAX_DEPTH = 8;
const FORMULA_MAX_NODES = 256;
const FORMULA_MAX_ARGUMENTS = 16;
const FORMULA_VALUE_LIMIT = 1_000_000_000;

const BINARY_OPERATIONS = new Set([
    'subtract',
    'floor_div',
    'ceil_div'
]);

function isFormula(value) {
    return value !== null &&
        typeof value === 'object' &&
        !Array.isArray(value) &&
        Array.isArray(value.arguments);
}

function* leafArguments(formula) {
    const stack = [...formula.arguments].reverse();

    while (stack.length) {
        const argument = stack.pop();

        if (isFormula(argument)) {
            stack.push(...[...argument.arguments].reverse());
        } else {
            yield argument;
        }
    }
}

function element(tag, text, className) {
    const result = document.createElement(tag);

    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;

    return result;
}

function createBasisIcon(code) {
    const namespace = 'http://www.w3.org/2000/svg';

    const svg = document.createElementNS(namespace, 'svg');
    svg.classList.add('system-editor__basis-icon');
    svg.setAttribute('viewBox', '0 0 64 64');
    svg.setAttribute('width', '64');
    svg.setAttribute('height', '64');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');

    const illustrations = {
        // Двадцатигранная кость.
        dnd5e_2014_srd51: [
            ['path', {
                d: 'M32 5 55 19 55 45 32 59 9 45 9 19Z',
                class: 'system-editor__icon-surface'
            }],
            ['path', {
                d: 'M32 5 20 25 44 25Z'
            }],
            ['path', {
                d: 'M9 19 20 25 9 45M55 19 44 25 55 45'
            }],
            ['path', {
                d: 'M20 25 32 47 44 25ZM9 45 32 47 55 45M32 47V59'
            }]
        ],

        // Щит с компасной звездой.
        pf2e_remaster: [
            ['path', {
                d: 'M32 5 53 13V30C53 43 44 53 32 59'
                    + ' 20 53 11 43 11 30V13Z',
                class: 'system-editor__icon-surface'
            }],
            ['path', {
                d: 'M32 11 47 17V30C47 40 41 48 32 53'
                    + ' 23 48 17 40 17 30V17Z'
            }],
            ['path', {
                d: 'M32 19 36 28 45 32 36 36'
                    + ' 32 45 28 36 19 32 28 28Z'
            }]
        ],

        // Свиток для авторских правил.
        custom: [
            ['path', {
                d: 'M17 10H47V45H23V18'
                    + 'C23 13 21 10 17 10Z',
                class: 'system-editor__icon-surface'
            }],
            ['path', {
                d: 'M17 10C13 10 10 13 10 17'
                    + 'V22H23V18C23 13 21 10 17 10Z'
            }],
            ['path', {
                d: 'M23 45H54V48C54 53 51 56 47 56'
                    + 'H23C19 56 16 53 16 49V45Z',
                class: 'system-editor__icon-surface'
            }],
            ['path', {
                d: 'M47 45V49C47 53 44 56 40 56'
            }],
            ['path', {
                d: 'M29 22H40M29 29H40M29 36H36'
            }]
        ]
    };

    const shapes = illustrations[code] || illustrations.custom;

    for (const [tag, attributes] of shapes) {
        const shape = document.createElementNS(namespace, tag);

        for (const [name, value] of Object.entries(attributes)) {
            shape.setAttribute(name, value);
        }

        svg.append(shape);
    }

    return svg;
}

function button(text, action) {
    const result = element('button', text, 'btn btn-outline-primary');
    result.type = 'button';
    result.addEventListener('click', action);
    return result;
}

function field(title, control) {
    const result = element('label', undefined, 'system-editor__field');
    result.append(element('span', title), control);
    return result;
}

function control(value, options = {}) {
    const result = document.createElement('input');
    result.type = options.type || 'text';

    for (const [name, item] of Object.entries(options)) {
        result.setAttribute(name, String(item));
    }

    result.value = value ?? '';
    return result;
}

function choices(options, value) {
    const result = document.createElement('select');

    for (const [key, label] of options) {
        const option = element('option', label);
        option.value = key;
        result.append(option);
    }

    result.value = value;
    return result;
}

function upgrade(raw) {
    const result = clone(raw);

    if (result.schema_version === 1) {
        result.schema_version = 2;
        result.calculations = {
            attributes: Object.fromEntries(
                result.attribute_codes.map((code) => [
                    code,
                    {
                        label: LABELS[code] || code,
                        min_value: -1000,
                        max_value: 1000
                    }
                ])
            ),
            derived: {}
        };
    }

    if (
        result.schema_version !== 2 ||
        !result.calculations?.attributes ||
        !result.calculations?.derived
    ) {
        throw new Error(
            'Эта версия правил пока не поддерживается редактором.'
        );
    }

    return result;
}

export function createRulesEditor(host, {
    request,
    systemId,
    standaloneOnly = false,
    singlePage = false,
    getExecutorVersion = () => '1.0',
    onBusy = () => {},
    onChange = () => {},
    onInvalid = () => {}
}) {
    if (!host) return null;

    const body = host.querySelector('[data-rules-body]');
    const basis = host.querySelector('[data-rules-basis]');
    const message = host.querySelector('[data-rules-message]');
    const controls = host.querySelector('[data-rules-controls]');

    let profile = null;
    let revision = null;
    let dirty = false;
    let busy = false;
    let parentBusy = true;
    let presets = [];
    let selectedPreset = '';
    let engineVersion = null;
    let explicitOverrides = {};
    let availableEngines = [];
    let availableVersions = [];
    let selectedEngineId = '';
    let selectedVersionId = '';
    let enginesLoaded = false;
    let activePage = 'main';
    let result;
    let sampleLevel = '1';
    let samples = {};
    let sourceControls = [];
    // Временная память редактора, не часть отправляемых правил.
    // Позволяет переключиться на общее правило и обратно,
    // не потеряв набранную формулу до перезагрузки или сохранения.
    const modifierFormulaDrafts = new WeakMap();

    function sync() {
        controls.disabled = busy || parentBusy;

        basis.querySelectorAll('button, select, input').forEach((item) => {
            item.disabled = busy || parentBusy;
        });
    }

    function clearResult() {
        if (result) {
            result.hidden = true;
            result.replaceChildren();
        }
    }

    function changed() {
        dirty = true;
        clearResult();
        message.textContent = 'Есть несохранённые настройки правил.';
        onChange();
    }

    function showPage(name) {
        activePage = name;

        body.querySelectorAll('[data-editor-panel]').forEach((panel) => {
            panel.hidden = !singlePage && panel.dataset.editorPanel !== name;
        });
    }

    function page(name, title, help) {
        const panel = element(
            'section',
            undefined,
            'system-editor__panel'
        );

        panel.dataset.editorPanel = name;
        panel.setAttribute('aria-label', title);
        panel.append(
            element('h2', title),
            element('p', help, 'profile-note')
        );

        body.append(panel);
        return panel;
    }

    function details(title) {
        const result = element(
            'details',
            undefined,
            'system-editor__details'
        );

        result.append(element('summary', title));
        return result;
    }

    function bindInput(title, value, options, setter, sample = false) {
        const input = control(value, options);

        if (sample) input.dataset.sample = 'true';

        input.addEventListener('input', () => {
            setter(input.value);

            if (sample) {
                clearResult();
            } else {
                changed();
            }
        });

        return field(title, input);
    }

	function sources(excludeCode, scope = 'derived') {
        const values = [
            ['#number', 'Число'],
            ['#formula', 'Вложенное вычисление']
        ];

        if (scope === 'modifier') {
            values.push([
                'attribute.value',
                'Значение этой характеристики'
            ]);

            return values;
        }

        values.push(['level', 'Уровень персонажа']);

        if (!profile) return values;

        for (const [code, item] of Object.entries(
            profile.calculations.attributes
        )) {
            const title = item.label.trim() || 'Без названия';

            values.push(
                [`attribute.${code}`, `Значение: ${title}`],
                [`modifier.${code}`, `Модификатор: ${title}`]
            );
        }

        for (const [code, item] of Object.entries(
            profile.calculations.derived
        )) {
            if (code !== excludeCode) {
                values.push([
                    `stat.${code}`,
                    `Показатель: ${item.label.trim() || 'Без названия'}`
                ]);
            }
        }

        return values;
    }

    function refreshSources() {
        for (const item of sourceControls) {
            const current = item.select.value;
            const options = sources(item.code, item.scope);

            if (!options.some(([value]) => value === current)) {
                options.push([
                    current,
                    'Недоступный источник — выберите другой'
                ]);
            }

            const replacement = choices(options, current);

            item.select.replaceChildren(...replacement.children);
            item.select.value = current;
        }
    }

    function newCode(prefix, collection) {
        let number = 1;

        while (own(collection, `${prefix}_${number}`)) {
            number += 1;
        }

        return `${prefix}_${number}`;
    }

    function deleteEntry(kind, code) {
        const references = kind === 'attributes'
            ? [`attribute.${code}`, `modifier.${code}`]
            : [`stat.${code}`];

        const usedBy = Object.entries(profile.calculations.derived)
            .filter(([dependentCode, item]) => {
                // Собственная некорректная ссылка не должна
                // мешать удалить сам этот показатель.
                if (kind === 'derived' && dependentCode === code) {
                    return false;
                }

                return [...leafArguments(item.formula)]
                    .some((argument) => references.includes(argument));
            })
            .map(([, item]) => item.label || 'Показатель без названия');

        if (usedBy.length) {
            message.textContent =
                'Сначала измените формулы, использующие этот элемент: ' +
                usedBy.join(', ') + '.';
            return;
        }

        if (
            kind === 'attributes' &&
            Object.keys(profile.calculations.attributes).length === 1
        ) {
            message.textContent =
                'Текущему движку нужна хотя бы одна характеристика.';
            return;
        }

        if (!window.confirm('Удалить этот элемент из черновика?')) {
            return;
        }

        delete profile.calculations[kind][code];

        // В samples находятся только характеристики примера.
        // Удаление показателя не должно очищать их значения.
        if (kind === 'attributes') {
            delete samples[code];
        }

        changed();
        render();
    }

        function checkEngineVersion(version, engineId, versionId) {
            if (
                !version ||
                version.id !== versionId ||
                version.engine_id !== engineId ||
                !Number.isInteger(version.version_number) ||
                version.version_number < 1 ||
                !version.rules_json
            ) {
                throw new Error(
                    'Сервер вернул некорректную публикацию движка.'
                );
            }

            if (
                version.rules_engine_version !== getExecutorVersion()
            ) {
                throw new Error(
                    'Публикация рассчитана на другую версию ' +
                    'программного исполнителя.'
                );
            }

            // Автоматически изменять защищённую schema_version
            // выбранной публикации нельзя.
            if (version.rules_json.schema_version !== 2) {
                throw new Error(
                    'Эта публикация пока не поддерживается ' +
                    'связанным редактором. Нужна схема правил 2.'
                );
            }

            return upgrade(version.rules_json);
        }

        async function readAllPages(path) {
            const items = [];
            const ids = new Set();
            let offset = 0;

            while (true) {
                const data = await request(
                    `${path}?limit=100&offset=${offset}`
                );

                if (!Array.isArray(data?.items)) {
                    throw new Error(
                        'Сервер вернул некорректную страницу каталога.'
                    );
                }

                for (const item of data.items) {
                    if (
                        typeof item?.id !== 'string' ||
                        !item.id ||
                        ids.has(item.id)
                    ) {
                        throw new Error(
                            'Каталог изменился или содержит ' +
                            'некорректные записи. Повторите загрузку.'
                        );
                    }

                    ids.add(item.id);
                    items.push(item);
                }

                if (data.next_offset === null) return items;

                if (
                    !Number.isSafeInteger(data.next_offset) ||
                    data.next_offset <= offset ||
                    data.items.length === 0
                ) {
                    throw new Error(
                        'Сервер вернул некорректное продолжение каталога.'
                    );
                }

                offset = data.next_offset;
            }
        }

        async function basisAction(action) {
            if (busy || parentBusy) return;

            busy = true;
            onBusy(true);
            sync();

            try {
                await action();
            } catch (error) {
                message.textContent =
                    error.message || 'Не удалось загрузить основу.';
            } finally {
                busy = false;
                onBusy(false);
                sync();
            }
        }

        function renderBasis() {
            if (standaloneOnly) {
                renderStandaloneBasis();
                return;
            }
            if (!engineVersion) {
                renderStandaloneBasis();
            } else {
                basis.replaceChildren();

                basis.append(
                    element('h3', 'Связанная система'),
                    element(
                        'p',
                        `Основа: публикация №${engineVersion.version_number}. ` +
                        `Профиль: ${engineVersion.rules_json.base_ruleset}.`
                    ),
                    element(
                        'p',
                        'Редактор меняет правила этой системы, ' +
                        'но не опубликованный движок. Новые публикации ' +
                        'не подключаются автоматически.',
                        'profile-note'
                    )
                );
            }

            const catalog = element(
                'section',
                undefined,
                'system-editor__details'
            );

            catalog.append(
                element('h3', 'Опубликованный движок'),
                element(
                    'p',
                    'Выбор публикации заменит текущие настройки правил. ' +
                    'Название и описание системы останутся в форме.',
                    'profile-note'
                )
            );

            catalog.append(button(
                enginesLoaded
                    ? 'Обновить каталог движков'
                    : 'Загрузить каталог движков',
                () => void basisAction(async () => {
                    const loaded = await readAllPages(
                        '/admin/rule-engines'
                    );

                    availableEngines = loaded;
                    availableVersions = [];
                    selectedEngineId = loaded[0]?.id || '';
                    selectedVersionId = '';
                    enginesLoaded = true;

                    renderBasis();

                    message.textContent = loaded.length
                        ? 'Выберите движок и загрузите его публикации.'
                        : 'Доступных опубликованных движков пока нет.';
                })
            ));

            if (availableEngines.length) {
                const engineSelect = choices(
                    availableEngines.map((item) => [
                        item.id,
                        item.name || item.slug || 'Движок без названия'
                    ]),
                    selectedEngineId
                );

                engineSelect.addEventListener('change', () => {
                    selectedEngineId = engineSelect.value;
                    selectedVersionId = '';
                    availableVersions = [];
                    renderBasis();
                    sync();
                });

                catalog.append(
                    field('Движок', engineSelect),
                    button(
                        'Загрузить публикации',
                        () => void basisAction(async () => {
                            const engineId = selectedEngineId;

                            const loaded = await readAllPages(
                                '/admin/rule-engines/' +
                                encodeURIComponent(engineId) +
                                '/versions'
                            );

                            availableVersions = loaded.filter(
                                (item) =>
                                    item.engine_id === engineId &&
                                    item.rules_engine_version ===
                                        getExecutorVersion()
                            );

                            selectedVersionId =
                                availableVersions[0]?.id || '';

                            renderBasis();

                            message.textContent = availableVersions.length
                                ? 'Выберите конкретную публикацию.'
                                : 'Для этого движка нет публикаций, ' +
                                    'совместимых с исполнителем системы.';
                        })
                    )
                );
            }

            if (availableVersions.length) {
                const versionSelect = choices(
                    availableVersions.map((item) => [
                        item.id,
                        `Публикация №${item.version_number}`
                    ]),
                    selectedVersionId
                );

                versionSelect.addEventListener('change', () => {
                    selectedVersionId = versionSelect.value;
                });

                catalog.append(
                    field('Публикация', versionSelect),
                    button(
                        'Использовать публикацию',
                        () => void basisAction(async () => {
                            if (
                                profile &&
                                !window.confirm(
                                    'Заменить текущие настройки правил ' +
                                    'выбранной публикацией? Изменения ' +
                                    'характеристик и формул будут сброшены. ' +
                                    'Карточка системы останется без изменений.'
                                )
                            ) {
                                return;
                            }

                            const engineId = selectedEngineId;
                            const versionId = selectedVersionId;

                            const version = await request(
                                '/admin/rule-engines/' +
                                encodeURIComponent(engineId) +
                                '/versions/' +
                                encodeURIComponent(versionId)
                            );

                            const nextProfile = checkEngineVersion(
                                version,
                                engineId,
                                versionId
                            );

                            // Состояние меняем только после успешной
                            // загрузки и проверки всей публикации.
                            profile = nextProfile;
                            engineVersion = clone(version);
                            explicitOverrides = {};
                            samples = {};
                            sampleLevel = '1';

                            changed();
                            renderBasis();
                            render();

                            message.textContent =
                                'Публикация выбрана. Настройте систему ' +
                                'и сохраните изменения.';
                        })
                    )
                );
            }

            basis.append(catalog);
            sync();
        }

    function renderStandaloneBasis() {
        basis.replaceChildren();
        basis.append(element('h3', 'Самостоятельная система из пресета'));

        if (profile) {
            const names = {
                dnd5e_2014_srd51:
                    'D&D 5e — SRD 5.1 / правила 2014 года',
                pf2e_remaster: 'Pathfinder 2e Remaster'
            };

            basis.append(element(
                'p',
                names[profile.base_ruleset] || profile.base_ruleset
            ));

            basis.append(element(
                'p',
                'Настройки основы можно изменять. ' +
                'Для замены всей основы загрузите страницу заново ' +
                'до начала редактирования или создайте другую систему.',
                'profile-note'
            ));
        } else {
            const cards = element(
                'div',
                undefined,
                'system-editor__basis-grid'
            );

            const descriptions = {
                dnd5e_2014_srd51: 'Правила 2014 года · SRD 5.1',
                pf2e_remaster: 'Remaster'
            };

            for (const preset of presets) {
                const card = element(
                    'label',
                    undefined,
                    'system-editor__basis-card'
                );

                const radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = 'editor_basis_choice';
                radio.value = preset.code;
                radio.checked = selectedPreset === preset.code;

                const text = element(
                    'span',
                    undefined,
                    'system-editor__basis-text'
                );

                text.append(
                    element('strong', preset.name),
                    element(
                        'small',
                        descriptions[preset.code] ||
                            'Готовые настройки расчётов'
                    )
                );

                radio.addEventListener('change', () => {
                    selectedPreset = radio.value;

                    for (const option of cards.querySelectorAll(
                        '.system-editor__basis-card'
                    )) {
                        option.classList.toggle(
                            'is-selected',
                            option.querySelector('input')?.checked === true
                        );
                    }
                });

                card.classList.toggle('is-selected', radio.checked);
                card.append(
                    radio,
                    createBasisIcon(preset.code),
                    text
                );

                cards.append(card);
            }

            // Информационная карточка, а не доступный пресет.
            const custom = element(
                'div',
                undefined,
                'system-editor__basis-card ' +
                'system-editor__basis-card--unavailable'
            );

            const customText = element(
                'span',
                undefined,
                'system-editor__basis-text'
            );

            customText.append(
                element('strong', 'Свои правила'),
                element('small', 'После расширения движка')
            );

            custom.append(
                createBasisIcon('custom'),
                customText
            );

            cards.append(custom);

            const apply = button('Использовать основу', () => {
                const preset = presets.find(
                    (item) => item.code === selectedPreset
                );

                if (!preset?.rules) {
                    message.textContent =
                        'Сначала выберите основу правил.';
                    cards.querySelector('input')?.focus();
                    return;
                }

                try {
                    profile = upgrade(preset.rules);
                    engineVersion = null;
                    explicitOverrides = {};
                    samples = {};
                    sampleLevel = '1';
                    changed();
                    renderBasis();
                    render();
                    sync();
                } catch (error) {
                    message.textContent = error.message;
                }
            });

            basis.append(
                cards,
                element(
                    'p',
                    'Основа заполняет настройки. Их можно изменить.',
                    'system-editor__basis-note'
                ),
                apply
            );
        }

        basis.append(element(
            'p',
            'Независимые авторские правила станут доступны после ' +
            'расширения движка. Сейчас можно изменять поддерживаемые ' +
            'характеристики и формулы выбранной основы.',
            'profile-note'
        ));
    }

    function standardModifierFormula() {
        // Переносим прежнее правило в дерево вычислений.
        // При некорректных исходных числах не создаём повреждённую формулу.
        const offset = integer(
            profile.modifier_offset,
            'Вычитаемое число',
            -1000,
            1000
        );

        const divisor = integer(
            profile.modifier_divisor,
            'Делитель',
            1,
            1000
        );

        return {
            operation: 'floor_div',
            arguments: [
                {
                    operation: 'subtract',
                    arguments: ['attribute.value', offset]
                },
                divisor
            ]
        };
    }

    function renderModifierSettings(owner, individual = false) {
        const block = element(
            'div',
            undefined,
            'system-editor__modifier-settings'
        );

        const custom = owner.modifier_formula != null;

        const mode = choices([
            [
                'inherit',
                individual
                    ? 'По общему правилу системы'
                    : 'Стандартное правило: вычесть и разделить'
            ],
            ['custom', 'Своя формула']
        ], custom ? 'custom' : 'inherit');

        mode.addEventListener('change', () => {
            try {
                if (mode.value === 'custom') {
                    const cached = modifierFormulaDrafts.get(owner);

                    if (cached) {
                        owner.modifier_formula = clone(cached);
                    } else if (
                        individual &&
                        isFormula(profile.modifier_formula)
                    ) {
                        // Начинаем с независимой копии общей формулы.
                        owner.modifier_formula = clone(
                            profile.modifier_formula
                        );
                    } else {
                        owner.modifier_formula = standardModifierFormula();
                    }
                } else {
                    if (isFormula(owner.modifier_formula)) {
                        modifierFormulaDrafts.set(
                            owner,
                            clone(owner.modifier_formula)
                        );
                    }

                    owner.modifier_formula = null;
                }

                changed();
                render();
            } catch (error) {
                mode.value = custom ? 'custom' : 'inherit';

                message.textContent =
                    error.message || 'Не удалось изменить правило расчёта.';
            }
        });

        block.append(field(
            individual
                ? 'Расчёт модификатора характеристики'
                : 'Общее правило модификаторов',
            mode
        ));

        if (custom) {
            block.append(element(
                'p',
                individual
                    ? 'Эта формула заменяет общее правило только для ' +
                        'данной характеристики.'
                    : 'Эта формула применяется к характеристикам, ' +
                        'у которых не задано собственное правило.',
                'profile-note'
            ));

            if (isFormula(owner.modifier_formula)) {
                block.append(
                    renderFormula(
                        owner.modifier_formula,
                        null,
                        1,
                        'modifier'
                    )
                );
            } else {
                block.append(element(
                    'p',
                    'Формула имеет неподдерживаемую структуру. ' +
                        'Выберите стандартное или общее правило, ' +
                        'затем создайте свою формулу заново.',
                    'profile-note'
                ));
            }
        } else if (individual) {
            block.append(element(
                'p',
                'Используется общая формула системы, а если она не задана — ' +
                    'стандартное правило вычитания и деления.',
                'profile-note'
            ));
        }

        return block;
    }

    function validateModifierFormula(formula, title) {
        if (formula == null) return;

        if (!isFormula(formula)) {
            throw new Error(`${title}: не задана корректная формула.`);
        }

        validateFormulaTree(
            formula,
            null,
            title,
            'modifier'
        );
    }

    function renderAttributes(panel) {
        const mode = choices([
            ['score', 'Значение → вычисляемый модификатор'],
            ['modifier', 'Модификатор вводится напрямую']
        ], profile.attribute_mode);

        mode.addEventListener('change', () => {
            profile.attribute_mode = mode.value;
            changed();
            render();
        });

        panel.append(field('Как используются характеристики', mode));

        if (profile.attribute_mode === 'score') {
            panel.append(
                element(
                    'p',
                    'Задайте общее правило расчёта модификаторов. ' +
                        'Для отдельных характеристик его можно переопределить.',
                    'profile-note'
                ),
                renderModifierSettings(profile)
            );

            const standard = details(
                'Стандартное правило: вычитание и деление'
            );

            standard.append(
                element(
                    'p',
                    'Используется, если общая и индивидуальная формулы ' +
                        'не заданы. Из значения вычитается число, затем ' +
                        'результат делится с округлением вниз.',
                    'profile-note'
                ),
                bindInput(
                    'Вычесть из значения',
                    profile.modifier_offset,
                    {
                        type: 'number',
                        required: true,
                        min: -1000,
                        max: 1000,
                        step: 1
                    },
                    (value) => {
                        profile.modifier_offset = value;
                    }
                ),
                bindInput(
                    'Разделить на',
                    profile.modifier_divisor,
                    {
                        type: 'number',
                        required: true,
                        min: 1,
                        max: 1000,
                        step: 1
                    },
                    (value) => {
                        profile.modifier_divisor = value;
                    }
                )
            );

            panel.append(standard);
        } else {
            panel.append(element(
                'p',
                'Введённое значение уже является модификатором. ' +
                    'Настроенные формулы сохраняются, но в этом режиме ' +
                    'не применяются.',
                'profile-note'
            ));
        }

        const cards = element(
            'div',
            undefined,
            'system-editor__cards'
        );

        for (const [code, item] of Object.entries(
            profile.calculations.attributes
        )) {
            const card = element(
                'article',
                undefined,
                'system-editor__card'
            );

            card.append(bindInput(
                'Название характеристики',
                item.label,
                { required: true, maxlength: 100 },
                (value) => {
                    item.label = value;
                    refreshSources();
                }
            ));

            const settings = details(
                'Настроить допустимые значения'
            );

            settings.append(
                bindInput(
                    'Минимальное значение',
                    item.min_value,
                    {
                        type: 'number',
                        required: true,
                        min: -1000,
                        max: 1000,
                        step: 1
                    },
                    (value) => {
                        item.min_value = value;
                    }
                ),
                bindInput(
                    'Максимальное значение',
                    item.max_value,
                    {
                        type: 'number',
                        required: true,
                        min: -1000,
                        max: 1000,
                        step: 1
                    },
                    (value) => {
                        item.max_value = value;
                    }
                )
            );

            card.append(settings);

            if (profile.attribute_mode === 'score') {
                card.append(renderModifierSettings(item, true));
            }

            card.append(button(
                'Удалить характеристику',
                () => deleteEntry('attributes', code)
            ));

            cards.append(card);
        }

        panel.append(
            cards,
            button('Добавить характеристику', () => {
                const collection = profile.calculations.attributes;

                if (Object.keys(collection).length >= 40) {
                    message.textContent =
                        'Текущая версия движка поддерживает ' +
                        'до 40 характеристик.';
                    return;
                }

                const code = newCode('attribute', collection);

                collection[code] = {
                    label: 'Новая характеристика',
                    min_value: profile.attribute_mode === 'score'
                        ? 1
                        : -10,
                    max_value: profile.attribute_mode === 'score'
                        ? 30
                        : 20,
                    modifier_formula: null
                };

                changed();
                render();
            })
        );
    }

    function renderFormula(formula, code, depth = 1, scope = 'derived') {

        const block = element(
            'div',
            undefined,
            'system-editor__formula'
        );

        block.append(element(
            'h4',
            depth === 1
                ? (
                    scope === 'modifier'
                        ? 'Формула модификатора'
                        : 'Формула показателя'
                )
                : 'Вложенное вычисление'
        ));

        const operation = choices(OPERATIONS, formula.operation);

        operation.addEventListener('change', () => {
            formula.operation = operation.value;

            // Для вычитания и деления нужны два аргумента.
            // Уже введённые лишние аргументы не удаляем:
            // пользователь сам решит, какие оставить.
            if (BINARY_OPERATIONS.has(formula.operation)) {
                while (formula.arguments.length < 2) {
                    formula.arguments.push(
                        formula.operation === 'subtract' ? 0 : 1
                    );
                }
            }

            changed();
            render();
        });

        block.append(field('Математическое действие', operation));

        const binary = BINARY_OPERATIONS.has(formula.operation);

        if (binary) {
            block.append(element(
                'p',
                formula.operation === 'subtract'
                    ? 'Из первого значения вычитается второе. ' +
                        'Нужны ровно два значения.'
                    : 'Первое значение делится на второе. ' +
                        'Нужны ровно два значения.',
                'profile-note'
            ));
        }

        formula.arguments.forEach((argument, index) => {
            const argumentBlock = element(
                'div',
                undefined,
                'system-editor__formula-argument'
            );

            const row = element(
                'div',
                undefined,
                'system-editor__operand'
            );

            const nested = isFormula(argument);
            const numeric =
                typeof argument === 'number' || argument === null;

            const current = nested
                ? '#formula'
                : numeric ? '#number' : argument;

            const options = sources(code, scope);

            if (!options.some(([value]) => value === current)) {
                options.push([
                    current,
                    'Недоступный источник — выберите другой'
                ]);
            }

            const source = choices(options, current);
            sourceControls.push({ select: source, code, scope });

            source.addEventListener('change', () => {
                if (
                    source.value === '#formula' &&
                    depth >= FORMULA_MAX_DEPTH
                ) {
                    source.value = current;
                    message.textContent =
                        'Достигнута допустимая глубина вычислений. ' +
                        'Упростите формулу или используйте другой показатель.';
                    return;
                }

                if (source.value === '#formula') {
                    // Берём последнее значение из модели:
                    // число могло измениться после отрисовки поля.
                    const previous = formula.arguments[index];

                    formula.arguments[index] = {
                        operation: 'sum',
                        arguments: [previous]
                    };
                } else if (source.value === '#number') {
                    formula.arguments[index] = 0;
                } else {
                    formula.arguments[index] = source.value;
                }

                changed();
                render();
            });

            let title = `Значение ${index + 1}`;

            if (formula.operation === 'subtract') {
                title = index === 0
                    ? 'Из какого значения вычесть'
                    : index === 1 ? 'Что вычесть' : title;
            } else if (
                formula.operation === 'floor_div' ||
                formula.operation === 'ceil_div'
            ) {
                title = index === 0
                    ? 'Что разделить'
                    : index === 1 ? 'На что разделить' : title;
            }

            row.append(field(title, source));

            if (numeric) {
                row.append(bindInput(
                    'Число',
                    argument,
                    {
                        type: 'number',
                        required: true,
                        min: -FORMULA_VALUE_LIMIT,
                        max: FORMULA_VALUE_LIMIT,
                        step: 1
                    },
                    (value) => {
                        formula.arguments[index] =
                            value === '' ? null : Number(value);
                    }
                ));
            }

            const remove = button('Убрать значение', () => {
                formula.arguments.splice(index, 1);
                changed();
                render();
            });

            // Не оставляем операцию без аргументов,
            // а двоичную операцию — менее чем с двумя.
            remove.disabled =
                formula.arguments.length <= (binary ? 2 : 1);

            row.append(remove);
            argumentBlock.append(row);

            if (nested) {
                argumentBlock.append(
                    renderFormula(argument, code, depth + 1, scope)
                );
            }

            block.append(argumentBlock);
        });

        const add = button('Добавить значение', () => {
            formula.arguments.push(0);
            changed();
            render();
        });

        add.disabled = formula.arguments.length >= (
            binary ? 2 : FORMULA_MAX_ARGUMENTS
        );

        block.append(add);

        if (binary && formula.arguments.length > 2) {
            block.append(element(
                'p',
                'Для выбранного действия оставьте ровно два значения. ' +
                'Уже введённые данные не удалены автоматически.',
                'profile-note'
            ));
        }

        return block;
    }

    function renderDerived(panel) {
        panel.append(element(
            'p',
            'Для каждого значения выберите число, источник или ' +
            'вложенное вычисление. Вложенный блок сначала рассчитывается ' +
            'целиком, затем его результат используется во внешнем действии.'
        ));

        for (const [code, item] of Object.entries(
            profile.calculations.derived
        )) {
            const card = element(
                'article',
                undefined,
                'system-editor__card'
            );

            card.append(
                bindInput(
                    'Название показателя',
                    item.label,
                    { required: true, maxlength: 100 },
                    (value) => {
                        item.label = value;
                        refreshSources();
                    }
                ),
                renderFormula(item.formula, code),
                button(
                    'Удалить показатель',
                    () => deleteEntry('derived', code)
                )
            );

            panel.append(card);
        }

        panel.append(button('Добавить показатель', () => {
            const collection = profile.calculations.derived;

            if (Object.keys(collection).length >= 128) {
                message.textContent =
                    'Текущая версия движка поддерживает ' +
                    'до 128 показателей.';
                return;
            }

            collection[newCode('stat', collection)] = {
                label: 'Новый показатель',
                formula: {
                    operation: 'sum',
                    arguments: [10]
                }
            };

            changed();
            render();
        }));
    }

    function renderPreview(panel) {
        panel.append(element(
            'p',
            'Значения примера нужны только для проверки. ' +
            'Они не сохраняются как характеристики будущих персонажей.'
        ));

        panel.append(bindInput(
            'Уровень персонажа для примера',
            sampleLevel,
            {
                type: 'number',
                required: true,
                min: 1,
                max: profile.max_level,
                step: 1
            },
            (value) => {
                sampleLevel = value;
            },
            true
        ));

        for (const [code, item] of Object.entries(
            profile.calculations.attributes
        )) {
            const initial = profile.attribute_mode === 'score'
                ? 10
                : 0;

            if (!own(samples, code)) {
                samples[code] = String(Math.max(
                    Number(item.min_value),
                    Math.min(initial, Number(item.max_value))
                ));
            }

            panel.append(bindInput(
                item.label || 'Характеристика без названия',
                samples[code],
                {
                    type: 'number',
                    required: true,
                    min: item.min_value,
                    max: item.max_value,
                    step: 1
                },
                (value) => {
                    samples[code] = value;
                },
                true
            ));
        }

        panel.append(button(
            'Проверить расчёт',
            () => void preview()
        ));

        result = element(
            'div',
            undefined,
            'system-editor__result'
        );

        result.setAttribute('aria-live', 'polite');
        result.hidden = true;
        panel.append(result);
    }

    function render() {
        body.replaceChildren();
        sourceControls = [];
        result = null;

        if (!profile) {
            for (const [name, title] of [
                ['attributes', 'Характеристики'],
                ['derived', 'Показатели'],
                ['preview', 'Проверка и сохранение']
            ]) {
                page(
                    name,
                    title,
                    'Сначала выберите основу на странице «Основа».'
                );
            }
        } else {
            renderAttributes(page(
                'attributes',
                'Характеристики',
                'Это определения характеристик системы, ' +
                'а не значения персонажа.'
            ));

            renderDerived(page(
                'derived',
                'Вычисляемые показатели',
                'Порядок значений важен для вычитания и деления. ' +
                'Проверка допустимости формул выполняется сервером.'
            ));

            renderPreview(page(
                'preview',
                'Проверка на примере персонажа',
                'Проверьте результат, затем сохраните систему и черновик.'
            ));
        }

        showPage(activePage);
        sync();
    }

    function integer(value, title, min, max) {
        const number = Number(value);

        if (
            value === null ||
            String(value).trim() === '' ||
            !Number.isSafeInteger(number) ||
            (min !== undefined && number < min) ||
            (max !== undefined && number > max)
        ) {
            throw new Error(
                `${title}: укажите целое число в допустимом диапазоне.`
            );
        }

        return number;
    }

    function validateControls(includeSamples = false) {
        for (const input of body.querySelectorAll('input, select')) {
            if (
                !includeSamples &&
                input.dataset.sample === 'true'
            ) {
                continue;
            }

            if (!input.checkValidity()) {
                onInvalid(input);
                input.reportValidity();
                throw new Error('Проверьте выделенное поле.');
            }
        }
    }

    function validateFormulaTree(formula, code, title, scope = 'derived') {
        const allowed = new Set(
            sources(code, scope)
                .map(([value]) => value)
                .filter((value) => !value.startsWith('#'))
        );

        const operations = new Set(
            OPERATIONS.map(([value]) => value)
        );

        const dependencies = new Set();
        const stack = [{ value: formula, depth: 1 }];
        let nodes = 0;

        while (stack.length) {
            const { value, depth } = stack.pop();
            nodes += 1;

            if (nodes > FORMULA_MAX_NODES) {
                throw new Error(
                    `${title}: формула слишком велика. ` +
                    'Упростите её или вынесите часть в другой показатель.'
                );
            }

            if (typeof value === 'number') {
                if (
                    !Number.isSafeInteger(value) ||
                    Math.abs(value) > FORMULA_VALUE_LIMIT
                ) {
                    throw new Error(
                        `${title}: константа должна быть целым числом ` +
                        'в допустимом диапазоне.'
                    );
                }

                continue;
            }

            if (typeof value === 'string') {
                if (!allowed.has(value)) {
                    throw new Error(
                        `${title}: выберите доступный источник значения.`
                    );
                }

                if (value.startsWith('stat.')) {
                    dependencies.add(value.slice(5));
                }

                continue;
            }

            if (
                !isFormula(value) ||
                !operations.has(value.operation)
            ) {
                throw new Error(
                    `${title}: проверьте математическое действие ` +
                    'и его значения.'
                );
            }

            if (depth > FORMULA_MAX_DEPTH) {
                throw new Error(
                    `${title}: слишком большая глубина ` +
                    'вложенных вычислений.'
                );
            }

            const count = value.arguments.length;

            if (count < 1 || count > FORMULA_MAX_ARGUMENTS) {
                throw new Error(
                    `${title}: недопустимое количество значений в действии.`
                );
            }

            if (
                BINARY_OPERATIONS.has(value.operation) &&
                count !== 2
            ) {
                throw new Error(
                    `${title}: для вычитания или деления ` +
                    'нужны ровно два значения.'
                );
            }

            if (
                (value.operation === 'floor_div' ||
                    value.operation === 'ceil_div') &&
                value.arguments[1] === 0
            ) {
                throw new Error(`${title}: нельзя делить на ноль.`);
            }

            for (const argument of value.arguments) {
                stack.push({
                    value: argument,
                    depth: depth + 1
                });
            }
        }

        return dependencies;
    }

    function validateDependencyGraph(dependencies, definitions) {
        const remaining = new Map(
            [...dependencies].map(([code, required]) => [
                code,
                new Set(required)
            ])
        );

        while (remaining.size) {
            const ready = [...remaining]
                .filter(([, required]) => required.size === 0)
                .map(([code]) => code);

            if (!ready.length) {
                const names = [...remaining.keys()]
                    .map((code) => definitions[code].label)
                    .join(', ');

                throw new Error(
                    'Обнаружена циклическая зависимость показателей: ' +
                    names + '. Проверьте их ссылки друг на друга.'
                );
            }

            for (const code of ready) {
                remaining.delete(code);
            }

            for (const required of remaining.values()) {
                for (const code of ready) {
                    required.delete(code);
                }
            }
        }
    }

    function collect() {
        if (!profile) {
            throw new Error(
                'Выберите и примените основу на странице «Основа».'
            );
        }

        validateControls();
        const rules = clone(profile);

        rules.modifier_offset = integer(
            rules.modifier_offset,
            'Вычитаемое число',
            -1000,
            1000
        );

        rules.modifier_divisor = integer(
            rules.modifier_divisor,
            'Делитель',
            1,
            1000
        );

        rules.modifier_formula ??= null;

        validateModifierFormula(
            rules.modifier_formula,
            'Общая формула модификатора'
        );

        for (const item of Object.values(
            rules.calculations.attributes
        )) {
            item.label = item.label.trim();

            if (!item.label) {
                throw new Error('Укажите название характеристики.');
            }

            item.min_value = integer(
                item.min_value,
                'Минимум',
                -1000,
                1000
            );

            item.max_value = integer(
                item.max_value,
                'Максимум',
                -1000,
                1000
            );

            if (item.min_value > item.max_value) {
                    throw new Error(
                        `${item.label}: минимум больше максимума.`
                    );
                }

                item.modifier_formula ??= null;

                validateModifierFormula(
                    item.modifier_formula,
                    `Модификатор «${item.label}»`
                );
        }

        const dependencies = new Map();

        for (const [code, item] of Object.entries(
            rules.calculations.derived
        )) {
            item.label = item.label.trim();

            if (!item.label) {
                throw new Error('Укажите название показателя.');
            }

            if (!isFormula(item.formula)) {
                throw new Error(
                    `${item.label}: не задана формула показателя.`
                );
            }

            dependencies.set(
                code,
                validateFormulaTree(item.formula, code, item.label)
            );
        }

        validateDependencyGraph(
            dependencies,
            rules.calculations.derived
        );

        rules.attribute_codes = Object.keys(
            rules.calculations.attributes
        );

        return rules;
    }

    function appendCalculationSteps(steps, rules) {
        if (!Array.isArray(steps)) return;

        const list = element('ol');

        for (const step of steps) {
            if (typeof step.code !== 'string') continue;

            const [reference, ...path] = step.code.split('/');
            let name;

            if (reference.startsWith('modifier.')) {
                const code = reference.slice('modifier.'.length);
                const definition = rules.calculations.attributes[code];

                if (!definition) continue;

                name = `Модификатор «${definition.label}»`;
            } else if (reference.startsWith('stat.')) {
                const code = reference.slice('stat.'.length);
                const definition = rules.calculations.derived[code];

                if (!definition) continue;

                name = definition.label;
            } else {
                continue;
            }

            const location = path.length
                ? ' — вложенное действие ' +
                    path.map((part) => Number(part) + 1).join('.')
                : ' — итог';

            const operation = step.operation === 'identity'
                ? 'Использовать введённое значение'
                : OPERATIONS.find(
                    ([value]) => value === step.operation
                )?.[1] || 'Вычисление';

            list.append(element(
                'li',
                `${name}${location}: ${operation}. ` +
                    `Значения: ${step.resolved_arguments.join(', ')}. ` +
                    `Результат: ${step.value}.`
            ));
        }

        if (!list.children.length) return;

        const explanation = details('Как получен результат');

        explanation.append(list);
        result.append(explanation);
    }

    async function preview() {
        if (busy || parentBusy) return;

        try {
            const rules = collect();
            validateControls(true);

            const attributes = Object.fromEntries(
                Object.entries(rules.calculations.attributes)
                    .map(([code, item]) => [
                        code,
                        integer(
                            samples[code],
                            item.label,
                            item.min_value,
                            item.max_value
                        )
                    ])
            );

            const level = integer(
                sampleLevel,
                'Уровень',
                1,
                rules.max_level
            );

            busy = true;
            onBusy(true);
            sync();
            clearResult();
            message.textContent = 'Проверка расчёта…';

            const data = await request(
                '/admin/game-systems/rules/attributes/preview',
                'POST',
                { rules, level, attributes },
                { readOnly: true }
            );

            if (!data?.modifiers || !data?.derived) {
                throw new Error(
                    'Ответ предпросмотра имеет неожиданный формат.'
                );
            }

            result.append(element('h3', 'Результат'));

            for (const [title, values, definitions] of [
                [
                    'Модификаторы',
                    data.modifiers,
                    rules.calculations.attributes
                ],
                [
                    'Показатели',
                    data.derived,
                    rules.calculations.derived
                ]
            ]) {
                result.append(element('h4', title));
                const list = element('dl');

                for (const [code, value] of Object.entries(values)) {
                    list.append(
                        element(
                            'dt',
                            definitions[code]?.label || code
                        ),
                        element('dd', String(value))
                    );
                }

                result.append(list);
            }

            appendCalculationSteps(data.steps, rules);
            result.hidden = false;

            message.textContent =
                'Расчёт выполнен. Пример персонажа ' +
                'и правила ещё не сохранены.';
        } catch (error) {
            message.textContent =
                error.message || 'Не удалось проверить расчёт.';
        } finally {
            busy = false;
            onBusy(false);
            sync();
        }
    }

    async function load() {
        if (busy) return;

        busy = true;
        sync();

        try {
            let loaded = null;
            let nextEngineVersion = null;
            let nextOverrides = {};

            if (systemId) {
                const state = await request(
                    `/admin/game-systems/${encodeURIComponent(systemId)}` +
                    '/rules/draft'
                );

                if (!state || !own(state, 'draft')) {
                    throw new Error(
                        'Не удалось проверить состояние черновика.'
                    );
                }

                loaded = state.draft;

                if (loaded && (
                    loaded.system_id !== systemId ||
                    !Number.isInteger(loaded.revision) ||
                    loaded.revision < 1 ||
                    !loaded.rules
                )) {
                    throw new Error(
                        'Сервер вернул некорректный черновик.'
                    );
                }

                if (loaded?.engine_version_id != null) {
                    const origin = await request(
                        `/admin/game-systems/${encodeURIComponent(systemId)}` +
                        '/editor/engine'
                    );

                    if (
                        origin?.draft_revision !== loaded.revision ||
                        origin.engine_version?.id !==
                            loaded.engine_version_id
                    ) {
                        throw new Error(
                            'Черновик изменился во время загрузки. ' +
                            'Загрузите страницу заново, чтобы ' +
                            'не смешивать разные ревизии.'
                        );
                    }

                    nextEngineVersion = origin.engine_version;

                    checkEngineVersion(
                        nextEngineVersion,
                        nextEngineVersion.engine_id,
                        loaded.engine_version_id
                    );

                    nextOverrides = readEngineOverrides(
                        loaded,
                        nextEngineVersion
                    );
                } else if (loaded?.rules_overrides != null) {
                    throw new Error(
                        'В черновике есть переопределения ' +
                        'без публикации движка.'
                    );
                }
            }

            let nextPresets = [];

            if (!loaded) {
                nextPresets = await request(
                    '/admin/game-systems/rules/calculation-presets'
                );

                if (
                    !Array.isArray(nextPresets) ||
                    !nextPresets.length
                ) {
                    throw new Error(
                        'Не удалось загрузить основы правил.'
                    );
                }
            }

            const nextProfile = loaded
                ? upgrade(loaded.rules)
                : null;

            profile = nextProfile;
            revision = loaded?.revision ?? null;
            dirty = loaded?.rules.schema_version === 1;

            engineVersion = nextEngineVersion
                ? clone(nextEngineVersion)
                : null;
            explicitOverrides = nextOverrides;

            presets = nextPresets;
            selectedPreset = '';
            sampleLevel = '1';
            samples = {};

            availableEngines = [];
            availableVersions = [];
            selectedEngineId = '';
            selectedVersionId = '';
            enginesLoaded = false;

            renderBasis();
            render();

            message.textContent = loaded
                ? `Черновик загружен. Ревизия: ${revision}.`
                : 'Выберите основу. Создание на сервере ' +
                    'ещё не выполнялось.';
        } finally {
            busy = false;
            sync();
        }
    }

    function collectSubmission() {
        const rules = collect();

        if (!engineVersion) {
            return { rules };
        }

        if (
            engineVersion.rules_engine_version !==
            getExecutorVersion()
        ) {
            throw new Error(
                'Версия исполнителя системы не соответствует основе.'
            );
        }

        return {
            engine_id: engineVersion.engine_id,
            engine_version_id: engineVersion.id,
            rules_overrides: collectEngineOverrides(
                engineVersion.rules_json,
                rules,
                explicitOverrides
            )
        };
    }

    function acceptSaved(draft) {
        if (
            !draft?.rules ||
            !Number.isInteger(draft.revision) ||
            draft.revision < 1 ||
            (systemId && draft.system_id !== systemId)
        ) {
            throw new Error(
                'Ответ сохранения черновика не удалось проверить.'
            );
        }

        const nextProfile = upgrade(draft.rules);
        let nextOverrides = {};

        if (engineVersion) {
            nextOverrides = readEngineOverrides(
                draft,
                engineVersion
            );
        } else if (
            draft.engine_version_id != null ||
            draft.rules_overrides != null
        ) {
            throw new Error(
                'Сервер вернул неожиданную связь с движком. ' +
                'Проверьте сохранённые данные перед повтором.'
            );
        }

        profile = nextProfile;
        revision = draft.revision;
        explicitOverrides = nextOverrides;
        dirty = false;

        renderBasis();
        render();

        message.textContent =
            `Сохранён черновик, ревизия ${revision}. ` +
            'Публикация не выполнялась.';
    }

    function acceptEngineDraft(draft) {
        if (
            !standaloneOnly ||
            systemId ||
            typeof draft?.engine_id !== 'string' ||
            !draft.engine_id ||
            draft.rules_engine_version !== getExecutorVersion() ||
            draft.rules_json?.schema_version !== 2
        ) {
            throw new Error(
                'Черновик движка не соответствует режиму редактора.'
            );
        }

        acceptSaved({
            rules: draft.rules_json,
            revision: draft.revision,
            engine_version_id: null,
            rules_overrides: null
        });
    }

    return {
        load,
        collect,
        collectSubmission,
        acceptSaved,
        acceptEngineDraft,
        showPage,
        getRevision: () => revision,
        hasUnsaved: () => dirty,
        isBusy: () => busy,
        setParentBusy(value) {
            parentBusy = value;
            sync();
        }
    };
}