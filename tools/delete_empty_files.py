# tools/delete_empty_files.py

import argparse
import os
import stat
import sys
from pathlib import Path


def is_link_or_reparse(info):
	return (
			stat.S_ISLNK(info.st_mode)
			or bool(getattr(info, "st_file_attributes", 0) & 0x400)
	)

def check_directory(path):
	"""Проверить каталог и отсутствие ссылок в его пути."""
	for component in reversed((path, *path.parents)):
		info = component.lstat()

		if is_link_or_reparse(info):
			raise ValueError(
				f"Путь проходит через ссылку или reparse point: "
				f"{component}"
			)

		if not stat.S_ISDIR(info.st_mode):
			raise ValueError(f"Это не каталог: {component}")

def main():
	parser = argparse.ArgumentParser(
		description=(
			"Поиск файлов размером 0 байт. "
			"Удаление выполняется только с --delete."
		)
	)
	parser.add_argument("directory", help="Каталог для проверки")
	parser.add_argument(
		"--exclude",
		action="append",
		default=[],
		metavar="NAME",
		help="Исключить имя файла. Можно указать несколько раз.",
	)
	parser.add_argument(
		"--recursive",
		action="store_true",
		help="Проверять вложенные каталоги",
	)
	parser.add_argument(
		"--delete",
		action="store_true",
		help="Удалить найденные пустые файлы",
	)
	args = parser.parse_args()

	for name in args.exclude:
		if (
				not name
				or name in {".", ".."}
				or "/" in name
				or "\\" in name
				or ":" in name
		):
			parser.error(
				"--exclude принимает имя без пути, "
				"например __init__.py"
			)

	# На Windows normcase приводит имена к нижнему регистру.
	excluded = {os.path.normcase(name) for name in args.exclude}
	root = Path(os.path.abspath(args.directory))

	try:
		check_directory(root)
	except (OSError, ValueError) as error:
		print(f"Ошибка: {error}", file=sys.stderr)
		return 1

	pending = [root]
	found = 0
	deleted = 0
	errors = 0

	print("Режим:", "УДАЛЕНИЕ" if args.delete else "ТОЛЬКО ПРОСМОТР")
	print(f"Каталог: {root}")

	while pending:
		directory = pending.pop()

		try:
			check_directory(directory)

			with os.scandir(directory) as iterator:
				paths = sorted(
					(Path(entry.path) for entry in iterator),
					key=lambda path: (
						os.path.normcase(path.name),
						path.name,
					),
				)

		except (OSError, ValueError) as error:
			errors += 1
			print(
				f"Не удалось прочитать каталог {directory}: {error}",
				file=sys.stderr,
			)
			continue

		for path in paths:
			try:
				info = path.lstat()

				if is_link_or_reparse(info):
					print(f"Пропущена ссылка или reparse point: {path}")
					continue

				if stat.S_ISDIR(info.st_mode):
					if args.recursive:
						pending.append(path)
					continue

				if not stat.S_ISREG(info.st_mode):
					continue

				if os.path.normcase(path.name) in excluded:
					continue

				if info.st_size != 0:
					continue

				found += 1

				if not args.delete:
					print(f"Кандидат на удаление: {path}")
					continue

				# Повторные проверки непосредственно перед удалением.
				check_directory(path.parent)
				current = path.lstat()

				if (
						is_link_or_reparse(current)
						or not stat.S_ISREG(current.st_mode)
						or current.st_size != 0
						or (current.st_dev, current.st_ino)
						!= (info.st_dev, info.st_ino)
				):
					print(f"Пропущен изменившийся файл: {path}")
					continue

				path.unlink()
				deleted += 1
				print(f"Удалён: {path}")

			except (OSError, ValueError) as error:
				errors += 1
				print(
					f"Ошибка обработки {path}: {error}",
					file=sys.stderr,
				)

	print(f"\nНайдено кандидатов на удаление: {found}")
	print(f"Удалено: {deleted}")
	print(f"Ошибок: {errors}")

	if not args.delete:
		print("Ничего не удалено. Для удаления добавь --delete.")

	return 1 if errors else 0


if __name__ == "__main__":
	raise SystemExit(main())
