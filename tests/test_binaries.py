from node_edge import NodeEngine, default_node_bin, default_npm_bin


def test_defaults_fall_back_to_path(monkeypatch):
    import node_edge._binaries as binaries

    monkeypatch.setattr(binaries, "_nodejs_wheel_bin_dir", lambda: None)

    assert binaries.default_node_bin() == "node"
    assert binaries.default_npm_bin() == "npm"


def test_defaults_prefer_nodejs_wheel(monkeypatch, tmp_path):
    import node_edge._binaries as binaries

    monkeypatch.setattr(binaries, "_nodejs_wheel_bin_dir", lambda: tmp_path)

    assert binaries.default_node_bin() == f"{tmp_path}/node"
    assert binaries.default_npm_bin() == f"{tmp_path}/npm"


def test_engine_uses_defaults():
    engine = NodeEngine({})

    assert engine.node_bin == default_node_bin()
    assert engine.npm_bin == default_npm_bin()


def test_engine_explicit_bins_win():
    engine = NodeEngine({}, node_bin="/opt/node", npm_bin="/opt/npm")

    assert engine.node_bin == "/opt/node"
    assert engine.npm_bin == "/opt/npm"
