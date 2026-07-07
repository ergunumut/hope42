import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent / "hope42_cli.py"
spec = importlib.util.spec_from_file_location("hope42_cli", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TestAuthErrorHandling(unittest.TestCase):
    def test_parse_auth_error_mentions_sso_and_api_access(self):
        message = module.describe_auth_failure("error code: 1010", '{"error":"invalid_grant"}')
        self.assertIn("SSO", message)
        self.assertIn("API", message)


if __name__ == "__main__":
    unittest.main()
