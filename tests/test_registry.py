from datagrid_agents.registry import list_definition_slugs, list_definitions, load_definition


def test_expected_construction_agents_exist():
    slugs = list_definition_slugs()
    assert "rfi_reviewer" in slugs
    assert "submittal_checker" in slugs
    assert "safety_observer" in slugs
    assert "schedule_risk" in slugs
    assert "daily_report_summarizer" in slugs
    assert "change_order_analyst" in slugs


def test_load_definition_has_required_fields():
    definition = load_definition("rfi_reviewer")
    assert definition.name
    assert definition.system_prompt
    assert "semantic_search" in definition.tools
    params = definition.create_params(["kn_demo"])
    assert params["name"] == definition.name
    assert params["corpus"] == [{"type": "knowledge", "knowledge_id": "kn_demo"}]


def test_list_definitions_loads_all():
    definitions = list_definitions()
    assert len(definitions) == len(list_definition_slugs())
    assert all(d.slug for d in definitions)
