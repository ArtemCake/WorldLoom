## Запуск тестов

```powershell
# Без PostgreSQL: pg-тесты помечаются как skipped.
python -m unittest discover -s tests/python -p "test_*.py" -v

if ($LASTEXITCODE -eq 0) {
$jsTests = @(Get-ChildItem -Path .\tests\js -Recurse -Filter *.test.mjs -File | ForEach-Object { $_.FullName })
node --test $jsTests
}
```

## Интеграционные проверки PostgreSQL

Тесты `tests/python/rules/test_article_postgresql.py` и
`tests/python/rules/test_book_postgresql.py` выполняются только при заданном
`WORLDLOOM_RULES_TEST_URL`. Каждый тест создаёт отдельную временную схему и
удаляет её после себя, поэтому база должна допускать `CREATE SCHEMA`.

Имя базы должно заканчиваться на `_test` или `_tests`.

В строке подключения подставьте свои логин и пароль PostgreSQL. Значения
`user` и `password` — это плейсхолдеры: с ними сервер обрывает соединение на
аутентификации, и все pg-тесты помечаются как skipped с сообщением о
недоступной базе.

```powershell
$env:WORLDLOOM_RULES_TEST_URL = "postgresql+asyncpg://<логин>:<пароль>@127.0.0.1:5432/worldlooms_rules_tests"
python -m pytest tests/python -q -ra
```

В bash-совместимой оболочке переменную передают инлайном:

```bash
WORLDLOOM_RULES_TEST_URL='postgresql+asyncpg://<логин>:<пароль>@127.0.0.1:5432/worldlooms_rules_tests' \
  python -m pytest tests/python -q -ra
```

Схема готовится общим помощником `tests/python/rules/pg_support.py`: он
применяет цепочку миграций по `down_revision` (имена файлов не важны) и
создаёт обязательных пользователей.

## Независимо от результата

```powershell
python -m unittest discover -s tests/python -p "test_*.py" -v

$jsTests = @(Get-ChildItem -Path .\tests\js -Recurse -Filter *.test.mjs -File | ForEach-Object { $_.FullName })
node --test $jsTests
```
