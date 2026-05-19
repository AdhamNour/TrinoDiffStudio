import json
import networkx as nx

with open("dbt/target/manifest.json") as f:
    manifest = json.load(f)

G = nx.DiGraph()
for node_id, node in manifest["nodes"].items():
    if node["resource_type"] != "model":
        continue
    G.add_node(node_id)
    for parent in node.get("depends_on", {}).get("nodes", []):
        if parent.startswith("model."):
            G.add_edge(parent, node_id)

# Every cycle lives inside an SCC of size > 1 (or a self-loop)
cycles = [
    scc for scc in nx.strongly_connected_components(G)
    if len(scc) > 1 or (len(scc) == 1 and G.has_edge(next(iter(scc)), next(iter(scc))))
]

for i, scc in enumerate(cycles, 1):
    print(f"Cycle {i} ({len(scc)} models):")
    for m in sorted(scc):
        print(f"  - {m}")
    # If you also want the exact edges forming cycles inside this SCC:
    sub = G.subgraph(scc)
    for c in nx.simple_cycles(sub):
        print("   path:", " -> ".join(c + [c[0]]))