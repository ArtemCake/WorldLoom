# tests/python/game_systems/test_system_book_commands.py

import unittest
from uuid import uuid4
from pydantic import ValidationError
from backend.app.modules.game_systems.schemas.system_book_set import SystemBookPin, SystemBookSet
from backend.app.modules.game_systems.services import system_book_commands as commands


class SystemBookCommandsTests(unittest.TestCase):
	def setUp(self):
		self.first = SystemBookPin(book_id=uuid4(), version_id=uuid4())
		self.second = SystemBookPin(book_id=uuid4(), version_id=uuid4())
		self.third = SystemBookPin(book_id=uuid4(), version_id=uuid4())
		self.original = SystemBookSet(books=[self.first, self.second, self.third])
		self.before = self.original.model_dump(mode="json")

	def assert_original_unchanged(self):
		self.assertEqual(self.original.model_dump(mode="json"), self.before)

	def test_empty_draft_is_allowed(self):
		result = SystemBookSet()

		self.assertEqual(result.books, [])
		self.assertEqual(result.schema_version, 1)

	def test_transport_identifiers_are_read_from_strings(self):
		result = SystemBookPin.model_validate({
			"book_id": str(self.first.book_id),
			"version_id": str(self.first.version_id),
		})

		self.assertEqual(result, self.first)

	def test_duplicate_book_is_rejected(self):
		another_version = SystemBookPin(book_id=self.first.book_id, version_id=uuid4())

		with self.assertRaises(ValidationError):
			SystemBookSet(books=[self.first, another_version])

	def test_duplicate_publication_is_rejected(self):
		another_book = SystemBookPin(book_id=uuid4(), version_id=self.first.version_id)

		with self.assertRaises(ValidationError):
			SystemBookSet(books=[self.first, another_book])

	def test_unsupported_format_is_rejected(self):
		with self.assertRaises(ValidationError):
			SystemBookSet.model_validate({"schema_version": 2, "books": []})

	def test_add_appends_without_changing_original(self):
		pin = SystemBookPin(book_id=uuid4(), version_id=uuid4())
		result = commands.add_system_book(self.original, pin)

		self.assertEqual(result.books, [self.first, self.second, self.third, pin])
		self.assert_original_unchanged()

	def test_add_existing_book_does_not_replace_publication(self):
		pin = SystemBookPin(book_id=self.first.book_id, version_id=uuid4())

		with self.assertRaises(ValueError):
			commands.add_system_book(self.original, pin)

		self.assert_original_unchanged()

	def test_replace_keeps_position_and_other_books(self):
		pin = SystemBookPin(book_id=self.second.book_id, version_id=uuid4())
		result = commands.replace_system_book(self.original, pin, self.second.version_id)

		self.assertEqual(result.books, [self.first, pin, self.third])
		self.assert_original_unchanged()

	def test_replace_same_publication_has_no_content_changes(self):
		result = commands.replace_system_book(self.original, self.second, self.second.version_id)

		self.assertEqual(result.model_dump(mode="json"), self.before)
		self.assertIsNot(result, self.original)

	def test_replace_rejects_unexpected_publication(self):
		pin = SystemBookPin(book_id=self.second.book_id, version_id=uuid4())

		with self.assertRaises(ValueError):
			commands.replace_system_book(self.original, pin, uuid4())

		self.assert_original_unchanged()

	def test_replace_does_not_add_missing_book(self):
		pin = SystemBookPin(book_id=uuid4(), version_id=uuid4())

		with self.assertRaises(ValueError):
			commands.replace_system_book(self.original, pin, pin.version_id)

		self.assert_original_unchanged()

	def test_remove_keeps_remaining_order(self):
		result = commands.remove_system_book(self.original, self.second.book_id, self.second.version_id)

		self.assertEqual(result.books, [self.first, self.third])
		self.assert_original_unchanged()

	def test_remove_last_book_leaves_valid_empty_draft(self):
		value = SystemBookSet(books=[self.first])
		result = commands.remove_system_book(value, self.first.book_id, self.first.version_id)

		self.assertEqual(result.books, [])
		self.assertEqual(value.books, [self.first])

	def test_remove_rejects_unexpected_publication(self):
		with self.assertRaises(ValueError):
			commands.remove_system_book(self.original, self.first.book_id, uuid4())

		self.assert_original_unchanged()

	def test_move_before_another_book(self):
		result = commands.move_system_book(self.original, self.third.book_id, self.first.book_id)

		self.assertEqual(result.books, [self.third, self.first, self.second])
		self.assert_original_unchanged()

	def test_move_forward_uses_position_after_removal(self):
		result = commands.move_system_book(self.original, self.first.book_id, self.third.book_id)

		self.assertEqual(result.books, [self.second, self.first, self.third])
		self.assert_original_unchanged()

	def test_move_to_end(self):
		result = commands.move_system_book(self.original, self.first.book_id, None)

		self.assertEqual(result.books, [self.second, self.third, self.first])
		self.assert_original_unchanged()

	def test_move_before_self_changes_nothing(self):
		result = commands.move_system_book(self.original, self.second.book_id, self.second.book_id)

		self.assertEqual(result.model_dump(mode="json"), self.before)
		self.assert_original_unchanged()

	def test_unknown_move_target_does_not_remove_source(self):
		with self.assertRaises(ValueError):
			commands.move_system_book(self.original, self.first.book_id, uuid4())

		self.assert_original_unchanged()

	def test_unknown_source_is_rejected(self):
		with self.assertRaises(ValueError):
			commands.move_system_book(self.original, uuid4(), None)

		self.assert_original_unchanged()

	def test_returned_state_does_not_share_nested_items(self):
		result = commands.move_system_book(self.original, self.first.book_id, None)

		for item in result.books:
			source = next(book for book in self.original.books if book.book_id == item.book_id)
			self.assertIsNot(item, source)

		self.assert_original_unchanged()
