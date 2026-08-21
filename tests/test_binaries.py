from pathlib import Path

from node_edge import NodeEngine, default_node_bin, default_npm_command


def test_defaults_fall_back_to_path(monkeypatch):
    import node_edge._binaries as binaries

    monkeypatch.setattr(binaries, "_nodejs_wheel_root", lambda: None)

    assert binaries.default_node_bin() == "node"
    assert binaries.default_npm_command() == ["npm"]


def test_defaults_prefer_nodejs_wheel(monkeypatch, tmp_path):
    import node_edge._binaries as binaries

    monkeypatch.setattr(binaries, "_nodejs_wheel_root", lambda: Path(tmp_path))

    assert binaries.default_node_bin() == f"{tmp_path}/bin/node"
    assert binaries.default_npm_command() == [
        f"{tmp_path}/bin/node",
        f"{tmp_path}/lib/node_modules/npm/bin/npm-cli.js",
    ]


def test_engine_uses_defaults():
    engine = NodeEngine({})

    assert engine.node_bin == default_node_bin()
    assert engine.npm_command == default_npm_command()


def test_engine_explicit_bins_win():
    engine = NodeEngine({}, node_bin="/opt/node", npm_bin="/opt/npm")

    assert engine.node_bin == "/opt/node"
    assert engine.npm_command == ["/opt/npm"]
