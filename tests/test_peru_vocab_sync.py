"""Peru fork: the shared work-mode / level vocabulary must not drift.

src/peru.ts is copied verbatim into every Peru portal CLI so each skill stays a
self-contained folder, and tools/rank_state.py validates the same vocabulary in
Python. A copy edited in one place only would make /scrape, /rank and /apply
disagree on what a posting's modality or level is.
"""
import importlib.util
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / ".agents" / "skills"
PERU_CLIS = ["computrabajo-search", "bumeran-search", "getonboard-search", "linkedin-search", "jev-search"]


def ts_list(source: str, const: str) -> set[str]:
    block = re.search(rf"export const {const}[^=]*=\s*\[(.*?)\]", source, re.S)
    assert block, f"{const} not found in peru.ts"
    return set(re.findall(r'"([^"]+)"', block.group(1)))


class PeruVocabularySync(unittest.TestCase):
    def test_every_copy_is_identical(self):
        copies = {name: (SKILLS / name / "cli" / "src" / "peru.ts").read_bytes() for name in PERU_CLIS}
        reference = copies["computrabajo-search"]
        drifted = [name for name, body in copies.items() if body != reference]
        self.assertFalse(drifted, f"src/peru.ts differs from computrabajo-search's copy in: {drifted}")

    def test_every_copy_has_the_shared_tests(self):
        copies = {name: (SKILLS / name / "cli" / "tests" / "peru.test.ts").read_bytes() for name in PERU_CLIS}
        reference = copies["computrabajo-search"]
        self.assertFalse([n for n, b in copies.items() if b != reference], "tests/peru.test.ts copies differ")

    def test_rank_state_accepts_exactly_the_typescript_vocabulary(self):
        source = (SKILLS / "computrabajo-search" / "cli" / "src" / "peru.ts").read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location("rank_state", REPO / "tools" / "rank_state.py")
        rank_state = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rank_state)
        self.assertEqual(rank_state.MODALITIES, ts_list(source, "MODALITIES"))
        self.assertEqual(rank_state.LEVELS, ts_list(source, "LEVELS"))


if __name__ == "__main__":
    unittest.main()
