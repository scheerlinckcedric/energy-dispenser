from pathlib import Path
import struct


ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "energy_dispenser"
EXAMPLES = ROOT / "examples"
DIAGRAMS = ROOT / "docs" / "diagrams"
POWER_MODEL = ROOT / "docs" / "power-model.md"


def test_public_examples_exist() -> None:
    expected = {
        "test-consumer": {"README.md", "requester.yaml"},
        "persistent-consumers": {"README.md"},
        "electric-boiler": {"README.md", "requester.yaml", "processor.yaml"},
        "ev-charger": {"README.md", "requester.yaml", "processor.yaml"},
        "reference": {"digital-report.yaml"},
    }

    assert {path.name for path in EXAMPLES.iterdir() if path.is_file()} == {
        "README.md"
    }
    for folder_name, filenames in expected.items():
        folder = EXAMPLES / folder_name
        assert folder.is_dir()
        assert filenames <= {path.name for path in folder.iterdir() if path.is_file()}


def test_public_diagrams_exist() -> None:
    expected = {
        "architecture.svg",
        "available-power.svg",
    }
    actual = {path.name for path in DIAGRAMS.iterdir() if path.is_file()}
    assert expected <= actual


def test_obsolete_example_diagrams_are_removed() -> None:
    assert not (EXAMPLES / "diagrams").exists()
    obsolete = {
        "system-overview.png",
        "request-allocation-processor.png",
        "allocation-cycle.png",
        "available-power.png",
    }
    assert obsolete.isdisjoint(path.name for path in ROOT.rglob("*"))


def test_examples_teach_matching_requester_and_processor_contracts() -> None:
    boiler = EXAMPLES / "electric-boiler"
    requester = (boiler / "requester.yaml").read_text(encoding="utf-8")
    processor = (boiler / "processor.yaml").read_text(encoding="utf-8")
    assert "minimum_power: 2000" in requester
    assert "preferred_power: 2000" in requester
    assert "maximum_power: 2000" in requester
    assert "above: 1999" in processor

    ev = EXAMPLES / "ev-charger"
    ev_processor = (ev / "processor.yaml").read_text(encoding="utf-8")
    assert 'seconds: "/15"' in ev_processor
    assert "budget / voltage" in ev_processor
    assert "switch.turn_off" in ev_processor


def test_architecture_diagram_preserves_public_boundaries() -> None:
    text = (DIAGRAMS / "architecture.svg").read_text(encoding="utf-8")
    for concept in ("Requester", "Energy Dispenser", "Processor", "Physical device"):
        assert concept in text


def test_readme_describes_authoritative_available_power_and_reporting() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "authoritative **raw source measurement**" in text
    assert "settling ceiling" in text
    assert "`actual_power` regularly" in text
    assert "2 seconds" in text


def test_power_model_documents_feedback_and_distinct_timers() -> None:
    text = POWER_MODEL.read_text(encoding="utf-8")
    assert "raw_available_power" in text
    assert "controlled_actual_power" in text
    assert "Protected floor" in text
    assert "Settling ceiling" in text
    assert "minimum_claim_time" in text
    assert "Device command stability belongs in the processor" in text
    assert "Unit boundary" in text
    assert "must therefore send" in text


def test_actual_power_sensor_is_part_of_the_public_integration() -> None:
    source = (INTEGRATION / "sensor.py").read_text()
    assert "class ActualPowerSensor" in source
    assert "energy_dispenser_actual_power_" in source


def test_legacy_demand_modes_are_not_part_of_the_public_contract() -> None:
    config_flow = (INTEGRATION / "config_flow.py").read_text(encoding="utf-8")
    assert config_flow.count('"demand_mode"') == 1
    assert 'user_input["demand_mode"]' not in config_flow

    paths = [
        INTEGRATION / "requester.py",
        INTEGRATION / "translations" / "en.json",
        INTEGRATION / "translations" / "nl.json",
    ]
    for path in paths:
        assert "demand_mode" not in path.read_text(encoding="utf-8")


def test_hacs_repository_structure() -> None:
    assert (ROOT / "hacs.json").is_file()
    assert (INTEGRATION / "__init__.py").is_file()
    assert (INTEGRATION / "manifest.json").is_file()
    assert (INTEGRATION / "strings.json").is_file()
    assert (INTEGRATION / "brand" / "icon.png").is_file()


def test_brand_icons_have_home_assistant_dimensions() -> None:
    brand = INTEGRATION / "brand"

    for filename, expected_size in (("icon.png", 256), ("icon@2x.png", 512)):
        data = (brand / filename).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == (expected_size, expected_size)


def test_readme_explanation_image_exists() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    image_path = "assets/smart-energy-network.png"

    assert image_path in readme
    assert (ROOT / image_path).is_file()


def test_public_version_is_consistent() -> None:
    import json

    version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
    manifest = json.loads(
        (INTEGRATION / "manifest.json").read_text(encoding="utf-8")
    )
    readme_heading = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]

    assert manifest["version"] == version
    assert readme_heading == f"# Energy Dispenser v{version}"
    assert manifest["documentation"] == (
        "https://github.com/scheerlinckcedric/energy-dispenser"
    )
    assert manifest["issue_tracker"] == (
        "https://github.com/scheerlinckcedric/energy-dispenser/issues"
    )
    assert manifest["codeowners"] == ["@scheerlinckcedric"]
