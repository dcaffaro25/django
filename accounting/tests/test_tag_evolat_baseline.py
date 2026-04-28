"""Sanity tests for the ``tag_evolat_baseline`` management command.

We don't run the command end-to-end here -- that requires a fixture
mirror of Evolat's chart and the tests would just validate that
Django ORM works. Instead we verify the static anchor tables are
internally consistent: every category and tag value referenced is a
valid member of its closed enum. This catches typos that would
otherwise only surface when an operator runs the command and gets
``CommandError: invalid report_category 'receitabruta'``.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from accounting.management.commands.tag_evolat_baseline import (
    LEAF_CATEGORY_OVERRIDES,
    LEVEL_1_CATEGORIES,
    LEVEL_2_CATEGORIES,
    PATTERN_TAGS,
    SUBTREE_TAGS,
)
from accounting.services.taxonomy_meta import (
    REPORT_CATEGORY_VALUES,
    TAG_VALUES,
)


class AnchorTableValidationTests(SimpleTestCase):
    def test_level1_categories_use_valid_enum_values(self):
        for name, category, tags in LEVEL_1_CATEGORIES:
            with self.subTest(name=name):
                self.assertIn(
                    category, REPORT_CATEGORY_VALUES,
                    f"category {category!r} on {name!r} not in REPORT_CATEGORY_VALUES",
                )
                for t in tags:
                    self.assertIn(
                        t, TAG_VALUES,
                        f"tag {t!r} on {name!r} not in TAG_VALUES",
                    )

    def test_level2_categories_use_valid_enum_values(self):
        for parent_name, child_name, category, tags in LEVEL_2_CATEGORIES:
            with self.subTest(parent=parent_name, child=child_name):
                self.assertIn(
                    category, REPORT_CATEGORY_VALUES,
                    f"category {category!r} on {child_name!r} not in REPORT_CATEGORY_VALUES",
                )
                for t in tags:
                    self.assertIn(
                        t, TAG_VALUES,
                        f"tag {t!r} on {child_name!r} not in TAG_VALUES",
                    )

    def test_subtree_tags_use_valid_enum_values(self):
        for anchor, tags in SUBTREE_TAGS:
            with self.subTest(anchor=anchor):
                for t in tags:
                    self.assertIn(
                        t, TAG_VALUES,
                        f"tag {t!r} on subtree {anchor!r} not in TAG_VALUES",
                    )

    def test_no_duplicate_anchor_names_at_level_1(self):
        """If two rows in LEVEL_1_CATEGORIES have the same name, the
        command would silently apply twice and only the second value
        would stick. Catch the typo at test-time instead."""
        names = [name for name, _, _ in LEVEL_1_CATEGORIES]
        self.assertEqual(
            len(names), len(set(names)),
            f"duplicate anchor names in LEVEL_1_CATEGORIES: "
            f"{[n for n in names if names.count(n) > 1]}",
        )

    def test_no_duplicate_subtree_anchors(self):
        names = [a for a, _ in SUBTREE_TAGS]
        self.assertEqual(
            len(names), len(set(names)),
            f"duplicate anchors in SUBTREE_TAGS: "
            f"{[n for n in names if names.count(n) > 1]}",
        )

    def test_leaf_category_overrides_use_valid_enum_values(self):
        for name, category in LEAF_CATEGORY_OVERRIDES:
            with self.subTest(name=name):
                self.assertIn(
                    category, REPORT_CATEGORY_VALUES,
                    f"override category {category!r} on {name!r} not in REPORT_CATEGORY_VALUES",
                )

    def test_pattern_tags_use_valid_enum_values(self):
        for substr, tags in PATTERN_TAGS:
            with self.subTest(substr=substr):
                for t in tags:
                    self.assertIn(
                        t, TAG_VALUES,
                        f"tag {t!r} on pattern {substr!r} not in TAG_VALUES",
                    )

    def test_level2_parents_are_NOT_in_level1_categories(self):
        """The level-2 disambiguation pattern only makes sense when
        the level-1 parent is intentionally LEFT untagged (because
        its children have mixed categories). If a parent appears in
        both tables, the level-1 tag would apply first and the level-2
        children would inherit a category that conflicts with their
        own tag. Test catches the misconfiguration up front."""
        level1_names = {name for name, _, _ in LEVEL_1_CATEGORIES}
        level2_parent_names = {parent for parent, _, _, _ in LEVEL_2_CATEGORIES}
        overlap = level1_names & level2_parent_names
        self.assertFalse(
            overlap,
            f"these names appear as both a level-1 anchor AND a "
            f"level-2 parent of disambiguation: {overlap}. Pick one.",
        )
