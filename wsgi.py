import importlib.util
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_FILE = os.path.join(BASE_DIR, "app.py")

spec = importlib.util.spec_from_file_location("ipaper_app", APP_FILE)
module = importlib.util.module_from_spec(spec)

sys.modules["ipaper_app"] = module
spec.loader.exec_module(module)

app = module.app
