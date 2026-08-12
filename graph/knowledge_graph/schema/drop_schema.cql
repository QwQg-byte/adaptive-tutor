// Remove only the named Schema objects managed by this project.
// Data, lookup indexes and unrelated Schema objects are not touched.

DROP INDEX content_search_fulltext IF EXISTS;
DROP INDEX question_difficulty_id_idx IF EXISTS;
DROP INDEX question_category1_id_idx IF EXISTS;
DROP INDEX question_category1_idx IF EXISTS;
DROP INDEX question_difficulty_idx IF EXISTS;
DROP INDEX knowledge_node_chapter_id_idx IF EXISTS;
DROP INDEX knowledge_node_name_idx IF EXISTS;

DROP CONSTRAINT question_id_unique IF EXISTS;
DROP CONSTRAINT knowledge_node_node_id_unique IF EXISTS;
DROP CONSTRAINT knowledge_node_id_unique IF EXISTS;
