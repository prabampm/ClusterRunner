from contextlib import suppress
import os
import logbook
from unittest import TestCase
from unittest.mock import patch

from app.util import log
from app.util.conf.configuration import Configuration
from app.util.conf.master_config_loader import MasterConfigLoader
from app.util.unhandled_exception_handler import UnhandledExceptionHandler


class BaseUnitTestCase(TestCase):

    _base_setup_called = False

    def setUp(self):
        super().setUp()
        self._set_up_safe_guards()

        # Reset singletons so that they get recreated for every test that uses them.
        Configuration.reset_singleton()
        UnhandledExceptionHandler.reset_singleton()

        # Explicitly initialize UnhandledExceptionHandler singleton here (on the main thread) since it sets up signal
        # handlers that must execute on the main thread.
        UnhandledExceptionHandler.singleton()

        MasterConfigLoader().configure_defaults(Configuration.singleton())
        MasterConfigLoader().configure_postload(Configuration.singleton())
        self.patch('app.util.conf.master_config_loader.MasterConfigLoader.load_from_config_file')

        # Configure logging to go to stdout. This makes debugging easier by allowing us to see logs for failed tests.
        log.configure_logging('DEBUG')
        # Then stub out configure_logging so we don't end up logging to real files during testing.
        self.patch('app.util.log.configure_logging')

        # Set up TestHandler. This allows asserting on log messages in tests.
        self.log_handler = logbook.TestHandler(bubble=True)
        self.log_handler.push_application()

        self._base_setup_called = True

    def tearDown(self):
        # We require super().setUp() to be called for all BaseTestCase subclasses.
        self.assertTrue(self._base_setup_called,
                        '{} must call super().setUp() in its setUp() method.'.format(self.__class__.__name__))

        # Pop all log handlers off the stack so that we start fresh on the next test. This includes the TestHandler
        # pushed in setUp() and any handlers that may have been pushed during test execution.
        with suppress(AssertionError):  # AssertionError is raised once all handlers have been popped off the stack.
            while True:
                logbook.Handler.stack_manager.pop_application()

    def patch(self, target, **kwargs):
        """
        Replaces the specified target with a mock. This is a convenience method on top of unittest.mock.patch.
        This defaults the 'autospec' parameter to True to verify that mock interfaces match the interface of the target.
        It also registers a handler to restore this patch at the end of the current test method.

        :param target: The item (object, method, etc.) to replace with a mock. (See docs for unittest.mock.patch.)
        :type target: str

        :param kwargs: Additional arguments to be passed to unittest.mock.patch
        :type kwargs: dict

        :return: The mock object that target has been replaced with
        :rtype: MagicMock
        """
        # default autospec to True unless 'new' is specified (they are incompatible arguments to patch())
        if 'new' not in kwargs:
            kwargs.setdefault('autospec', True)

        patcher = patch(target, **kwargs)

        try:
            mock = patcher.start()
        except TypeError as ex:
            raise UnitTestPatchError('Could not patch "{}". Has this target already been patched either in this class '
                                     '({}) or in BaseUnitTestCase?'.format(target, self.__class__.__name__)) from ex

        self.addCleanup(patcher.stop)
        return mock

    def patch_abspath(self, abspath_target, cwd='/my_current_directory/'):
        """
        Replace os.path.abspath with a function that behaves similarly, but predictably. This replacement will just
        prepend the input path with the specified fake cwd.

        :param abspath_target: The target to supply to self.patch(), e.g. "module_under_test.os.path.abspath"
        :type abspath_target: str
        :param cwd: The fake current working directory that will be prepended to non-absolute input paths
        :type cwd: str
        """
        def fake_abspath(path):
            if not os.path.isabs(path):
                path = os.path.join(cwd, path)
            return path

        patched_abspath = self.patch(abspath_target)
        patched_abspath.side_effect = fake_abspath
        return patched_abspath

    def _set_up_safe_guards(self):
        """
        This method allows us to raise an exception if a member is invoked.
        To safe guard a method, pass in the name to patch, and the reason
        why we should safeguard it.

        Test writers can apply their own patches by patching in their respective
        test classes setUp() before calling super().setUp().
        """
        safeguarded_packages = {
            'filesystem side effects': [
                'os.chmod',
                'os.killpg',
                'os.makedirs',
                'os.remove',
                'os.rename',
                'os.rmdir',
                'shutil.rmtree',
                'app.util.fs.extract_tar',
                'app.util.fs.compress_directory',
                'app.util.fs.compress_directories',
                'app.util.fs.create_dir',
                'app.util.fs.write_file',
            ],
            'launching child processes': [
                # 'subprocess.Popen.__init__',  # todo: Fix tests that break when we uncomment this.
            ]
        }
        for disabled_reason, patch_targets in safeguarded_packages.items():
            for patch_target in patch_targets:
                # Suppress UnitTestPatchError which happens if target has already been patched (no safeguard needed).
                with suppress(UnitTestPatchError):
                    self._safe_guard(patch_target, disabled_reason)

    def _safe_guard(self, patch_target, disabled_reason):
        message = '"{}" must be explicitly patched in this unit test to avoid {}.'.format(
            patch_target,
            disabled_reason
        )
        self.patch(patch_target, side_effect=[UnitTestDisabledMethodError(message)])


class UnitTestDisabledMethodError(Exception):
    pass


class UnitTestPatchError(Exception):
    pass