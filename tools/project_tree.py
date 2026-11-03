# tools/project_tree.py

import argparse
import fnmatch
import os
import stat
import sys
from pathlib import Path


def normalize(value):
	"""На Windows сравнивать без учёта регистра."""
	return value.casefold() if os.name == "nt" else value

def load_rules(path):
	rules = []

	for number, line in enumerate(
			path.read_text(encoding="utf-8-sig").splitlines(),
			start=1,
	):
		value = line.strip()

		if not value or value.startswith("#"):
			continue

		if "\\" in value:
			raise ValueError(
				f"Строка {number}: используй / вместо обратного слеша."
			)

		directory_only = value.endswith("/")
		anchored = value.startswith("/")
		pattern = value.strip("/")

		if (
				not pattern
				or any(part in {"", ".", ".."} for part in pattern.split("/"))
		):
			raise ValueError(
				f"Строка {number}: некорректное исключение {value!r}."
			)

		if not anchored and "/" in pattern:
			raise ValueError(
				f"Строка {number}: путь должен начинаться с /."
			)

		rules.append(
			(normalize(pattern), directory_only, anchored)
		)

	return rules

def is_excluded(relative, is_directory, rules):
	relative_name = normalize(relative.as_posix())
	basename = normalize(relative.name)

	for pattern, directory_only, anchored in rules:
		if directory_only and not is_directory:
			continue

		if anchored:
			# Привязанные к корню пути сравниваются точно.
			if relative_name == pattern:
				return True
		elif fnmatch.fnmatchcase(basename, pattern):
			return True

	return False

def is_link_or_reparse(info):
	return (
			stat.S_ISLNK(info.st_mode)
			or bool(getattr(info, "st_file_attributes", 0) & 0x400)
	)

def build_tree(root, output, rules):
	lines = [f"{root.name or root}/"]

	def read_children(directory):
		children = []

		with os.scandir(directory) as iterator:
			for entry in iterator:
				path = directory / entry.name

				# Сам файл результата в дерево не включаем.
				if path == output:
					continue

				info = path.lstat()
				linked = is_link_or_reparse(info)
				is_directory = stat.S_ISDIR(info.st_mode)

				if is_excluded(
						path.relative_to(root),
						is_directory,
						rules,
				):
					continue

				children.append((path, is_directory, linked))

		# Сначала каталоги, затем файлы; внутри — по имени.
		children.sort(
			key=lambda item: (
				not item[1],
				normalize(item[0].name),
				item[0].name,
			)
		)
		return children

	def push_children(stack, directory, prefix):
		children = read_children(directory)

		for index in range(len(children) - 1, -1, -1):
			path, is_directory, linked = children[index]
			stack.append(
				(
					path,
					prefix,
					index == len(children) - 1,
					is_directory,
					linked,
				)
			)

	stack = []
	push_children(stack, root, "")

	while stack:
		path, prefix, last, is_directory, linked = stack.pop()

		branch = "└── " if last else "├── "
		suffix = "/" if is_directory else ""

		if linked:
			suffix += " [ссылка — без обхода]"

		lines.append(f"{prefix}{branch}{path.name}{suffix}")

		if is_directory and not linked:
			# Повторная проверка перед обходом каталога.
			info = path.lstat()
			if (
					is_link_or_reparse(info)
					or not stat.S_ISDIR(info.st_mode)
			):
				raise ValueError(
					f"Каталог изменился во время обхода: {path}"
				)

			child_prefix = prefix + ("    " if last else "│   ")
			push_children(stack, path, child_prefix)

	return "\n".join(lines) + "\n"

def main():
	parser = argparse.ArgumentParser(
		description="Построить дерево проекта с исключениями."
	)
	parser.add_argument(
		"--root",
		default=".",
		help="Корень проекта; по умолчанию текущий каталог.",
	)
	parser.add_argument(
		"--ignore",
		default="structure_ignore.txt",
		help="Файл исключений, путь относительно корня или абсолютный.",
	)
	parser.add_argument(
		"--output",
		default="structure.txt",
		help="Результат, путь относительно корня или абсолютный.",
	)
	parser.add_argument(
		"--overwrite",
		action="store_true",
		help="Разрешить перезапись существующего результата.",
	)
	args = parser.parse_args()

	try:
		root = Path(args.root).resolve(strict=True)
		if not root.is_dir():
			raise ValueError("Корень проекта не является каталогом.")

		ignore = Path(args.ignore)
		if not ignore.is_absolute():
			ignore = root / ignore
		ignore = ignore.resolve(strict=True)

		output = Path(args.output)
		if not output.is_absolute():
			output = root / output
		output = Path(os.path.abspath(output))

		if output.resolve(strict=False) == ignore:
			raise ValueError(
				"Файл результата не должен совпадать с файлом исключений."
			)

		if output.exists() or output.is_symlink():
			info = output.lstat()
			if is_link_or_reparse(info) or not stat.S_ISREG(info.st_mode):
				raise ValueError(
					"Результат нельзя записать в ссылку или не обычный файл."
				)
			if not args.overwrite:
				raise ValueError(
					"Файл результата уже существует. "
					"Для обновления добавь --overwrite."
				)

		rules = load_rules(ignore)
		tree = build_tree(root, output, rules)

		mode = "w" if args.overwrite else "x"
		with output.open(mode, encoding="utf-8", newline="\n") as stream:
			stream.write(tree)

		print(f"Структура сохранена: {output}")
		return 0

	except (OSError, ValueError, UnicodeError) as error:
		print(f"Ошибка: {error}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	raise SystemExit(main())