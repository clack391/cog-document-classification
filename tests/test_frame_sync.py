"""The taxonomy Frame is the source of truth. These tests fail when the Frame,
the questions, the decision code and the output schema stop agreeing on the
document types and the tag vocabulary."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cog_core      # noqa: E402
import task_logic    # noqa: E402

FRAME = (ROOT / "taxonomy" / "document-taxonomy.frame.md").read_text()


def section(title):
    match = re.search(rf"^## {title}\n(.*?)(?=^## |\Z)", FRAME, re.S | re.M)
    assert match, f"Frame has no '{title}' section"
    return match.group(1)


FRAME_TYPES = re.findall(r"^- \*\*`([a-z_]+)`\*\*:", section("Terminology"), re.M)
FRAME_TAGS = re.findall(r"^\| `([a-z_]+)` \|", section("Tag Vocabulary"), re.M)
FRAME_TYPE_TAGS = dict(re.findall(r"^\| `([a-z_]+)` \| `([a-z_]+)` \|", section("Tag Vocabulary"), re.M))


class FrameSync(unittest.TestCase):
    def test_the_frame_lists_types_and_tags(self):
        self.assertEqual(len(FRAME_TYPES), 6)
        self.assertEqual(FRAME_TYPES[-1], "other")
        self.assertTrue(FRAME_TAGS)

    def test_questions_offer_exactly_the_frame_types(self):
        self.assertEqual(list(cog_core.QUESTIONS["document_type"]["criteria"]), FRAME_TYPES)

    def test_one_question_per_frame_tag(self):
        asked = [q[len(task_logic.TAG_PREFIX):] for q in cog_core.QUESTIONS
                 if q.startswith(task_logic.TAG_PREFIX)]
        self.assertEqual(sorted(asked), sorted(FRAME_TAGS))

    def test_decision_code_uses_the_frame_tags_and_types(self):
        self.assertEqual(list(task_logic.TYPE_TAGS), FRAME_TYPES)
        general = [t for t in FRAME_TAGS if t not in FRAME_TYPE_TAGS]
        self.assertEqual(list(task_logic.GENERAL_TAGS), general)
        coded = {tag: kind for kind, tags in task_logic.TYPE_TAGS.items() for tag in tags}
        self.assertEqual(coded, FRAME_TYPE_TAGS)

    def test_output_schema_uses_the_frame_tags_and_types(self):
        decision = cog_core.OUTPUT_SCHEMA["$defs"]["decision"]["properties"]
        self.assertEqual([t for t in decision["document_type"]["enum"] if t], FRAME_TYPES)
        self.assertEqual(sorted(decision["tags"]["items"]["enum"]), sorted(FRAME_TAGS))


if __name__ == "__main__":
    unittest.main()
