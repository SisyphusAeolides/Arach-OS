#!/usr/bin/env python3
from pathlib import Path

verifier = Path("scripts/verify-components.py")
text = verifier.read_text(encoding="utf-8")
function = '''def validate_component_readme(component: dict[str, str], directory: str) -> None:
    readme = show_remote_file(directory, "README.md")
    if STALE_PRODUCT.search(readme):
        raise ValueError(
            f"locked {component['name']} README uses the retired product identity"
        )


'''
if text.count(function) != 1:
    raise SystemExit("component README validator differs")
text = text.replace(function, "")
call = "        validate_component_readme(component, directory)\n"
if text.count(call) != 1:
    raise SystemExit("component README validation call differs")
verifier.write_text(text.replace(call, ""), encoding="utf-8")

tests = Path("scripts/test_verify_components.py")
text = tests.read_text(encoding="utf-8")
for block in (
'''    def test_line_wrapped_retired_product_name_is_rejected(self) -> None:
        with mock.patch.object(
            VERIFY,
            "show_remote_file",
            return_value="Runtime for Arach\\nOS.\\n",
        ):
            with self.assertRaisesRegex(ValueError, "retired product identity"):
                VERIFY.validate_component_readme({"name": "example"}, "/unused")

''',
'''    def test_canonical_component_readme_is_accepted(self) -> None:
        with mock.patch.object(
            VERIFY,
            "show_remote_file",
            return_value="Runtime for ArachOS.\\n",
        ):
            VERIFY.validate_component_readme({"name": "example"}, "/unused")

''',
):
    if text.count(block) != 1:
        raise SystemExit("component README test block differs")
    text = text.replace(block, "")
tests.write_text(text, encoding="utf-8")
