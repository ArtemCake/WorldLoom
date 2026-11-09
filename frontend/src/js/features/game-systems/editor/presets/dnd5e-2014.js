// frontend/src/js/features/game-systems/editor/presets/dnd5e-2014.js

/**
 * Базовые числовые расчёты и определения ресурсов D&D 5e 2014.
 *
 * Совместимо с RulesProfile schema_version: 4.
 *
 * Это часть пакета правил, а не полная реализация:
 * - не выполняет броски;
 * - не расходует ресурсы персонажа;
 * - не назначает владения по классу;
 * - не применяет состояния и ситуативные эффекты;
 * - не проверяет законность выбора компетентности;
 * - не создаёт персонажа по процедуре правил;
 * - не вычисляет максимум хитов по классам и истории уровней;
 * - не проверяет условия получения преимуществ отдыха.
 */

import {FORMULA_VALUE_LIMIT} from '../shared/formula-contract.js';


const ABILITIES = [
	['strength', 'Сила'],
	['dexterity', 'Ловкость'],
	['constitution', 'Телосложение'],
	['intelligence', 'Интеллект'],
	['wisdom', 'Мудрость'],
	['charisma', 'Харизма']
];

const SKILLS = [
	['acrobatics', 'Акробатика', 'dexterity'],
	['animal_handling', 'Уход за животными', 'wisdom'],
	['arcana', 'Магия', 'intelligence'],
	['athletics', 'Атлетика', 'strength'],
	['deception', 'Обман', 'charisma'],
	['history', 'История', 'intelligence'],
	['insight', 'Проницательность', 'wisdom'],
	['intimidation', 'Запугивание', 'charisma'],
	['investigation', 'Расследование', 'intelligence'],
	['medicine', 'Медицина', 'wisdom'],
	['nature', 'Природа', 'intelligence'],
	['perception', 'Внимательность', 'wisdom'],
	['performance', 'Выступление', 'charisma'],
	['persuasion', 'Убеждение', 'charisma'],
	['religion', 'Религия', 'intelligence'],
	['sleight_of_hand', 'Ловкость рук', 'dexterity'],
	['stealth', 'Скрытность', 'dexterity'],
	['survival', 'Выживание', 'wisdom']
];

function addHitPoints(profile) {
	/*
	 * Максимум вводится вручную до подключения классов,
	 * истории повышения уровней и модифицирующих эффектов.
	 *
	 * 1 — техническое начальное заполнение редактора.
	 * Это не результат создания персонажа по правилам.
	 *
	 * FORMULA_VALUE_LIMIT — предел числового контракта,
	 * а не игровое ограничение максимума хитов.
	 */
	addAttribute(profile, 'hit_points_max', 'Максимум хитов', 1, FORMULA_VALUE_LIMIT, 1);

	/*
	 * Определение ресурса не содержит текущих хитов персонажа.
	 * initial применяется только при создании состояния ресурса.
	 *
	 * long_rest означает уже подтверждённый отдых.
	 * Проверка условий отдыха относится к отдельной процедуре.
	 */
	profile.resources.hit_points = {
		label: 'Хиты',
		maximum: attributeReference('hit_points_max'),
		initial: 'full',
		recovery: {
			long_rest: 'full'
		}
	};
}

function operation(name, ...args) {
	return {
		operation: name,
		arguments: args
	};
}

function attributeReference(code) {
	return `attribute.${code}`;
}

function statReference(code) {
	return `stat.${code}`;
}

function addAttribute(profile, code, label, minimum, maximum, initial) {
	profile.calculations.attributes[code] = {
		label,
		min_value: minimum,
		max_value: maximum
	};

	profile.initial_attributes[code] = initial;
}

function addChoiceAttribute(profile, code, label, choices, initial) {
	const values = choices.map((item) => item.value);

	profile.calculations.attributes[code] = {
		label,
		field_type: 'choice',
		choices: choices.map((item) => ({ ...item })),
		min_value: Math.min(...values),
		max_value: Math.max(...values)
	};

	profile.initial_attributes[code] = initial;
}

function addDerived(profile, code, label, formula) {
	profile.calculations.derived[code] = {
		label,
		formula
	};
}

export function createDnd5e2014NumericProfile() {
	const profile = {
		schema_version: 4,
		calculations: {
			attributes: {},
			derived: {}
		},
		initial_attributes: {},
		resources: {}
	};

	/*
	 * 10 — нейтральное начальное заполнение редактора.
	 * Это не стандартный массив и не покупка характеристик.
	 *
	 * Диапазон 0–30 допускает хранение числового состояния,
	 * в том числе после эффектов.
	 *
	 * Ограничения создания персонажа, обычное повышение
	 * до 20 и последствия снижения до 0 требуют отдельных
	 * контекстных правил. Этот диапазон их не заменяет.
	 */
	for (const [code, label] of ABILITIES) {
		addAttribute(
			profile,
			code,
			label,
			0,
			30,
			10
		);

		addDerived(
			profile,
			`${code}_modifier`,
			`Модификатор: ${label}`,
			operation(
				'floor_div',
				operation(
					'subtract',
					attributeReference(code),
					10
				),
				2
			)
		);
	}

	/*
	 * Общий уровень персонажа.
	 * При мультиклассировании он должен вычисляться
	 * из уровней классов, а не редактироваться независимо.
	 *
	 * Здесь пока используется как исходный показатель.
	 */
	addAttribute(
		profile,
		'level',
		'Общий уровень персонажа',
		1,
		20,
		1
	);

	addDerived(
		profile,
		'proficiency_bonus',
		'Бонус мастерства',
		operation(
			'sum',
			2,
			operation(
				'floor_div',
				operation(
					'subtract',
					attributeReference('level'),
					1
				),
				4
			)
		)
	);

	/*
	 * Спасброски.
	 * 0 — нет владения, 1 — есть владение.
	 *
	 * Выбор владений по классу и особенности,
	 * изменяющие спасброски, подключаются отдельно.
	 */
	for (const [abilityCode, label] of ABILITIES) {
		const proficiencyCode = `save_${abilityCode}_trained`;

		addChoiceAttribute(
			profile,
			proficiencyCode,
			`Владение спасброском: ${label}`,
			[
				{ value: 0, label: 'Нет владения' },
				{ value: 1, label: 'Владение' }
			],
			0
		);

		addDerived(
			profile,
			`save_${abilityCode}`,
			`Спасбросок: ${label}`,
			operation(
				'sum',
				statReference(`${abilityCode}_modifier`),
				operation(
					'multiply',
					attributeReference(proficiencyCode),
					statReference('proficiency_bonus')
				)
			)
		);
	}

	/*
	 * Навыки.
	 * 0 — без владения;
	 * 1 — владение;
	 * 2 — компетентность: удвоенный бонус мастерства.
	 *
	 * Это множитель, а не два складываемых владения.
	 * Особенности с половиной бонуса мастерства
	 * и альтернативной характеристикой здесь не моделируются.
	 */
	for (const [skillCode, label, abilityCode] of SKILLS) {
		const rankCode = `skill_${skillCode}_rank`;
		const totalCode = `skill_${skillCode}`;

		addChoiceAttribute(
			profile,
			rankCode,
			`Владение: ${label}`,
			[
				{ value: 0, label: 'Нет владения' },
				{ value: 1, label: 'Владение' },
				{ value: 2, label: 'Компетентность' }
			],
			0
		);

		addDerived(
			profile,
			totalCode,
			`Бонус: ${label}`,
			operation(
				'sum',
				statReference(`${abilityCode}_modifier`),
				operation(
					'multiply',
					attributeReference(rankCode),
					statReference('proficiency_bonus')
				)
			)
		);

		/*
		 * Базовое пассивное значение.
		 *
		 * Преимущество, помеха и прочие применимые эффекты
		 * должны учитываться при разрешении конкретной проверки.
		 */
		addDerived(
			profile,
			`passive_${skillCode}_base`,
			`Пассивная проверка без эффектов: ${label}`,
			operation(
				'sum',
				10,
				statReference(totalCode)
			)
		);
	}

	addDerived(
		profile,
		'initiative_base',
		'Инициатива без дополнительных бонусов',
		operation(
			'sum',
			statReference('dexterity_modifier')
		)
	);

	/*
	 * Только обычный вариант без доспехов и щита.
	 * Не является окончательным КД персонажа.
	 *
	 * Доспехи, щит, классовые варианты защиты
	 * и эффекты должны обрабатываться отдельно.
	 */
	addDerived(
		profile,
		'armor_class_unarmored_base',
		'Базовый КД без доспехов и щита',
		operation(
			'sum',
			10,
			statReference('dexterity_modifier')
		)
	);
    addHitPoints(profile);
    addExtendedChecks(profile);

    return assignDnd2014Sections(profile);
}

function addFeatureSwitch(profile, code, label) {
    const choices = [
        {value: 0, label: 'Не применяется'},
        {value: 1, label: 'Применяется'}
    ];

    addChoiceAttribute(profile, code, label, choices, 0);
}

function halfCheckProficiency(abilityCode) {
    const jack = operation('multiply', attributeReference('jack_of_all_trades'), statReference('half_proficiency_floor'));
    const physical = ['strength', 'dexterity', 'constitution'].includes(abilityCode);

    if (!physical) return jack;

    const athlete = operation('multiply', attributeReference('remarkable_athlete'), statReference('half_proficiency_ceil'));

    // Несколько способов добавить часть бонуса мастерства не складываются.
    return operation('max', jack, athlete);
}

function untrainedCheckProficiency(abilityCode, rankCode) {
    const trained = operation('min', 1, attributeReference(rankCode));
    const untrained = operation('subtract', 1, trained);

    return operation('multiply', untrained, halfCheckProficiency(abilityCode));
}

function addCheckFeatures(profile) {
    addFeatureSwitch(profile, 'jack_of_all_trades', 'Мастер на все руки: особенность получена');
    addFeatureSwitch(profile, 'remarkable_athlete', 'Выдающийся атлет: особенность получена');

    profile.calculations.attributes.jack_of_all_trades.description =
        'Числовое применение полученной особенности. Требования класса и уровня проверяются отдельно.';

    profile.calculations.attributes.remarkable_athlete.description =
        'Бонус к проверкам Силы, Ловкости и Телосложения без владения. Дополнительная дальность прыжка сюда не входит.';

    const proficiency = statReference('proficiency_bonus');

    addDerived(profile, 'half_proficiency_floor', 'Половина бонуса мастерства вниз', operation('floor_div', proficiency, 2));
    addDerived(profile, 'half_proficiency_ceil', 'Половина бонуса мастерства вверх', operation('ceil_div', proficiency, 2));

    for (const [abilityCode, label] of ABILITIES) {
        const code = `check_${abilityCode}_untrained_base`;
        const modifier = statReference(`${abilityCode}_modifier`);
        const formula = operation('sum', modifier, halfCheckProficiency(abilityCode));

        addDerived(profile, code, `Проверка без владения: ${label}`, formula);

        profile.calculations.derived[code].description =
            'Проверка без владения с учётом включённых особенностей, без прочих ситуативных модификаторов.';
    }
}

function addSavingThrowTotals(profile) {
    for (const [abilityCode, label] of ABILITIES) {
        const bonusCode = `save_${abilityCode}_bonus`;
        const totalCode = `save_${abilityCode}_total`;

        addAttribute(profile, bonusCode, `Дополнительный бонус спасброска: ${label}`, -1000, 1000, 0);

        const formula = operation('sum', statReference(`save_${abilityCode}`), attributeReference(bonusCode));

        addDerived(profile, totalCode, `Итоговый бонус спасброска: ${label}`, formula);

        profile.calculations.attributes[bonusCode].description =
            'Только применимый числовой модификатор. Дополнительные кости и преимущество этим полем не моделируются.';
    }
}

function addSkillTotals(profile) {
    const passiveModes = [
        {value: -1, label: 'Помеха'},
        {value: 0, label: 'Обычная проверка'},
        {value: 1, label: 'Преимущество'}
    ];

    for (const [skillCode, label, abilityCode] of SKILLS) {
        const bonusCode = `skill_${skillCode}_bonus`;
        const modeCode = `passive_${skillCode}_mode`;
        const totalCode = `skill_${skillCode}_total`;
        const passiveCode = `passive_${skillCode}_total`;
        const rankCode = `skill_${skillCode}_rank`;

        addAttribute(profile, bonusCode, `Дополнительный бонус навыка: ${label}`, -1000, 1000, 0);
        addChoiceAttribute(profile, modeCode, `Условия пассивной проверки: ${label}`, passiveModes, 0);

        const base = statReference(`skill_${skillCode}`);
        const partialProficiency = untrainedCheckProficiency(abilityCode, rankCode);
        const bonus = attributeReference(bonusCode);
        const total = operation('sum', base, partialProficiency, bonus);

        addDerived(profile, totalCode, `Итоговый бонус навыка: ${label}`, total);

        const passiveAdjustment = operation('multiply', 5, attributeReference(modeCode));
        const passive = operation('sum', 10, statReference(totalCode), passiveAdjustment);

        addDerived(profile, passiveCode, `Итоговая пассивная проверка: ${label}`, passive);

        profile.calculations.attributes[modeCode].description =
            'Итоговые условия конкретной проверки. При одновременных преимуществе и помехе выберите обычную проверку.';

        profile.calculations.attributes[bonusCode].description =
            'Применимый постоянный числовой модификатор. Не заменяет дополнительные кости и ситуативные эффекты.';
    }
}

function addInitiativeTotal(profile) {
    const choices = [
        {value: 0, label: 'Нет владения'},
        {value: 1, label: 'Бонус мастерства применяется'}
    ];

    addChoiceAttribute(profile, 'initiative_trained', 'Применение бонуса мастерства к инициативе', choices, 0);
    addAttribute(profile, 'initiative_bonus', 'Дополнительный бонус инициативы', -1000, 1000, 0);

    profile.calculations.attributes.initiative_trained.description =
        'Включается только при наличии правила, добавляющего бонус мастерства к инициативе.';

    const trained = operation('multiply', attributeReference('initiative_trained'), statReference('proficiency_bonus'));
    const untrained = untrainedCheckProficiency('dexterity', 'initiative_trained');
    const formula = operation('sum', statReference('initiative_base'), trained, untrained, attributeReference('initiative_bonus'));

    addDerived(profile, 'initiative_total', 'Итоговый бонус инициативы', formula);
}

function addExtendedChecks(profile) {
    addCheckFeatures(profile);
    addSavingThrowTotals(profile);
    addSkillTotals(profile);
    addInitiativeTotal(profile);
}

export function assignDnd2014Sections(profile) {
    const attributes = profile.calculations?.attributes ?? {};
    const derived = profile.calculations?.derived ?? {};
    const resources = profile.resources ?? {};

    function assign(collection, code, section) {
        const definition = collection[code];

        if (definition && !definition.section) {
            definition.section = section;
        }
    }

    for (const [abilityCode] of ABILITIES) {
        assign(attributes, abilityCode, 'Характеристики');
        assign(derived, `${abilityCode}_modifier`, 'Характеристики');

        assign(attributes, `save_${abilityCode}_trained`, 'Спасброски');
        assign(attributes, `save_${abilityCode}_bonus`, 'Спасброски');
        assign(derived, `save_${abilityCode}`, 'Спасброски');
        assign(derived, `save_${abilityCode}_total`, 'Спасброски');

        assign(derived, `check_${abilityCode}_untrained_base`, 'Проверки характеристик');
    }

    for (const [skillCode] of SKILLS) {
        assign(attributes, `skill_${skillCode}_rank`, 'Навыки');
        assign(attributes, `skill_${skillCode}_bonus`, 'Навыки');
        assign(derived, `skill_${skillCode}`, 'Навыки');
        assign(derived, `skill_${skillCode}_total`, 'Навыки');

        assign(attributes, `passive_${skillCode}_mode`, 'Пассивные проверки');
        assign(derived, `passive_${skillCode}_base`, 'Пассивные проверки');
        assign(derived, `passive_${skillCode}_total`, 'Пассивные проверки');
    }

    assign(attributes, 'level', 'Уровень и мастерство');
    assign(derived, 'proficiency_bonus', 'Уровень и мастерство');
    assign(derived, 'half_proficiency_floor', 'Уровень и мастерство');
    assign(derived, 'half_proficiency_ceil', 'Уровень и мастерство');

    assign(attributes, 'jack_of_all_trades', 'Особенности');
    assign(attributes, 'remarkable_athlete', 'Особенности');

    assign(attributes, 'initiative_trained', 'Инициатива');
    assign(attributes, 'initiative_bonus', 'Инициатива');
    assign(derived, 'initiative_base', 'Инициатива');
    assign(derived, 'initiative_total', 'Инициатива');

    assign(derived, 'armor_class_unarmored_base', 'Защита');
    assign(attributes, 'hit_points_max', 'Хиты и ресурсы');
    assign(resources, 'hit_points', 'Хиты и ресурсы');

    return profile;
}