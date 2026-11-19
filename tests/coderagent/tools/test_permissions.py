import pytest

from coderagent.tools.permissions import (
    PermissionMode,
    PermissionPolicy,
    Rule,
    glob_to_regex,
    mode_block,
    mode_note,
    network_block,
    pattern_for,
)


def test_a_rule_with_an_unknown_decision_asks(tmp_path):
    """A decision the policy does not know is not an allow: the user is asked."""
    policy = PermissionPolicy(
        PermissionMode.DEFAULT, [Rule(tool="write", pattern="*.py", decision="Deny")], cwd=tmp_path
    )
    assert policy.check("write", {"path": "a.py"}) == "ask"


def test_a_rule_with_an_unknown_decision_asks_for_bash(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [Rule(tool="bash", pattern=".*", decision="Deny")], cwd=tmp_path)
    assert policy.check("bash", {"command": "pytest -q"}) == "ask"


def test_the_default_mode_allows_reads_and_asks_for_everything_else(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
    assert policy.check("read", {"path": "a.py"}) == "allow"
    assert policy.check("glob", {"pattern": "*"}) == "allow"
    assert policy.check("write", {"path": "a.py"}) == "ask"
    assert policy.check("edit", {"path": "a.py"}) == "ask"
    assert policy.check("bash", {"command": "pytest -q"}) == "ask"


def test_accept_edits_allows_file_writes_but_asks_for_bash(tmp_path):
    policy = PermissionPolicy(PermissionMode.ACCEPT_EDITS, [], cwd=tmp_path)
    assert policy.check("edit", {"path": "a.py"}) == "allow"
    assert policy.check("write", {"path": "a.py"}) == "allow"
    assert policy.check("bash", {"command": "pytest -q"}) == "ask"


@pytest.mark.parametrize("mode", [PermissionMode.PLAN, PermissionMode.READONLY])
def test_plan_and_readonly_deny_every_write(tmp_path, mode):
    policy = PermissionPolicy(mode, [], cwd=tmp_path)
    assert policy.check("read", {"path": "a.py"}) == "allow"
    assert policy.check("write", {"path": "a.py"}) == "deny"
    assert policy.check("bash", {"command": "ls"}) == "deny"


def test_bypass_allows_everything(tmp_path):
    policy = PermissionPolicy(PermissionMode.BYPASS, [], cwd=tmp_path)
    assert policy.check("bash", {"command": "rm -rf build"}) == "allow"
    assert policy.check("write", {"path": "a.py"}) == "allow"


def test_the_strictest_matching_rule_wins(tmp_path):
    rules = [
        Rule(tool="bash", pattern="git status", decision="allow"),
        Rule(tool="bash", pattern="git .*", decision="deny"),
    ]
    policy = PermissionPolicy(PermissionMode.DEFAULT, rules, cwd=tmp_path)
    assert policy.check("bash", {"command": "git status"}) == "deny"


def test_a_deny_rule_is_not_overridden_by_a_later_allow(tmp_path):
    rules = [
        Rule(tool="write", pattern="**/secrets/**", decision="deny", reason="the project says no"),
        Rule(tool="write", pattern="**/secrets/**", decision="allow", reason="explicitly allowed"),
    ]
    policy = PermissionPolicy(PermissionMode.DEFAULT, rules, cwd=tmp_path)
    decision = policy.evaluate("write", {"path": "secrets/key.txt"})
    assert decision.decision == "deny"
    assert decision.reason == "the project says no"


def test_a_deny_rule_of_a_command_is_not_overridden_by_a_later_allow(tmp_path):
    rules = [
        Rule(tool="bash", pattern="git push", decision="deny", reason="no pushing"),
        Rule(tool="bash", pattern="git .*", decision="allow", reason="git is fine"),
    ]
    policy = PermissionPolicy(PermissionMode.DEFAULT, rules, cwd=tmp_path)
    decision = policy.evaluate("bash", {"command": "git push origin main"})
    assert decision.decision == "deny"
    assert decision.reason == "no pushing"


def test_a_later_allow_still_overrides_an_earlier_ask(tmp_path):
    rules = [
        Rule(tool="bash", pattern="pytest", decision="ask", reason="ask first"),
        Rule(tool="bash", pattern="pytest .*", decision="allow", reason="allowed"),
    ]
    policy = PermissionPolicy(PermissionMode.DEFAULT, rules, cwd=tmp_path)
    assert policy.check("bash", {"command": "pytest -q"}) == "allow"


def test_path_rules_are_matched_against_the_path_relative_to_the_working_directory(tmp_path):
    policy = PermissionPolicy(
        PermissionMode.DEFAULT, [Rule(tool="write", pattern="**/tmp/**", decision="allow")], cwd=tmp_path
    )
    assert policy.check("write", {"path": "tmp/a.txt"}) == "allow"
    assert policy.check("write", {"path": "other/a.txt"}) == "ask"


def test_bash_rules_are_matched_as_regular_expressions(tmp_path):
    policy = PermissionPolicy(
        PermissionMode.DEFAULT, [Rule(tool="bash", pattern=r"pytest .*", decision="allow")], cwd=tmp_path
    )
    assert policy.check("bash", {"command": "pytest -k foo"}) == "allow"
    assert policy.check("bash", {"command": "rm -rf build"}) == "ask"


def test_an_invalid_bash_pattern_does_not_match(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [Rule(tool="bash", pattern="[", decision="allow")], cwd=tmp_path)
    assert policy.check("bash", {"command": "anything"}) == "ask"


def test_paths_outside_the_working_directory_are_denied(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
    assert policy.check("write", {"path": "../escape.py"}) == "deny"
    assert policy.check("read", {"path": "/etc/passwd"}) == "deny"


def test_an_include_directory_makes_an_outside_path_allowed(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, include_dirs=[str(tmp_path / "vendor")])
    assert policy.check("read", {"path": str(tmp_path / "vendor" / "lib.py")}) == "allow"


def test_evaluate_reports_the_rule_that_was_hit(tmp_path):
    policy = PermissionPolicy(
        PermissionMode.DEFAULT,
        [Rule(tool="bash", pattern="rm -rf", decision="deny", reason="dangerous")],
        cwd=tmp_path,
    )
    decision = policy.evaluate("bash", {"command": "rm -rf build"})
    assert decision.decision == "deny"
    assert decision.rule.reason == "dangerous"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(PermissionMode.PLAN, "plan mode"), (PermissionMode.READONLY, "read-only mode")],
)
def test_a_refusal_of_the_mode_says_why(tmp_path, mode, expected):
    """A refusal without a reason leaves the model guessing, and it guesses by trying again."""
    policy = PermissionPolicy(mode, [], cwd=tmp_path)
    assert expected in policy.evaluate("write", {"path": "a.py"}).reason
    assert expected in policy.evaluate("bash", {"command": "ls"}).reason


def test_a_refusal_by_a_rule_without_a_reason_still_says_why(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [Rule(tool="write", pattern="**", decision="deny")], cwd=tmp_path)
    assert policy.evaluate("write", {"path": "a.py"}).reason


def test_a_rule_with_a_reason_keeps_it(tmp_path):
    policy = PermissionPolicy(
        PermissionMode.DEFAULT,
        [Rule(tool="write", pattern="**", decision="deny", reason="the project says no")],
        cwd=tmp_path,
    )
    assert policy.evaluate("write", {"path": "a.py"}).reason == "the project says no"


def test_glob_to_regex_does_not_let_a_single_star_cross_a_slash():
    assert glob_to_regex("*.py").match("a.py")
    assert not glob_to_regex("*.py").match("dir/a.py")
    assert glob_to_regex("**/*.py").match("dir/a.py")
    assert glob_to_regex("**/*.py").match("a.py")


def test_the_bookkeeping_tools_never_need_approval(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
    assert policy.check("todo_write", {"todos": []}) == "allow"
    assert policy.check("bash_output", {"task_id": "x"}) == "allow"


@pytest.mark.parametrize("mode", [PermissionMode.PLAN, PermissionMode.READONLY])
def test_the_modes_that_take_tools_away_are_explained_to_the_model(mode):
    assert mode_note(mode)
    assert mode_block(mode).startswith(f'<permission_mode mode="{mode.value}">')
    assert mode_note(mode) in mode_block(mode)


@pytest.mark.parametrize("mode", [PermissionMode.DEFAULT, PermissionMode.ACCEPT_EDITS, PermissionMode.BYPASS])
def test_the_modes_that_take_nothing_away_need_no_explanation(mode):
    assert mode_note(mode) == ""
    assert mode_block(mode) == ""


def test_plan_and_readonly_are_told_different_things():
    assert "plan you would follow" in mode_note(PermissionMode.PLAN)
    assert "describe the change you would make" in mode_note(PermissionMode.READONLY)


def test_an_allow_rule_cannot_open_a_path_outside_the_working_directory(tmp_path):
    """The rules of the user cannot widen the bounds."""
    policy = PermissionPolicy(
        PermissionMode.DEFAULT,
        [Rule(tool="read", pattern="**/etc/passwd", decision="allow")],
        cwd=tmp_path,
    )
    assert policy.check("read", {"path": "/etc/passwd"}) == "deny"


def test_an_allow_rule_cannot_open_a_path_outside_the_working_directory_in_bypass(tmp_path):
    policy = PermissionPolicy(
        PermissionMode.BYPASS,
        [Rule(tool="write", pattern="**/escape.py", decision="allow")],
        cwd=tmp_path,
    )
    assert policy.check("write", {"path": str(tmp_path.parent / "escape.py")}) == "deny"


def test_the_reason_names_the_directories_that_are_open(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, include_dirs=[str(tmp_path / "vendor")])
    decision = policy.evaluate("read", {"path": "/etc/passwd"})
    assert "vendor" in decision.reason


def test_the_commands_that_only_look_around_go_through(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
    assert policy.check("bash", {"command": "ls -la"}) == "allow"
    assert policy.check("bash", {"command": "git status"}) == "allow"
    assert policy.check("bash", {"command": "cat a.py | grep foo"}) == "allow"


def test_a_dangerous_command_asks_and_says_why(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
    decision = policy.evaluate("bash", {"command": "curl http://example.com"})
    assert decision.decision == "ask"
    assert "sends data out" in decision.reason


def test_a_dangerous_command_is_not_blocked_in_bypass(tmp_path):
    policy = PermissionPolicy(PermissionMode.BYPASS, [], cwd=tmp_path)
    assert policy.check("bash", {"command": "curl http://example.com"}) == "allow"


def test_a_rule_is_about_the_beginning_of_the_command(tmp_path):
    rules = [Rule(tool="bash", pattern="git push", decision="deny")]
    policy = PermissionPolicy(PermissionMode.DEFAULT, rules, cwd=tmp_path)
    assert policy.check("bash", {"command": "git push origin main"}) == "deny"
    assert policy.check("bash", {"command": 'echo "git push" file'}) == "allow"


def test_every_part_of_a_command_is_judged_on_its_own(tmp_path):
    rules = [Rule(tool="bash", pattern="pytest", decision="allow")]
    policy = PermissionPolicy(PermissionMode.DEFAULT, rules, cwd=tmp_path)
    assert policy.check("bash", {"command": "pytest -q"}) == "allow"
    assert policy.check("bash", {"command": "pytest -q && rm -rf build"}) == "ask"


def test_a_command_that_reaches_outside_the_working_directory_is_denied(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
    assert policy.check("bash", {"command": "cat /etc/passwd"}) == "deny"
    assert policy.check("bash", {"command": "cat ../secret.txt"}) == "deny"
    assert policy.check("bash", {"command": "cat ~/.ssh/id_rsa"}) == "deny"
    assert policy.check("bash", {"command": "cd .. && ls"}) == "deny"


def test_the_bounds_of_the_disk_hold_in_bypass(tmp_path):
    policy = PermissionPolicy(PermissionMode.BYPASS, [], cwd=tmp_path)
    assert policy.check("bash", {"command": "cat /etc/passwd"}) == "deny"


def test_a_program_of_the_system_may_be_run(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
    assert policy.check("bash", {"command": "/bin/ls"}) != "deny"


def test_a_command_that_writes_with_a_redirection_asks(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
    assert policy.check("bash", {"command": "echo hello > out.txt"}) == "ask"


def test_the_rule_of_an_always_allow_matches_the_command_again(tmp_path):
    pattern = pattern_for("bash", {"command": "pytest -q && echo done"})
    policy = PermissionPolicy(
        PermissionMode.DEFAULT, [Rule(tool="bash", pattern=pattern, decision="allow")], cwd=tmp_path
    )
    assert policy.check("bash", {"command": "pytest -q && echo done"}) == "allow"


def test_a_closed_network_refuses_the_commands_that_reach_it(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, network="deny")
    assert policy.check("bash", {"command": "curl http://example.com"}) == "deny"
    assert policy.check("bash", {"command": "pip install requests"}) == "deny"
    assert policy.check("bash", {"command": "git push origin main"}) == "deny"


def test_a_closed_network_leaves_the_commands_that_stay_at_home(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, network="deny")
    assert policy.check("bash", {"command": "git status"}) == "allow"
    assert policy.check("bash", {"command": "pytest -q"}) == "ask"


def test_a_closed_network_holds_in_bypass(tmp_path):
    policy = PermissionPolicy(PermissionMode.BYPASS, [], cwd=tmp_path, network="deny")
    assert policy.check("bash", {"command": "curl http://example.com"}) == "deny"


def test_an_allow_rule_cannot_open_a_closed_network(tmp_path):
    policy = PermissionPolicy(
        PermissionMode.DEFAULT,
        [Rule(tool="bash", pattern="curl .*", decision="allow")],
        cwd=tmp_path,
        network="deny",
    )
    assert policy.check("bash", {"command": "curl http://example.com"}) == "deny"


def test_the_reason_of_a_closed_network_says_why(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, network="deny")
    decision = policy.evaluate("bash", {"command": "curl http://example.com"})
    assert "the network is closed" in decision.reason
    assert "curl" in decision.reason


def test_an_unknown_network_policy_is_refused():
    with pytest.raises(ValueError, match="unknown network policy"):
        PermissionPolicy(network="maybe")


def test_the_model_is_told_when_the_network_is_closed():
    assert network_block("deny").startswith('<permission_network policy="deny">')
    assert network_block("allow") == ""


def test_a_denied_path_is_denied_for_the_file_tools(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, deny_paths=["*.env", "secrets/**"])
    assert policy.check("read", {"path": ".env"}) == "deny"
    assert policy.check("read", {"path": "secrets/key"}) == "deny"
    assert policy.check("read", {"path": "main.py"}) == "allow"


def test_a_denied_path_is_denied_for_a_command_that_names_it(tmp_path):
    """The path is off limits for the shell too, not only for the file tools."""
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, deny_paths=["*.env", "secrets/**"])
    assert policy.check("bash", {"command": "cat .env"}) == "deny"
    assert policy.check("bash", {"command": "cat secrets/key"}) == "deny"
    assert policy.check("bash", {"command": "cat sub/.env"}) == "deny"
    assert policy.check("bash", {"command": "echo hi > .env"}) == "deny"
    assert policy.check("bash", {"command": "cat main.py"}) == "allow"


def test_a_denied_path_holds_in_bypass(tmp_path):
    policy = PermissionPolicy(PermissionMode.BYPASS, [], cwd=tmp_path, deny_paths=["*.env"])
    assert policy.check("read", {"path": ".env"}) == "deny"
    assert policy.check("bash", {"command": "cat .env"}) == "deny"


def test_an_allow_rule_cannot_open_a_denied_path(tmp_path):
    """The denied paths come after the rules: they win over an allow."""
    policy = PermissionPolicy(
        PermissionMode.DEFAULT,
        [Rule(tool="*", pattern="*", decision="allow")],
        cwd=tmp_path,
        deny_paths=["*.env"],
    )
    assert policy.check("read", {"path": ".env"}) == "deny"
    assert policy.check("read", {"path": "main.py"}) == "allow"


def test_the_reason_of_a_denied_path_says_why(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, deny_paths=["*.env"])
    decision = policy.evaluate("read", {"path": ".env"})
    assert ".env" in decision.reason
    assert "*.env" in decision.reason


def test_a_denied_directory_is_denied_with_the_files_below_it(tmp_path):
    """A search below a denied directory is refused as well."""
    (tmp_path / "secrets").mkdir()
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, deny_paths=["secrets/**"])
    assert policy.check("read", {"path": "secrets"}) == "deny"
    assert policy.check("grep", {"path": "secrets", "pattern": "x"}) == "deny"
    assert policy.check("bash", {"command": "grep -r x secrets"}) == "deny"
