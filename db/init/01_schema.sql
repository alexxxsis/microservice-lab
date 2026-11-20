-- =====================================================================
--  Схема БД микросервиса Task Tracker.
--  Скрипт выполняется автоматически при первом старте контейнера
--  postgres (каталог /docker-entrypoint-initdb.d).
-- =====================================================================

CREATE TABLE IF NOT EXISTS tasks (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(120) NOT NULL UNIQUE,
    description TEXT,
    status      VARCHAR(20)  NOT NULL DEFAULT 'todo',
    priority    VARCHAR(20)  NOT NULL DEFAULT 'medium',
    due_date    DATE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT tasks_title_length_check CHECK (char_length(title) BETWEEN 3 AND 120),
    CONSTRAINT tasks_status_check       CHECK (status IN ('todo', 'in_progress', 'done')),
    CONSTRAINT tasks_priority_check     CHECK (priority IN ('low', 'medium', 'high')),
    CONSTRAINT tasks_description_length_check CHECK (description IS NULL OR char_length(description) <= 1000)
);

COMMENT ON TABLE tasks IS 'Задачи трекера';
COMMENT ON COLUMN tasks.status IS 'Статус: todo | in_progress | done';
COMMENT ON COLUMN tasks.priority IS 'Приоритет: low | medium | high';

CREATE INDEX IF NOT EXISTS tasks_status_idx   ON tasks (status);
CREATE INDEX IF NOT EXISTS tasks_priority_idx ON tasks (priority);
CREATE INDEX IF NOT EXISTS tasks_due_date_idx ON tasks (due_date);

-- Автоматическое обновление updated_at на стороне СУБД:
-- даже если строку изменили напрямую через psql, метка времени будет верной.
CREATE OR REPLACE FUNCTION tasks_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tasks_set_updated_at_trg ON tasks;
CREATE TRIGGER tasks_set_updated_at_trg
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION tasks_set_updated_at();
