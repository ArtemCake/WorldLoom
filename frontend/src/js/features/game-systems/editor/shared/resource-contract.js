// frontend/src/js/features/game-systems/editor/shared/resource-contract.js

import {CODE_PATTERN, FORMULA_VALUE_LIMIT as LIMIT} from './formula-contract.js';
import {normalizeShortLabel} from './short-label.js';

export function isRecord(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function ensure(condition, message) {
	if (!condition) throw new Error(message);
}

function nonnegative(value) {
	return Number.isSafeInteger(value) && value >= 0 && value <= LIMIT;
}

function knownFields(value, fields, title) {
	ensure(isRecord(value), `${title}: ожидается объект.`);

	for (const key of Object.keys(value)) {
		ensure(fields.includes(key), `${title}: неподдерживаемое поле «${key}».`);
	}
}

export function validateResources(resources, calculations = null) {
	ensure(isRecord(resources), 'Раздел ресурсов должен быть объектом.');
	ensure(Object.keys(resources).length <= 128, 'Слишком много ресурсов.');

	const result = Object.create(null);

	for (const [code, definition] of Object.entries(resources)) {
		ensure(CODE_PATTERN.test(code), `Некорректный код ресурса: «${code}».`);
		const fields = ['label', 'short_label', 'description', 'maximum', 'initial', 'recovery'];
		knownFields(definition, fields, `Ресурс ${code}`);

		const {label, maximum} = definition;
		const description = definition.description ?? '';
		const validDescription = typeof description === 'string' && [...description].length <= 10000;
		ensure(validDescription, `Ресурс ${code}: описание должно быть текстом до 10000 символов.`);
		const initial = definition.initial ?? 'full';
		const recovery = definition.recovery ?? {};

		ensure(typeof label === 'string' && label.trim().length > 0 && label.length <= 100, `Ресурс ${code}: нужно название.`);
		ensure(initial === 'full' || nonnegative(initial), `Ресурс ${code}: недопустимый начальный запас.`);

		if (typeof maximum === 'string') {
			const parts = maximum.split('.');
			const [namespace, target] = parts;

			ensure(parts.length === 2, `Ресурс ${code}: некорректная ссылка максимума.`);
			ensure(['attribute', 'stat'].includes(namespace), `Ресурс ${code}: неизвестный вид ссылки.`);
			ensure(CODE_PATTERN.test(target), `Ресурс ${code}: некорректный код источника.`);

			if (calculations) {
				const source = namespace === 'attribute' ? calculations.attributes : calculations.derived;
				ensure(isRecord(source) && Object.hasOwn(source, target), `Ресурс ${code}: источник ${maximum} отсутствует.`);
			}
		} else {
			ensure(nonnegative(maximum), `Ресурс ${code}: максимум должен быть неотрицательным целым числом.`);
			ensure(initial === 'full' || initial <= maximum, `Ресурс ${code}: начальный запас превышает максимум.`);
		}

		ensure(isRecord(recovery), `Ресурс ${code}: некорректные правила восстановления.`);
		ensure(Object.keys(recovery).length <= 128, `Ресурс ${code}: слишком много событий восстановления.`);

		const copiedRecovery = Object.create(null);

		for (const [event, amount] of Object.entries(recovery)) {
			ensure(CODE_PATTERN.test(event), `Ресурс ${code}: некорректный код события «${event}».`);
			ensure(amount === 'full' || (nonnegative(amount) && amount > 0), `Ресурс ${code}: некорректное восстановление.`);
			copiedRecovery[event] = amount;
		}

		result[code] = {label, maximum, initial, recovery: copiedRecovery};

		if (Object.hasOwn(definition, 'short_label')) {
			result[code].short_label = normalizeShortLabel(definition.short_label);
		}
		if (Object.hasOwn(definition, 'description')) {
			result[code].description = description;
		}

	}

	return result;
}

export function readProfileResources(profile) {
	ensure(isRecord(profile), 'Профиль правил должен быть объектом.');
	ensure([3, 4].includes(profile.schema_version), 'Поддерживаются версии профиля 3 и 4.');
	ensure(isRecord(profile.calculations), 'Нет раздела расчётов.');
	ensure(isRecord(profile.calculations.attributes), 'Нет определений исходных показателей.');
	ensure(isRecord(profile.calculations.derived), 'Нет определений вычисляемых показателей.');
	ensure(isRecord(profile.initial_attributes), 'Нет начальных значений.');

	if (profile.schema_version === 4) {
		ensure(Object.hasOwn(profile, 'resources'), 'В версии 4 раздел ресурсов должен быть передан явно.');
	}

	const resources = Object.hasOwn(profile, 'resources') ? profile.resources : {};

	if (profile.schema_version === 3) {
		ensure(isRecord(resources) && Object.keys(resources).length === 0, 'Версия 3 не может содержать ресурсы.');
	}

	return validateResources(resources, profile.calculations);
}

export function validateResourcePreview(resources, result) {
	ensure(isRecord(result?.resource_limits), 'Сервер не вернул максимумы ресурсов.');
	ensure(isRecord(result?.resource_initial), 'Сервер не вернул начальные запасы ресурсов.');

	const codes = Object.keys(resources);

	for (const values of [result.resource_limits, result.resource_initial]) {
		ensure(Object.keys(values).length === codes.length, 'Состав ресурсов в ответе сервера не совпадает с запросом.');
		ensure(codes.every((code) => Object.hasOwn(values, code)), 'В ответе сервера отсутствуют ресурсы.');
	}

	return codes.map((code) => {
		const definition = resources[code];
		const maximum = result.resource_limits[code];
		const initial = result.resource_initial[code];

		ensure(nonnegative(maximum) && nonnegative(initial), `Некорректный результат для ресурса ${code}.`);
		ensure(initial <= maximum, `Начальный запас ресурса ${code} превышает максимум.`);

		let expectedMaximum = definition.maximum;

		if (typeof expectedMaximum === 'string') {
			const [namespace, target] = expectedMaximum.split('.');
			const source = namespace === 'attribute' ? result.attributes : result.derived;
			ensure(isRecord(source) && Object.hasOwn(source, target), `В ответе нет источника максимума ресурса ${code}.`);
			expectedMaximum = source[target];
		}

		const expectedInitial = definition.initial === 'full' ? maximum : definition.initial;

		ensure(maximum === expectedMaximum, `Не совпадает максимум ресурса ${code}.`);
		ensure(initial === expectedInitial, `Не совпадает начальный запас ресурса ${code}.`);

		return {code, label: definition.label, maximum, initial};
	});
}