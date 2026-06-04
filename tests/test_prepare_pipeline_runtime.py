import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.prepare_pipeline_runtime import (
    PreparePipelineDependencies,
    run_prepare_and_attach,
)
from notes_runner_lib.prepare_transcript_runtime import PrepareTranscriptDependencies


class PreparePipelineRuntimeTests(unittest.TestCase):
    def test_run_prepare_and_attach_calls_transcript_then_bundle(self) -> None:
        calls: list[str] = []

        def fake_transcript(*_args, **_kwargs):
            calls.append("transcript")
            return {"work_dir": "/tmp/work", "reused": False}

        def fake_attach(payload, prepare_payload, bundle_dir, **_kwargs):
            calls.append("attach")
            self.assertEqual(prepare_payload["work_dir"], "/tmp/work")
            payload["prepare"] = prepare_payload

        deps = PreparePipelineDependencies(
            transcript=PrepareTranscriptDependencies(
                resolve_bundle_work_dir=lambda _bundle: None,
                load_prepare_payload=lambda _work: {},
                prepare_fingerprint_for_files=lambda _files: ([], "fp"),
                run_prepare_logic=lambda _files, source_hints=None: {"work_dir": "/tmp/work"},
                enrich_work_dir_with_source_hints=lambda *_args, **_kwargs: None,
            ),
            header_seed_filename="header-seed.json",
            ensure_dir=lambda path, _label: path,
            build_status=lambda _work: {"execution_plan": {}},
            link_bundle_work_dir=lambda _bundle, work: work,
            clean_title=lambda value: value,
            is_informative_title=lambda _value: True,
            work_prompt_dir=lambda work: work / "prompts",
            work_stage_dir=lambda work: work / "stages",
            record_bundle_stage_metric=lambda *_args, **_kwargs: None,
        )

        with mock.patch(
            "notes_runner_lib.prepare_pipeline_runtime.run_prepare_for_transcript",
            side_effect=fake_transcript,
        ) as transcript_mock:
            with mock.patch(
                "notes_runner_lib.prepare_pipeline_runtime.attach_prepare_outputs",
                side_effect=fake_attach,
            ):
                payload: dict[str, object] = {}
                result = run_prepare_and_attach(
                    payload,
                    Path("/tmp/transcript.md"),
                    Path("/tmp/bundle"),
                    deps=deps,
                )

        transcript_mock.assert_called_once()
        self.assertEqual(calls, ["transcript", "attach"])
        self.assertIn("prepare", payload)
        self.assertEqual(result["work_dir"], "/tmp/work")


if __name__ == "__main__":
    unittest.main()