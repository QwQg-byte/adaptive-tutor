// Neo4j 5.4+ Schema for the current KnowledgeNode / Question model.
// Every statement is idempotent and may be executed repeatedly.

CREATE CONSTRAINT knowledge_node_id_unique IF NOT EXISTS
FOR (n:KnowledgeNode) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT knowledge_node_node_id_unique IF NOT EXISTS
FOR (n:KnowledgeNode) REQUIRE n.node_id IS UNIQUE;

CREATE CONSTRAINT question_id_unique IF NOT EXISTS
FOR (q:Question) REQUIRE q.id IS UNIQUE;

CREATE RANGE INDEX knowledge_node_name_idx IF NOT EXISTS
FOR (n:KnowledgeNode) ON (n.name);

CREATE RANGE INDEX knowledge_node_chapter_id_idx IF NOT EXISTS
FOR (n:KnowledgeNode) ON (n.chapter_id);

CREATE RANGE INDEX question_difficulty_idx IF NOT EXISTS
FOR (q:Question) ON (q.difficulty);

CREATE RANGE INDEX question_category1_idx IF NOT EXISTS
FOR (q:Question) ON (q.category1);

CREATE RANGE INDEX question_category1_id_idx IF NOT EXISTS
FOR (q:Question) ON (q.category1, q.id);

CREATE RANGE INDEX question_difficulty_id_idx IF NOT EXISTS
FOR (q:Question) ON (q.difficulty, q.id);

CREATE FULLTEXT INDEX content_search_fulltext IF NOT EXISTS
FOR (n:KnowledgeNode|Chapter|Question)
ON EACH [n.name, n.title, n.overview, n.description, n.content,
         n.category1, n.category2, n.section]
OPTIONS {indexConfig: {`fulltext.analyzer`: 'cjk',
                       `fulltext.eventually_consistent`: false}};
