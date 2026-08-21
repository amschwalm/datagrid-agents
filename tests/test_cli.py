from datagrid_agents.cli import main


def test_list_local_definitions_exits_zero(capsys):
    code = main(["list"])
    captured = capsys.readouterr()
    assert code == 0
    assert "rfi_reviewer" in captured.out
    assert "Construction RFI Reviewer" in captured.out


def test_show_definition(capsys):
    code = main(["show", "safety_observer"])
    captured = capsys.readouterr()
    assert code == 0
    assert "system_prompt:" in captured.out
    assert "jobsite safety" in captured.out.lower()
