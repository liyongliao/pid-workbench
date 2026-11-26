import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import support
from site_assets import asset
from cad_runtime import converter_status

class DeploymentTests(unittest.TestCase):
    def test_missing_wrapper_is_distinct_from_missing_engine(self):
        with patch.dict(os.environ,{'PID_DWG_CONVERTER':'/usr/local/bin/pid-oda-headless','PID_DISABLE_DWG_CONVERTER':''}),patch('cad_runtime.platform.system',return_value='Linux'),patch('cad_runtime.os.access',return_value=True):
            result=converter_status()
            self.assertFalse(result['available'])
            self.assertIn('启动器缺失',result['name'])

    def test_site_bootstrap_and_extra_modules_without_core_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);static=root/'code';static.mkdir();site=root/'site/static';site.mkdir(parents=True)
            for name in ('project-settings.js','custom.js','app.js'):(site/name).write_text('// private extension')
            (static/'app.js').write_text('// application')
            self.assertEqual(asset(root,'/project-settings.js',static),(site/'project-settings.js').resolve())
            self.assertEqual(asset(root,'/custom.js',static),(site/'custom.js').resolve())
            self.assertIsNone(asset(root,'/app.js',static))
            self.assertIsNone(asset(root,'/../custom.js',static))
            self.assertIsNone(asset(root,'/data/access-control.json',static))
