import subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class ReleaseVersionTest(unittest.TestCase):
    def test_version_parsed_from_header(self):
        out = subprocess.run(["bash", "-c", f'source "{ROOT}/tools/make-release/_release-common.sh" && tr_version "{ROOT}"'],
                             capture_output=True, text=True, check=True).stdout.strip()
        header = (ROOT / "src/TemplateAppVersion.h").read_text()
        self.assertIn(f'"{out}"', header)
        self.assertRegex(out, r"^\d+\.\d+\.\d+$")

if __name__ == "__main__":
    unittest.main()
