# Neo4j AuraDB Free First

JIMS-AI uses Neo4j Aura as the day-one cloud graph runtime for causal graph, concept lattice, entity relationship, dependency, and temporal links.

Use **AuraDB Free** first. The Professional trial shown in the Neo4j console is not free after the trial ends; at 1GB it becomes roughly `$0.09/hour`, about `$65.70/month`, unless the instance is deleted or billing is accepted intentionally.

Required production variables:

```text
JIMS_GRAPH_PROVIDER=neo4j_aura
JIMS_ENABLE_NEO4J=true
NEO4J_URI=neo4j+s://...
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
NEO4J_DATABASE=neo4j
```

Recommended path:

1. Delete the AuraDB Professional trial before it expires if you do not want billing.
2. Create an AuraDB Free instance.
3. Copy its connection URI, username, password, and database into `.env`.
4. Keep `JIMS_ENABLE_NEO4J=true` so strict startup verifies the cloud graph.

AuraDB Free is suitable for initial cloud setup and early project-memory graphs. Move to AuraDB Professional pay-as-you-go only when the graph grows beyond the free limits or needs production features such as backups, higher performance, and support.
