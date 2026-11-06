// frontend/src/js/features/game-systems/editor/game-system-engine-origin.js

export const OVERRIDABLE_FIELDS = Object.freeze([
    'calculations',
    'initial_attributes',
    'resources'
]);

const allowed = new Set(OVERRIDABLE_FIELDS);
const own = (value, key) => Object.hasOwn(value, key);
const clone = (value) => JSON.parse(JSON.stringify(value));

function record(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (!record(value)) return value;

    return Object.fromEntries(
        Object.keys(value).sort().map((key) => [key, canonical(value[key])])
    );
}

export function jsonEqual(left, right) {
    return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}

function normalizedRules(raw) {
    if (!record(raw) || ![3, 4].includes(raw.schema_version)) {
        throw new Error('Для связанной системы требуется профиль правил формата 3 или 4.');
    }

    if (!record(raw.calculations)) {
        throw new Error('В правилах отсутствует раздел вычислений.');
    }

    if (!record(raw.calculations.attributes) || !record(raw.calculations.derived)) {
        throw new Error('В правилах отсутствуют коллекции характеристик или формул.');
    }

    if (!record(raw.initial_attributes)) {
        throw new Error('В правилах отсутствуют начальные значения характеристик.');
    }

    const rules = clone(raw);

    if (rules.schema_version === 3 && !own(rules, 'resources')) {
        rules.resources = {};
    }

    if (!record(rules.resources)) {
        throw new Error('Раздел ресурсов должен быть объектом.');
    }

    if (rules.schema_version === 3 && Object.keys(rules.resources).length) {
        throw new Error('Ресурсы поддерживаются начиная с версии профиля 4.');
    }

    return rules;
}

function checkOverrides(overrides) {
    if (!record(overrides)) {
        throw new Error('Переопределения должны быть объектом.');
    }

    for (const key of Object.keys(overrides)) {
        if (!allowed.has(key)) {
            throw new Error(`Поле «${key}» нельзя переопределять.`);
        }
    }
}

export function collectEngineOverrides(baseRules, effectiveRules, explicitOverrides = {}) {
    checkOverrides(explicitOverrides);

    const base = normalizedRules(baseRules);
    const effective = normalizedRules(effectiveRules);
    const keys = new Set([...Object.keys(base), ...Object.keys(effective)]);

    for (const key of keys) {
        if (!allowed.has(key) && !jsonEqual(base[key], effective[key])) {
            throw new Error(`Изменение поля «${key}» требует отдельного перехода версии правил.`);
        }
    }

    const overrides = {};

    for (const key of OVERRIDABLE_FIELDS) {
        const explicitlySet = own(explicitOverrides, key);
        const different = !jsonEqual(base[key], effective[key]);

        if (!explicitlySet && !different) continue;

        if (!own(effective, key)) {
            throw new Error(`В итоговых правилах отсутствует поле «${key}».`);
        }

        // Сервер заменяет раздел целиком, а не объединяет вложенные поля.
        overrides[key] = clone(effective[key]);
    }

    return overrides;
}

export function readEngineOverrides(draft, version) {
    const validVersion = record(version)
    && typeof version.id === 'string' && version.id.length > 0
    && typeof version.engine_id === 'string' && version.engine_id.length > 0;

    if (!validVersion || draft?.engine_version_id !== version.id) {
        throw new Error('Публикация основы не соответствует черновику системы.');
    }

    const overrides = draft.rules_overrides;

    checkOverrides(overrides);

    const base = normalizedRules(version.rules_json);
    const assembled = {...base, ...clone(overrides)};
    const effective = normalizedRules(draft.rules);

    if (!jsonEqual(normalizedRules(assembled), effective)) {
        throw new Error('Правила черновика не совпадают с сохранённой основой и переопределениями.');
    }

    return clone(overrides);
}