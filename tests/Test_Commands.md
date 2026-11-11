## Запуск тестов
python -m unittest discover -s tests/python -p "test_*.py" -v

if ($LASTEXITCODE -eq 0) {
$jsTests = @(Get-ChildItem -Path .\tests\js -Recurse -Filter *.test.mjs -File | ForEach-Object { $_.FullName })
node --test $jsTests
}

## Независимо от результата

python -m unittest discover -s tests/python -p "test_*.py" -v

$jsTests = @(Get-ChildItem -Path .\tests\js -Recurse -Filter *.test.mjs -File | ForEach-Object { $_.FullName })
node --test $jsTests
