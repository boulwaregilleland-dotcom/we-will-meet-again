import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from network_events import NetworkEvents
import portable_app as app


class EventTests(unittest.TestCase):
    def test_real_windows_callback_and_release(self):
        watcher=NetworkEvents(initial=True)
        try:
            self.assertEqual(len(watcher.handles),2)
            self.assertTrue(watcher.event.wait(3))
        finally:
            watcher.close()
        self.assertEqual(watcher.handles,[])

    def test_native_event_wakes_wait_without_network_query(self):
        watcher=NetworkEvents()
        try:
            with tempfile.TemporaryDirectory() as folder:
                cfg=Path(folder)/'test.cfg'
                cfg.write_text('fictional')
                watcher.event.set()
                start=time.monotonic()
                self.assertEqual(watcher.wait(300,cfg,cfg.stat().st_mtime_ns),'network')
                self.assertLess(time.monotonic()-start,2)
                watcher.event.clear()
                cfg.unlink()
                self.assertEqual(watcher.wait(300,cfg,1),'config')
        finally:
            watcher.close()

    def test_stable_worker_waits_five_minutes(self):
        with patch.object(app,'CONFIG') as config, \
             patch.object(app,'protect',return_value=b'{"username":"u","password":"p"}'), \
             patch.object(app,'connection_for_config',return_value=('10.0.0.1',{'transport':'wired','service':'campus'},None)) as probe, \
             patch.object(app,'online',return_value=True),patch.object(app,'notify_success'), \
             patch.object(app,'set_state'),patch.object(app,'RotatingFileHandler',return_value=app.logging.NullHandler()):
            config.exists.return_value=True
            config.stat.return_value.st_mtime_ns=1
            watcher=Mock()
            def stop(*args):config.exists.return_value=False
            watcher.wait.side_effect=stop
            app.worker_loop(watcher)
            watcher.wait.assert_called_once_with(300,config,1)
            self.assertEqual(probe.call_count,1)


if __name__=='__main__':unittest.main()
