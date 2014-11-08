from unittest.mock import ANY
import pexpect

from app.project_type.git import Git
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestGit(BaseUnitTestCase):

    def setUp(self):
        self.patch('app.project_type.git.fs.create_dir')
        self.patch('os.symlink')
        self.mock_pexpect_child = self.patch('pexpect.spawn').return_value
        self.mock_pexpect_child.before = 'None'
        self.mock_pexpect_child.exitstatus = 0
        super().setUp()

    def test_timing_file_path_happy_path(self):
        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin', 'refs/changes/78/151978/27')
        timing_file = git_env.timing_file_path('QUnit')
        self.assertEquals(
            Configuration['base_directory'] +
            '/timings/master/scm.dev.box.net/box/www/current/QUnit.timing.json',
            timing_file
        )

    def test_execute_command_in_project_specifies_cwd_if_exists(self):
        os_path_exists_patch = self.patch('os.path.exists')
        os_path_exists_patch.return_value = True
        project_type_popen_patch = self.patch('app.project_type.project_type.Popen')
        project_type_popen_patch.return_value.communicate.return_value = None, None
        project_type_popen_patch.return_value.returncode = 0

        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin', 'refs/changes/78/151978/27')
        git_env.project_directory = 'proj_dir'
        git_env.execute_command_in_project('some_command')
        project_type_popen_patch.assert_called_once_with(
            'export PROJECT_DIR="proj_dir"; some_command',
            cwd='proj_dir',
            shell=ANY,
            stdout=ANY,
            stderr=ANY,
            start_new_session=ANY,
        )

    def test_execute_command_in_project_type_specifies_cwd_if_doesnt_exist(self):
        os_path_exists_patch = self.patch('os.path.exists')
        os_path_exists_patch.return_value = False
        project_type_popen_patch = self.patch('app.project_type.project_type.Popen')
        project_type_popen_patch.return_value.communicate.return_value = None, None
        project_type_popen_patch.return_value.returncode = 0

        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin', 'refs/changes/78/151978/27')
        git_env.project_directory = 'proj_dir'
        git_env.execute_command_in_project('some_command')
        project_type_popen_patch.assert_called_once_with(
            'export PROJECT_DIR="proj_dir"; some_command',
            cwd=None,
            shell=ANY,
            stdout=ANY,
            stderr=ANY,
            start_new_session=ANY,
        )

    def test_execute_git_remote_command_auto_adds_known_host_if_prompted(self):
        prompted = False

        def expect_side_effect(*args, **kwargs):
            nonlocal prompted

            if args[0] == ['^User.*: ', '^Pass.*: ', '.*Are you sure you want to continue connecting.*'] \
                    and not prompted:
                prompted = True
                return 2
            elif args[0] == pexpect.EOF:
                return 0

            raise pexpect.TIMEOUT('some_msg')

        self.mock_pexpect_child.expect.side_effect = expect_side_effect
        Configuration['git_strict_host_key_checking'] = False
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')
        git._execute_git_remote_command('some_command')
        self.mock_pexpect_child.sendline.assert_called_with("yes")

    def test_execute_git_remote_command_doesnt_auto_add_known_host_if_no_prompt(self):
        def expect_side_effect(*args, **kwargs):
            if args[0] == ['^User.*: ', '^Pass.*: ', '.*Are you sure you want to continue connecting.*']:
                raise pexpect.TIMEOUT('some_msg')
            return None

        self.mock_pexpect_child.expect.side_effect = expect_side_effect
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')
        git._execute_git_remote_command('some_command')
        self.assertEquals(self.mock_pexpect_child.sendline.call_count, 0)

    def test_execute_git_remote_command_raises_exception_if_strict_host_checking_and_prompted(self):
        def expect_side_effect(*args, **kwargs):
            if args[0] == ['^User.*: ', '^Pass.*: ', '.*Are you sure you want to continue connecting.*']:
                return 2
            return None

        self.mock_pexpect_child.expect.side_effect = expect_side_effect
        Configuration['git_strict_host_key_checking'] = True
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')
        self.assertRaises(RuntimeError, git._execute_git_remote_command, 'some_command')
