# Copyright (c) MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import subprocess
import sys
import tempfile
import unittest

import nibabel as nib
import numpy as np
from parameterized import parameterized

from monai.bundle import ConfigParser
from monai.transforms import LoadImage

TEST_CASE_1 = [os.path.join(os.path.dirname(__file__), "testing_data", "inference.json"), (128, 128, 128)]

TEST_CASE_2 = [os.path.join(os.path.dirname(__file__), "testing_data", "inference.yaml"), (128, 128, 128)]


class TestBundleRun(unittest.TestCase):
    @parameterized.expand([TEST_CASE_1, TEST_CASE_2])
    def test_shape(self, config_file, expected_shape):
        test_image = np.random.rand(*expected_shape)
        with tempfile.TemporaryDirectory() as tempdir:
            filename = os.path.join(tempdir, "image.nii")
            nib.save(nib.Nifti1Image(test_image, np.eye(4)), filename)

            # generate default args in a JSON file
            def_args = {"config_file": "will be replaced by `config_file` arg"}
            def_args_file = os.path.join(tempdir, "def_args.json")
            ConfigParser.export_config_file(config=def_args, filepath=def_args_file)

            meta = {"datalist": [{"image": filename}], "output_dir": tempdir, "window": (96, 96, 96)}
            # test YAML file
            meta_file = os.path.join(tempdir, "meta.yaml")
            ConfigParser.export_config_file(config=meta, filepath=meta_file, fmt="yaml")

            # test override with file, up case postfix
            overridefile1 = os.path.join(tempdir, "override1.JSON")
            with open(overridefile1, "w") as f:
                # test override with part of the overriding file
                json.dump({"move_net": "$@network_def.to(@device)"}, f)
            os.makedirs(os.path.join(tempdir, "jsons"), exist_ok=True)
            overridefile2 = os.path.join(tempdir, "jsons/override2.JSON")
            with open(overridefile2, "w") as f:
                # test override with the whole overriding file
                json.dump("Dataset", f)

            saver = LoadImage(image_only=True)

            if sys.platform == "win32":
                override = "--network $@network_def.to(@device) --dataset#_target_ Dataset"
            else:
                override = f"--network %{overridefile1}#move_net --dataset#_target_ %{overridefile2}"
            # test with `monai.bundle` as CLI entry directly
            cmd = f"-m monai.bundle run evaluator --postprocessing#transforms#2#output_postfix seg {override}"
            la = [f"{sys.executable}"] + cmd.split(" ") + ["--meta_file", meta_file] + ["--config_file", config_file]
            test_env = os.environ.copy()
            print(f"CUDA_VISIBLE_DEVICES in {__file__}", test_env.get("CUDA_VISIBLE_DEVICES"))
            ret = subprocess.check_call(la + ["--args_file", def_args_file], env=test_env)
            self.assertEqual(ret, 0)
            self.assertTupleEqual(saver(os.path.join(tempdir, "image", "image_seg.nii.gz")).shape, expected_shape)

            # here test the script with `google fire` tool as CLI
            cmd = "-m fire monai.bundle.scripts run --runner_id evaluator"
            cmd += f" --evaluator#amp False {override}"
            la = [f"{sys.executable}"] + cmd.split(" ") + ["--meta_file", meta_file] + ["--config_file", config_file]
            ret = subprocess.check_call(la, env=test_env)
            self.assertEqual(ret, 0)
            self.assertTupleEqual(saver(os.path.join(tempdir, "image", "image_trans.nii.gz")).shape, expected_shape)


if __name__ == "__main__":
    unittest.main()
