// rename-script.js

import fs from 'fs';
import path from 'path';

// --- НАСТРОЙКА ПУТЕЙ ---
// Используем fileURLToPath для корректной работы импорта в ESM
import { fileURLToPath } from 'url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const jsDistPath = path.resolve(__dirname, 'frontend/dist/assets', 'js');
const cssDistPath = path.resolve(__dirname, 'frontend/dist/assets', 'css');

console.log('[RENAME-SCRIPT] Запущен поиск файлов...');

function renameFile(folderPath, prefix, newName) {
  try {
    // Проверяем наличие папки
    if (!fs.existsSync(folderPath)) {
      console.warn(`Папка ${folderPath} не найдена. Пропускаем.`);
      return;
    }

    const files = fs.readdirSync(folderPath);

    // Ищем файл, который начинается с указанного префикса
    // (учитываем хеши вида main-DXie3Vxg.js)
    const targetFile = files.find(file => file.startsWith(prefix));

    if (targetFile) {
      const oldPath = path.join(folderPath, targetFile);
      const newPath = path.join(folderPath, newName);

      // Переименовываем файл синхронно
      fs.renameSync(oldPath, newPath);
      console.log(`✅ Файл '${targetFile}' успешно переименован в '${newName}'`);
    } else {
      console.log(`Файл с префиксом '${prefix}' в папке ${folderPath} не найден.`);
    }
  } catch (err) {
    console.error(`Ошибка при обработке ${folderPath}:`, err.message);
  }
}

// --- ВЫПОЛНЕНИЕ СКРИПТА ---
try {
  // 1. Переименовываем JS-файл
  renameFile(jsDistPath, 'main-', 'main.min.js');

  // 2. Переименовываем CSS-файл
  renameFile(cssDistPath, 'styles-', 'style.min.css');

  console.log('[RENAME-SCRIPT] Работа завершена.');
} catch (e) {
  console.error('[RENAME-SCRIPT] Фатальная ошибка:', e);
  process.exit(1); // Останавливаем CI/CD пайплайн, если нейминг упал
}