// frontend/src/js/features/game-systems/editor/presets/dnd5e-2014.js

/**
 * Базовые числовые расчёты D&D 5e 2014.
 *
 * Совместимо с RulesProfile schema_version: 3.
 *
 * Это первая часть пакета правил, а не полная реализация:
 * - не выполняет броски;
 * - не расходует ресурсы;
 * - не назначает владения по классу;
 * - не применяет состояния и ситуативные эффекты;
 * - не проверяет законность выбора компетентности;
 * - не создаёт персонажа по процедуре правил.
 */

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
		schema_version: 3,
		calculations: {
			attributes: {},
			derived: {}
		},
		initial_attributes: {}
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

	return profile;
}