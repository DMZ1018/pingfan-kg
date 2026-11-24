// 图谱查询示例（Neo4j / Cypher，Kùzu 亦兼容）
// 每条都对应 src/kg_cypher.py 里被测的查询

// Q1 一度邻居：孙少平直接关联的人与事
MATCH (a:Entity {name: "孙少平"})-[r]->(b:Entity)
RETURN b.name AS 对象, type(r) AS 关系
ORDER BY 对象;

// Q2 两跳：孙少平的关系的关系（发现"恋人的父亲""任职机构的同事"）
MATCH (a:Entity {name: "孙少平"})-[:`恋人`]->(m)-[r2]->(b:Entity)
RETURN m.name AS 中间人, type(r2) AS 二跳关系, b.name AS 对象;

// Q3 度中心性 Top10：谁是故事的枢纽
MATCH (a:Entity)-[r]->()
RETURN a.name AS 人物, count(r) AS 出度
ORDER BY 出度 DESC LIMIT 10;

// Q4 关系类型分布
MATCH ()-[r]->()
RETURN type(r) AS 关系, count(*) AS 次数
ORDER BY 次数 DESC;

// Q5 类型分布
MATCH (n:Entity)
RETURN n.type_cn AS 类型, count(*) AS 数量
ORDER BY 数量 DESC;

// Q6 亲属链：田福堂的子女
MATCH (a:Entity {name: "田福堂"})<-[:`父亲`]-(child:Entity)
RETURN child.name AS 子女;

// Q7 三角关系：谁和谁通过同一个人相连（两跳内闭环）
MATCH (a:Entity {name: "孙少安"})--(m)--(b:Entity)
WHERE a <> b
RETURN DISTINCT b.name AS 间接关联;
