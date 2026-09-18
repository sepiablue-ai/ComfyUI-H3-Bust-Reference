import re
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
import torch

NODE_DIR = Path(__file__).resolve().parent
ASSET_DIR = NODE_DIR / "assets" / "bust"


class H3BustReferenceSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "bust_size": (
                    ["01", "02", "03", "04", "05", "06"],
                    {"default": "01"},
                ),
                "ref_image_slot": (
                    [
                        "ref_image_0",
                        "ref_image_1",
                        "ref_image_2",
                        "ref_image_3",
                        "ref_image_4",
                        "ref_image_5",
                        "ref_image_6",
                        "ref_image_7",
                        "ref_image_8",
                    ],
                    {"default": "ref_image_1"},
                ),
                "base_prompt": (
                    "STRING",
                    {"multiline": True, "dynamicPrompts": False},
                ),
            },
            "optional": {
                "mode": (
                    ["Three-View Turnaround"],
                    {"default": "Three-View Turnaround"},
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("IMAGE", "PROMPT")
    FUNCTION = "select_bust_reference"
    CATEGORY = "MiniMax-H3/Bust Reference"

    def select_bust_reference(
        self,
        bust_size: str,
        base_prompt: str,
        ref_image_slot: str = "ref_image_1",
        mode: str = "Three-View Turnaround",
        picture_number: int = None,
        **kwargs,
    ):
        # 1. Base Prompt Validation
        if not isinstance(base_prompt, str) or not base_prompt.strip():
            raise ValueError(
                "Base Prompt must not be empty. Please provide a valid MiniMax H3 Ref2VA prompt."
            )

        if bust_size not in self.INPUT_TYPES()["required"]["bust_size"][0]:
            raise ValueError("Bust size must be one of 01 to 06.")
        if mode != "Three-View Turnaround":
            raise ValueError("Only Three-View Turnaround mode is supported.")
        if ref_image_slot not in self.INPUT_TYPES()["required"]["ref_image_slot"][0]:
            raise ValueError("Ref image slot must be ref_image_0 to ref_image_8.")

        # Slots must be connected contiguously from ref_image_0 in H3.
        if picture_number is not None:
            if type(picture_number) is not int or not 1 <= picture_number <= 9:
                raise ValueError("Picture number must be an integer from 1 to 9.")
            target_pic_num = picture_number
        else:
            target_pic_num = int(ref_image_slot.rsplit("_", 1)[1]) + 1

        # 2. Load Three-View Bust Asset (01 - 06)
        asset_file = ASSET_DIR / f"bust_{bust_size}_3view.png"
        if not asset_file.is_file():
            raise FileNotFoundError(
                f"Three-view bust asset file not found for size '{bust_size}': {asset_file}. "
                "Supported sizes are 01 to 06."
            )

        three_view_tensor = self._load_image_tensor(asset_file)

        # 3. Inject Role Definition Prompt
        modified_prompt = self._inject_three_view_reference(
            base_prompt.strip(),
            picture_number=target_pic_num,
        )

        return (three_view_tensor, modified_prompt)

    @staticmethod
    def _load_image_tensor(filepath: Path) -> torch.Tensor:
        with Image.open(filepath) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
            image_np = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(image_np)[None,]

    @classmethod
    def _inject_three_view_reference(
        cls,
        prompt: str,
        picture_number: int,
    ) -> str:
        target_sentence = (
            f"<Picture {picture_number}> is a three-view upper-body turnaround reference of the same adult woman, "
            "showing right side, front view, and left side. It defines the bust size "
            f"and upper-body proportions of <Subject 1> consistently across viewing angles. "
            "All three views represent the same body proportions from different viewing angles."
        )

        # Upgrade only complete sentences emitted by earlier node versions.
        # Never remove another picture's definition or user-authored text.
        prefix = f"<Picture {picture_number}> is "
        legacy_sentences = {
            prefix + "the upper-body proportion reference for <Subject 1>. "
            "It defines the bust size and upper-body silhouette of <Subject 1>.",
            prefix + "the frontal upper-body proportion reference for <Subject 1>. "
            "It defines the frontal bust size and upper-body silhouette of <Subject 1>.",
            prefix + "the right three-quarter upper-body proportion reference for <Subject 1>. "
            "It defines the three-dimensional bust volume, forward projection, and upper-body silhouette of <Subject 1>.",
            target_sentence.replace("bust size and upper-body", "bust size, bust volume, chest projection, and upper-body"),
        }
        exact_pic_pattern = re.compile(
            rf"^[ \t]*<Picture\s+{picture_number}>[ \t]+is[ \t]+[^\r\n]*",
            re.IGNORECASE | re.MULTILINE,
        )

        if exact_pic_pattern.search(prompt):
            return exact_pic_pattern.sub(
                lambda match: target_sentence
                if match.group(0).strip() in legacy_sentences else match.group(0),
                prompt,
            )

        newline = "\r\n" if "\r\n" in prompt else "\n"
        subj_def_pattern = re.compile(
            r"^[ \t]*subject_definitions:[ \t]*(?:\r?\n|$)",
            re.IGNORECASE | re.MULTILINE,
        )
        if subj_def_pattern.search(prompt):
            return subj_def_pattern.sub(
                lambda match: match.group(0).rstrip("\r\n") + newline + target_sentence + newline,
                prompt, count=1,
            )

        return f"subject_definitions:{newline}{target_sentence}{newline}{newline}{prompt}"
