import pytest

from backend.app.modules.game_systems.rules.rules_composition import compose_system_draft
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile


def profile(**extra):
	data = {
		"schema_version": 4,
		"calculations": {"attributes": {}, "derived": {}},
		"initial_attributes": {},
		"resources": {},
	}

	data.update(extra)

	return RulesProfile.model_validate(data)


def test_old_profile_has_empty_rulebook():
	assert profile().rulebook == {}


def test_rulebook_survives_serialization():
	rules = profile(rulebook={
		"resolution": {
			"label": "Разрешение проверок",
			"status": "described",
			"fields": {"method": "Бросок двух костей с добавлением подготовки."},
		}
	})

	restored = RulesProfile.model_validate_json(rules.model_dump_json())

	assert restored.rulebook == rules.rulebook


def test_rulebook_override_does_not_change_basis():
	base = profile()
	overrides = {
		"rulebook": {
			"powers": {
				"label": "Особые силы",
				"status": "unused",
				"fields": {},
			}
		}
	}

	effective = compose_system_draft(base, overrides)

	assert base.rulebook == {}
	assert effective.rulebook["powers"].status == "unused"


@pytest.mark.parametrize("status", ["automatic", "", 1])
def test_unknown_status_is_rejected(status):
	with pytest.raises(ValueError):
		profile(rulebook={
			"resolution": {
				"label": "Проверки",
				"status": status,
				"fields": {},
			}
		})


def test_non_text_description_is_rejected():
	with pytest.raises(ValueError):
		profile(rulebook={
			"resolution": {
				"label": "Проверки",
				"fields": {"method": 20},
			}
		})
