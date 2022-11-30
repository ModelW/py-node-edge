from node_edge import NodeEngine

ne = NodeEngine(
    {
        "dependencies": {
            "axios": "^1.2.0",
        },
        "type": "module",
    }
)

print(ne.package_signature)
print(ne.ensure_env_dir())
print(ne.create_env())
