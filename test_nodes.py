"""CPU regression tests. Run with the ComfyUI Python environment."""
import json
from pathlib import Path
import unittest

import torch

from nodes import H3BustReferenceSelector as Selector


class SelectorTests(unittest.TestCase):
    def test_assets(self):
        for size in ("01", "02", "03", "04", "05", "06"):
            with self.subTest(size=size):
                image, prompt = Selector().select_bust_reference(size, "summary:\nAn adult woman waves.")
                self.assertEqual(image.ndim, 4)
                self.assertEqual(image.shape[0], 1)
                self.assertEqual(image.shape[-1], 3)
                self.assertEqual(image.dtype, torch.float32)
                self.assertTrue(torch.isfinite(image).all())
                self.assertGreaterEqual(float(image.min()), 0)
                self.assertLessEqual(float(image.max()), 1)
                self.assertIn("<Picture 2>", prompt)

    def test_other_picture_is_preserved(self):
        role = "<Picture 1> is the upper-body character identity reference."
        prompt = "subject_definitions:\n" + role + "\nsummary:\nAn adult woman waves."
        result = Selector._inject_three_view_reference(prompt, 2)
        self.assertIn(role, result)
        self.assertIn("<Picture 2> is a three-view", result)

    def test_custom_target_is_preserved(self):
        for role in ("<Picture 2> is my custom proportion reference.",
                     "<Picture 2> is the frontal upper-body proportion reference for <Subject 1>. Keep my custom description."):
            prompt = "subject_definitions:\n" + role
            self.assertEqual(Selector._inject_three_view_reference(prompt, 2), prompt)

    def test_known_legacy_sentences_are_upgraded(self):
        roles = (
            "the upper-body proportion reference for <Subject 1>. It defines the bust size and upper-body silhouette of <Subject 1>.",
            "the frontal upper-body proportion reference for <Subject 1>. It defines the frontal bust size and upper-body silhouette of <Subject 1>.",
            "the right three-quarter upper-body proportion reference for <Subject 1>. It defines the three-dimensional bust volume, forward projection, and upper-body silhouette of <Subject 1>.",
            "a three-view upper-body turnaround reference of the same adult woman, showing right side, front view, and left side. It defines the bust size, bust volume, chest projection, and upper-body proportions of <Subject 1> consistently across viewing angles. All three views represent the same body proportions from different viewing angles.",
        )
        for role in roles:
            with self.subTest(role=role):
                result = Selector._inject_three_view_reference("<Picture 2> is " + role, 2)
                self.assertIn("<Picture 2> is a three-view", result)
                self.assertIn("It defines the bust size and upper-body proportions", result)

    def test_idempotence_and_line_endings(self):
        for ending in ("\n", "\r\n"):
            prompt = f"subject_definitions:{ending}<Picture 1> is the character.{ending}{ending}summary:{ending}Wave."
            result = Selector._inject_three_view_reference(prompt, 2)
            self.assertEqual(Selector._inject_three_view_reference(result, 2), result)
            self.assertEqual(result.count("<Picture 2>"), 1)
            self.assertIn(ending + "<Picture 2>", result)

    def test_slots(self):
        for slot in range(9):
            _, prompt = Selector().select_bust_reference("01", "summary:\nWave.", f"ref_image_{slot}")
            self.assertIn(f"<Picture {slot + 1}>", prompt)

    def test_invalid_inputs(self):
        for values in ({"base_prompt": " "}, {"base_prompt": None},
                       {"bust_size": "07"}, {"bust_size": "../../x"},
                       {"ref_image_slot": "typo"}, {"ref_image_slot": "ref_image_9"},
                       {"picture_number": 0}, {"picture_number": True},
                       {"mode": "Front Only"}):
            args = {"bust_size": "01", "base_prompt": "summary:\nWave."}
            args.update(values)
            with self.subTest(values=values), self.assertRaises(ValueError):
                Selector().select_bust_reference(**args)

    def test_legacy_keyword_call(self):
        _, prompt = Selector().select_bust_reference("01", "summary:\nWave.", picture_number=3)
        self.assertIn("<Picture 3>", prompt)

    def test_workflow_connections(self):
        workflow = json.loads(Path(__file__).with_name("sample_workflow_three_view.json").read_text(encoding="utf-8"))
        nodes = {n["id"]: n for n in workflow["nodes"]}
        self.assertEqual(len(nodes), len(workflow["nodes"]))
        for lid, src, output, dst, input_slot, kind in workflow["links"]:
            self.assertEqual(nodes[dst]["inputs"][input_slot]["link"], lid)
            self.assertIn(lid, nodes[src]["outputs"][output]["links"])
            self.assertEqual(nodes[src]["outputs"][output]["type"], kind)
            self.assertEqual(nodes[dst]["inputs"][input_slot]["type"], kind)
        ref = next(n for n in nodes.values() if n["type"] == "MiniMaxH3ReferenceToVideo")
        selector = next(n for n in nodes.values() if n["type"] == "H3BustReferenceSelector")
        by_link = {link[0]: link for link in workflow["links"]}
        pins = {i["name"]: by_link[i["link"]] for i in ref["inputs"] if i.get("link")}
        self.assertEqual(pins["ref_images.ref_image_1"][1:3], [selector["id"], 0])
        self.assertEqual(pins["prompt"][1:3], [selector["id"], 1])
        self.assertEqual(nodes[pins["ref_images.ref_image_0"][1]]["type"], "LoadImage")
        for node in nodes.values():
            if node["type"] == "LoraLoaderModelOnly":
                self.assertNotIn("\\", node["widgets_values"][0])
            if node["type"] == "LoadImage":
                self.assertEqual(node["widgets_values"][0], "")


if __name__ == "__main__":
    unittest.main()
