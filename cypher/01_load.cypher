// Neo4j 装载脚本（与 out/kg_llm.cypher 等价，含约束与索引）
// 用法：
//   1) 启动 Neo4j 5.x（需 Java 17/21）
//   2) cypher-shell -u neo4j -p <pwd> -f cypher/01_load.cypher
//   3) cypher-shell -u neo4j -p <pwd> -f cypher/02_queries.cypher

// ---------- 1. 约束与索引 ----------
CREATE CONSTRAINT ent_name IF NOT EXISTS FOR (n:Entity) REQUIRE n.name IS UNIQUE;
CREATE INDEX ent_type IF NOT EXISTS FOR (n:Entity) ON (n.type);

// ---------- 2. 节点（52 个） ----------
// 由 src/build_kg.py 自动生成，见 out/kg_llm.cypher；此处示范 3 条
MERGE (n:Entity {name: "孙少平"}) SET n.type = "PER", n.type_cn = "人物";
MERGE (n:Entity {name: "田晓霞"}) SET n.type = "PER", n.type_cn = "人物";
MERGE (n:Entity {name: "煤矿"})   SET n.type = "LOC", n.type_cn = "地点";

// ---------- 3. 关系（77 条） ----------
// 关系类型用反引号包裹，避免中文/特殊字符问题
MATCH (a:Entity {name: "孙少平"}), (b:Entity {name: "田晓霞"})
MERGE (a)-[:`恋人`]->(b);
MATCH (a:Entity {name: "孙少平"}), (b:Entity {name: "煤矿"})
MERGE (a)-[:`任职于`]->(b);

// ---------- 4. 校验 ----------
MATCH (n:Entity) RETURN count(n) AS nodes;
MATCH ()-[r]->() RETURN count(r) AS edges;
