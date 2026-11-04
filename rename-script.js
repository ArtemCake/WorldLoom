// rename-script.js

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.dirname(fileURLToPath(import.meta.url));
const distRoot = path.resolve(projectRoot, 'frontend/dist');
const manifestPath = path.join(distRoot, '.vite', 'manifest.json');
const temporaryManifestPath = `${manifestPath}.tmp`;

const targets = [
  {
    entry: 'src/js/main.js',
    directory: 'assets/js',
    extension: '.js',
    filename: 'main.min.js',
  },
  {
    entry: 'src/styles/style.scss',
    directory: 'assets/css',
    extension: '.css',
    filename: 'style.min.css',
  },
];

function prepareRenames(manifest) {
  return targets.map(({ entry, directory, extension, filename }) => {
    const source = manifest[entry]?.file;

    if (
    typeof source !== 'string'
    || path.posix.dirname(source) !== directory
    || path.posix.extname(source) !== extension
    || source.includes('\\')
    ) {
      throw new Error(
        `Некорректный путь результата сборки для ${entry}`,
      );
    }

    const destination = `${directory}/${filename}`;
    const sourcePath = path.join(distRoot, source);
    const destinationPath = path.join(distRoot, destination);

    if (!fs.statSync(sourcePath).isFile()) {
      throw new Error(`Результат сборки не является файлом: ${source}`);
    }

    if (
    source !== destination
    && fs.existsSync(destinationPath)
    ) {
      throw new Error(
        `Целевой файл уже существует: ${destination}. `
        + 'Выполните чистую сборку через npm run build.',
      );
    }

    return { source, destination, sourcePath, destinationPath };
  });
}

function updateManifest(manifest, renames) {
  const replacements = new Map(
    renames.map(({ source, destination }) => [source, destination]),
  );

  const replacePath = (value) => replacements.get(value) ?? value;

  for (const entry of Object.values(manifest)) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      throw new Error('Манифест содержит некорректную запись');
    }

    if (typeof entry.file === 'string') {
      entry.file = replacePath(entry.file);
    }

    for (const field of ['css', 'assets']) {
      if (Array.isArray(entry[field])) {
        entry[field] = entry[field].map(replacePath);
      }
    }
  }
}

function renameBuildFiles() {
  const manifest = JSON.parse(
    fs.readFileSync(manifestPath, 'utf8'),
  );

  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
    throw new Error('Манифест должен содержать объект');
  }

  // Проверяем обе точки входа до изменения файлов.
  const renames = prepareRenames(manifest);
  updateManifest(manifest, renames);

  const completed = [];
  let temporaryManifestCreated = false;

  try {
    // Открываем новый файл исключительно для текущего запуска.
    // Если .tmp уже существует, не перезаписываем и не удаляем его.
    const descriptor = fs.openSync(temporaryManifestPath, 'wx');
    temporaryManifestCreated = true;

    try {
      fs.writeFileSync(
        descriptor,
        `${JSON.stringify(manifest, null, 2)}\n`,
        { encoding: 'utf8' },
      );
    } finally {
      fs.closeSync(descriptor);
    }

    for (const rename of renames) {
      if (rename.source === rename.destination) {
        continue;
      }

      fs.renameSync(rename.sourcePath, rename.destinationPath);
      completed.push(rename);
    }

    // Подменяем манифест только после переименования обоих ресурсов.
    fs.renameSync(temporaryManifestPath, manifestPath);
    temporaryManifestCreated = false;
  } catch (error) {
    // При обычной ошибке возвращаем переименованные файлы назад.
    for (const rename of [...completed].reverse()) {
      try {
        fs.renameSync(rename.destinationPath, rename.sourcePath);
      } catch (rollbackError) {
        console.error(
          `[RENAME-SCRIPT] Не удалось восстановить ${rename.source}:`,
          rollbackError.message,
        );
      }
    }

    throw error;
  } finally {
    // Удаляем только временный файл, созданный этим запуском.
    if (temporaryManifestCreated) {
      try {
        if (fs.existsSync(temporaryManifestPath)) {
          fs.unlinkSync(temporaryManifestPath);
        }
      } catch (cleanupError) {
        console.error(
          '[RENAME-SCRIPT] Не удалось удалить временный манифест:',
          cleanupError.message,
        );
      }
    }
  }

  for (const { source, destination } of renames) {
    console.log(`[RENAME-SCRIPT] ${source} → ${destination}`);
  }

  console.log(
    '[RENAME-SCRIPT] Переименование и обновление манифеста завершены.',
  );
}

try {
  renameBuildFiles();
} catch (error) {
  console.error('[RENAME-SCRIPT] Ошибка:', error.message);
  process.exitCode = 1;
}