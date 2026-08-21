import unittest
from pathlib import Path
import sys


WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))
sys.path.insert(0, str(WORKER_ROOT / "scripts"))

from import_rag_v3_2_0_chroma import (  # noqa: E402
    CHUNK_SCHEMA_VERSION,
    CORPUS_STATUS,
    DATASET_VERSION,
    EXPECTED_COUNT,
    SCENARIO_TAXONOMY_VERSION,
    DEFAULT_INPUT_FILE,
    DEFAULT_MANIFEST_FILE,
    load_chunks,
    load_manifest,
    make_chroma_metadata,
)


class RagV320ImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest(DEFAULT_MANIFEST_FILE)
        cls.chunks = load_chunks(DEFAULT_INPUT_FILE)

    def test_manifest_matches_v3_2_0_contract(self) -> None:
        self.assertEqual(
            self.manifest["dataset_version"],
            DATASET_VERSION,
        )
        self.assertEqual(
            self.manifest["chunk_schema_version"],
            CHUNK_SCHEMA_VERSION,
        )
        self.assertEqual(
            self.manifest["scenario_taxonomy_version"],
            SCENARIO_TAXONOMY_VERSION,
        )
        self.assertEqual(
            self.manifest["corpus_status"],
            CORPUS_STATUS,
        )
        self.assertEqual(
            self.manifest["expected_chunk_count"],
            EXPECTED_COUNT,
        )

    def test_source_has_exactly_500_unique_chunks(self) -> None:
        ids = [
            item["chunk_id"]
            for item in self.chunks
        ]

        self.assertEqual(
            len(self.chunks),
            EXPECTED_COUNT,
        )
        self.assertEqual(
            len(set(ids)),
            EXPECTED_COUNT,
        )

    def test_versions_are_consistent_for_all_chunks(self) -> None:
        for item in self.chunks:
            metadata = item["metadata"]
            self.assertEqual(
                metadata["dataset_version"],
                DATASET_VERSION,
            )
            self.assertEqual(
                metadata["chunk_schema_version"],
                CHUNK_SCHEMA_VERSION,
            )
            self.assertEqual(
                metadata["scenario_taxonomy_version"],
                SCENARIO_TAXONOMY_VERSION,
            )
            self.assertEqual(
                metadata["corpus_status"],
                CORPUS_STATUS,
            )

    def test_metadata_is_chroma_writable(self) -> None:
        allowed_types = (
            str,
            int,
            float,
            bool,
        )

        for item in self.chunks:
            chroma_metadata = make_chroma_metadata(
                item
            )
            for value in chroma_metadata.values():
                self.assertIsInstance(
                    value,
                    allowed_types,
                )


if __name__ == "__main__":
    unittest.main()
