"""The pre-bash owner gate must catch deploy/remote/destructive commands and let ordinary work through."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pb_hooks  # noqa: E402

CASES = {
    "git push origin main": True, "git -C repo push": True, "ssh root@1.2.3.4 ls": True, "ssh-keygen -t ed25519": False,
    "rsync -av ./ root@host:/var/www": True, "php artisan migrate:fresh": True, "php artisan migrate": False,
    "php artisan migrate --force": True, "rm -rf /": True, "rm -fr ~": True, "rm -rf node_modules": False,
    r"Remove-Item -Recurse -Force C:\x": True, r"Remove-Item -Force -Recurse .\dist": True,
    "grep -r 'git push' .": False, "vercel deploy --prod": True, "npm test": False, "echo DROP TABLE x": False,
    "mysql -e 'DROP TABLE x'": True, "plink -batch root@host": True, "composer install": False,
    "echo hi && git push": True, "cat x | ssh host": True, "Get-Content f | Out-Null; git push": True,
    "vercel --prod": True, "npx vercel --prod": True, "php artisan migrate:refresh": True,
    "rm -r -f /": True, "rm --recursive --force /": True, "git status && git diff": False,
}


def gated(command: str) -> bool:
    return pb_hooks.is_risky(command)


class RiskyCommands(unittest.TestCase):
    def test_classification(self):
        wrong = {c: e for c, e in CASES.items() if gated(c) != e}
        self.assertEqual(wrong, {}, f"misclassified (expected gated?): {wrong}")


if __name__ == "__main__":
    unittest.main()
