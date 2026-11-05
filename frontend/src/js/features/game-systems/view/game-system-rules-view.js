// frontend/src/js/features/game-systems/view/game-system-rules-view.js

const ATTRIBUTE_LABELS = {
    str: 'Сила',
    dex: 'Ловкость',
    con: 'Телосложение',
    int: 'Интеллект',
    wis: 'Мудрость',
    cha: 'Харизма'
};

const CHECK_LABELS = {
    ability: 'Проверка характеристики',
    save: 'Спасбросок',
    attack: 'Атака'
};

const NATURAL_LABELS = {
    ignore: 'Не меняет результат автоматически',
    success: 'Успех',
    critical_success: 'Критический успех',
    improve: 'Повышение результата на одну степень',
    failure: 'Провал',
    critical_failure: 'Критический провал',
    worsen: 'Понижение результата на одну степень'
};

const BASIS_LABELS = {
    dnd5e_2014_srd51: 'D&D 5e — SRD 5.1',
    pf2e_remaster: 'Pathfinder 2e Remaster'
};

function element(tag, text, className) {
    const node = document.createElement(tag);

    if (text !== undefined) node.textContent = String(text);
    if (className) node.className = className;

    return node;
}

function note(text) {
    return element('p', text, 'system-view__note');
}

function section(title) {
    const node = element('section', undefined, 'system-view__panel');
    node.append(element('h3', title));
    return node;
}

function card(title) {
    const node = element('article', undefined, 'system-view__card');
    node.append(element('h4', title));
    return node;
}

function attributeName(rules, code) {
    const label = rules.calculations?.attributes?.[code]?.label;

    if (typeof label === 'string' && label.trim()) {
        return label;
    }

    if (ATTRIBUTE_LABELS[code]) return ATTRIBUTE_LABELS[code];

    const index = rules.attribute_codes.indexOf(code);

    return index >= 0
        ? `Характеристика ${index + 1}`
        : 'Неизвестная характеристика';
}

function sourceName(reference, rules, localName) {
    if (reference === 'level') return 'Уровень персонажа';

    if (reference === 'attribute.value' && localName !== null) {
        return localName;
    }

    const [namespace, code] = reference.split('.');

    if (
        (namespace === 'attribute' || namespace === 'modifier') &&
        rules.attribute_codes.includes(code)
    ) {
        const name = attributeName(rules, code);

        return namespace === 'attribute'
            ? `Значение «${name}»`
            : `Модификатор «${name}»`;
    }

    if (namespace === 'stat') {
        const label = rules.calculations?.derived?.[code]?.label;

        if (typeof label === 'string' && label.trim()) {
            return `Показатель «${label}»`;
        }
    }

    throw new Error('В формуле обнаружен неизвестный источник.');
}

function formulaText(value, rules, localName = null, depth = 0) {
    if (Number.isSafeInteger(value)) {
        return value < 0 ? `(${value})` : String(value);
    }

    if (typeof value === 'string') {
        return sourceName(value, rules, localName);
    }

    if (
        depth >= 8 ||
        !value ||
        typeof value !== 'object' ||
        !Array.isArray(value.arguments) ||
        value.arguments.length === 0 ||
        value.arguments.length > 16
    ) {
        throw new Error('Не удалось отобразить структуру формулы.');
    }

    const args = value.arguments.map((argument) =>
        formulaText(argument, rules, localName, depth + 1)
    );

    if (
        ['subtract', 'floor_div', 'ceil_div'].includes(value.operation) &&
        args.length !== 2
    ) {
        throw new Error('В формуле неверное количество аргументов.');
    }

    switch (value.operation) {
        case 'sum':
            return `(${args.join(' + ')})`;

        case 'subtract':
            return `(${args[0]} − ${args[1]})`;

        case 'multiply':
            return `(${args.join(' × ')})`;

        case 'floor_div':
            return `Округлить вниз (${args[0]} / ${args[1]})`;

        case 'ceil_div':
            return `Округлить вверх (${args[0]} / ${args[1]})`;

        case 'min':
            return `Наименьшее из (${args.join('; ')})`;

        case 'max':
            return `Наибольшее из (${args.join('; ')})`;

        default:
            throw new Error('В формуле используется неизвестная операция.');
    }
}

function standardFormula(rules) {
    return {
        operation: 'floor_div',
        arguments: [
            {
                operation: 'subtract',
                arguments: ['attribute.value', rules.modifier_offset]
            },
            rules.modifier_divisor
        ]
    };
}

function appendFormula(parent, formula, rules, localName = null) {
    parent.append(element(
        'p',
        formulaText(formula, rules, localName),
        'system-view__formula'
    ));
}

function appendDefinition(list, title, value) {
    list.append(
        element('dt', title),
        element('dd', value)
    );
}

function renderSummary(rules) {
    const panel = section('Основные настройки');
    const list = element('dl', undefined, 'system-view__facts');

    appendDefinition(
        list,
        'Основа настроек',
        BASIS_LABELS[rules.base_ruleset] || 'Другая основа'
    );

    appendDefinition(
        list,
        'Уровни персонажа',
        `От 1 до ${rules.max_level}`
    );

    appendDefinition(
        list,
        'Характеристики',
        rules.attribute_mode === 'modifier'
            ? 'Модификатор вводится напрямую'
            : 'Модификатор вычисляется из значения'
    );

    panel.append(
        list,
        note(
            'Основа обозначает происхождение настроек расчёта, ' +
            'а не наличие полного справочника выбранной ролевой системы.'
        )
    );

    return panel;
}

function renderAttributes(rules) {
    const panel = section('Характеристики');

    if (rules.attribute_mode === 'score') {
        panel.append(element('h4', 'Общее правило модификаторов'));

        appendFormula(
            panel,
            rules.modifier_formula ?? standardFormula(rules),
            rules,
            'Значение характеристики'
        );

        panel.append(note(
            'Применяется, если для характеристики не задана своя формула.'
        ));
    } else {
        panel.append(note(
            'Введённое значение уже является модификатором. ' +
            'Сохранённые формулы в этом режиме не применяются.'
        ));
    }

    const grid = element('div', undefined, 'system-view__grid');

    for (const code of rules.attribute_codes) {
        const name = attributeName(rules, code);
        const definition = rules.calculations?.attributes?.[code];
        const item = card(name);

        if (definition) {
            item.append(note(
                `Допустимые значения: от ${definition.min_value} ` +
                `до ${definition.max_value}.`
            ));
        } else {
            item.append(note(
                'В этой версии правил отдельный диапазон ' +
                'характеристики не задан.'
            ));
        }

        if (rules.attribute_mode === 'modifier') {
            item.append(element(
                'p',
                'Модификатор равен введённому значению.'
            ));
        } else {
            const individual = definition?.modifier_formula != null;

            item.append(note(
                individual
                    ? 'Своя формула — заменяет общее правило.'
                    : 'По общему правилу системы.'
            ));

            const formula = definition?.modifier_formula ??
                rules.modifier_formula ??
                standardFormula(rules);

            appendFormula(
                item,
                formula,
                rules,
                `Значение «${name}»`
            );
        }

        grid.append(item);
    }

    panel.append(grid);

    return panel;
}

function renderDerived(rules) {
    const panel = section('Вычисляемые показатели');
    const entries = Object.entries(rules.calculations?.derived ?? {});

    if (!entries.length) {
        panel.append(note(
            'В этой версии правил вычисляемые показатели не заданы.'
        ));

        return panel;
    }

    const grid = element('div', undefined, 'system-view__grid');

    for (const [, definition] of entries) {
        const item = card(definition.label);
        appendFormula(item, definition.formula, rules);
        grid.append(item);
    }

    panel.append(grid);

    return panel;
}

function table(headers, rows, captionText) {
    const wrapper = element(
        'div',
        undefined,
        'system-view__table-wrap'
    );

    wrapper.tabIndex = 0;
    wrapper.setAttribute('role', 'region');
    wrapper.setAttribute('aria-label', captionText);

    const node = element('table');
    node.append(element('caption', captionText));

    const head = element('thead');
    const headerRow = element('tr');

    for (const title of headers) {
        const cell = element('th', title);
        cell.scope = 'col';
        headerRow.append(cell);
    }

    head.append(headerRow);

    const body = element('tbody');

    for (const values of rows) {
        const row = element('tr');

        for (const value of values) {
            row.append(element('td', value));
        }

        body.append(row);
    }

    node.append(head, body);
    wrapper.append(node);

    return wrapper;
}

function bonusRanges(bonuses) {
    const rows = [];

    for (let start = 0; start < bonuses.length;) {
        let end = start;

        while (
            end + 1 < bonuses.length &&
            bonuses[end + 1] === bonuses[start]
        ) {
            end += 1;
        }

        const levels = start === end
            ? String(start + 1)
            : `${start + 1}–${end + 1}`;

        const value = bonuses[start];

        rows.push([
            levels,
            value > 0 ? `+${value}` : String(value)
        ]);

        start = end + 1;
    }

    return rows;
}

function renderProficiency(rules) {
    const panel = section('Владение');
    const grid = element('div', undefined, 'system-view__grid');

    for (const rank of Object.values(rules.proficiency_ranks)) {
        const item = card(rank.label);

        item.append(note(
            'Применяется: ' +
            rank.contexts.map((kind) => CHECK_LABELS[kind]).join(', ') +
            '.'
        ));

        item.append(table(
            ['Уровни', 'Бонус'],
            bonusRanges(rank.bonuses),
            `Бонусы: ${rank.label}`
        ));

        grid.append(item);
    }

    panel.append(grid);

    return panel;
}

function renderChecks(rules) {
    const panel = section('Броски и результат проверки');
    const checks = rules.checks;

    panel.append(element(
        'p',
        'Итог проверки: d20 + модификатор характеристики + ' +
        'бонус владения + дополнительные бонусы и штрафы.'
    ));

    if (checks.degrees === 'four') {
        panel.append(element(
            'p',
            'Используются четыре степени результата: критический провал, ' +
            'провал, успех и критический успех. ' +
            `Порог критического результата: ${checks.critical_margin}.`
        ));

        panel.append(note(
            'До учёта натурального броска: итог не ниже сложности ' +
            'даёт успех; превышение сложности на порог или больше — ' +
            'критический успех. Отставание на порог или больше — ' +
            'критический провал; остальные результаты ниже сложности — провал.'
        ));
    } else {
        panel.append(element(
            'p',
            'Базовый результат: успех, если итог не ниже сложности; ' +
            'иначе провал. После этого учитывается правило натурального броска.'
        ));
    }

    panel.append(note(
        checks.supports_advantage
            ? 'Преимущество и помеха поддерживаются: выбирается больший ' +
                'или меньший результат двух d20. При одновременном наличии ' +
                'они отменяют друг друга.'
            : 'Механика преимущества и помехи не поддерживается.'
    ));

    const rows = ['ability', 'save', 'attack'].map((kind) => {
        const natural = checks.natural[kind];

        return [
            CHECK_LABELS[kind],
            NATURAL_LABELS[natural.on_20],
            NATURAL_LABELS[natural.on_1]
        ];
    });

    panel.append(table(
        ['Вид проверки', 'Натуральная 20', 'Натуральная 1'],
        rows,
        'Влияние натуральных бросков'
    ));

    return panel;
}

function renderRules(rules) {
    if (
        !rules ||
        !Array.isArray(rules.attribute_codes) ||
        !['score', 'modifier'].includes(rules.attribute_mode) ||
        !rules.checks ||
        !rules.proficiency_ranks
    ) {
        throw new Error('Сервер вернул неподдерживаемую структуру правил.');
    }

    const fragment = document.createDocumentFragment();

    fragment.append(
        renderSummary(rules),
        renderAttributes(rules),
        renderDerived(rules),
        renderProficiency(rules),
        renderChecks(rules)
    );

    return fragment;
}

function publicationDate(value) {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return 'Дата публикации не распознана';
    }

    return new Intl.DateTimeFormat('ru-RU', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: 'UTC'
    }).format(date) + ' UTC';
}

export async function mountRulesView(host, { systemId, canEdit, request }) {
    const container = element('div', undefined, 'system-view');
    const controls = section('Версия правил');

    const status = element('p', '', 'system-view__note');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');

    const body = element('div');

    let selected = canEdit ? 'draft' : 'published';
    let selector = null;
    let generation = 0;

    if (canEdit) {
        const label = element(
            'label',
            undefined,
            'system-view__field'
        );

        label.append(element('span', 'Что показать'));

        selector = element('select');

        for (const [value, title] of [
            ['draft', 'Сохранённый черновик'],
            ['published', 'Последняя опубликованная версия']
        ]) {
            const option = element('option', title);
            option.value = value;
            selector.append(option);
        }

        selector.value = selected;
        label.append(selector);
        controls.append(label);
    } else {
        controls.append(note(
            'Показана последняя опубликованная версия. ' +
            'Неопубликованные изменения сюда не включаются.'
        ));
    }

    controls.append(status);
    container.append(controls, body);
    host.replaceChildren(container);

    async function loadSelected() {
        const current = ++generation;
        const source = selected;

        body.replaceChildren();
        status.textContent = source === 'draft'
            ? 'Загрузка сохранённого черновика…'
            : 'Загрузка опубликованной версии…';

        container.setAttribute('aria-busy', 'true');
        if (selector) selector.disabled = true;

        try {
            const id = encodeURIComponent(systemId);

            const path = source === 'draft'
                ? `/admin/game-systems/${id}/rules/draft`
                : (
                    canEdit
                        ? `/admin/game-systems/${id}/rules/latest`
                        : `/game-systems/items/${id}/rules/latest`
                );

            const data = await request(path);

            if (current !== generation || !container.isConnected) return;

            const key = source === 'draft' ? 'draft' : 'version';

            if (
                !data ||
                typeof data !== 'object' ||
                !Object.prototype.hasOwnProperty.call(data, key)
            ) {
                throw new Error('Ответ с версией правил не удалось прочитать.');
            }

            const snapshot = data[key];

            if (snapshot === null) {
                status.textContent = source === 'draft'
                    ? 'Сохранённого черновика нет.'
                    : 'Правила этой системы ещё не опубликованы.';

                return;
            }

            if (
                !snapshot ||
                snapshot.system_id !== systemId ||
                !snapshot.rules ||
                (
                    source === 'draft'
                        ? !Number.isInteger(snapshot.revision)
                        : !Number.isInteger(snapshot.version_number)
                )
            ) {
                throw new Error('Ответ с версией правил не удалось проверить.');
            }

            // Сначала строим содержимое отдельно.
            // При ошибке не оставляем на странице половину правил.
            const rendered = renderRules(snapshot.rules);

            status.textContent = source === 'draft'
                ? `Черновик · ревизия ${snapshot.revision}. ` +
                    'Это сохранённые, но не опубликованные правила.'
                : `Опубликованная версия №${snapshot.version_number} · ` +
                    `${publicationDate(snapshot.published_at)} · ` +
                    `игровая система снимка: ${snapshot.rules_engine_version}.`;

            body.replaceChildren(rendered);
        } catch (error) {
            if (current !== generation || !container.isConnected) return;

            body.replaceChildren();

            status.textContent =
                'Не удалось загрузить или отобразить выбранные правила. ' +
                (error.message || 'Повторите загрузку страницы.');

            if (error.status === 401) {
                const login = element(
                    'a',
                    'Войти в аккаунт',
                    'btn btn-outline-primary'
                );

                login.href = '/login';
                body.append(login);
            }
        } finally {
            if (current === generation && container.isConnected) {
                container.setAttribute('aria-busy', 'false');
                if (selector) selector.disabled = false;
            }
        }
    }

    selector?.addEventListener('change', () => {
        selected = selector.value;
        void loadSelected();
    });

    await loadSelected();
}