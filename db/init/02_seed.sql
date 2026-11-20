-- =====================================================================
--  Демонстрационные данные. Выполняется один раз при инициализации тома.
--  ON CONFLICT защищает от ошибки при повторном запуске скрипта.
-- =====================================================================

INSERT INTO tasks (title, description, status, priority, due_date)
VALUES
    ('Настроить docker-compose', 'Описать сервисы api и db, healthcheck и тома', 'done', 'high', CURRENT_DATE - 2),
    ('Написать Dockerfile (multi-stage)', 'Разделить сборку зависимостей и runtime-образ', 'done', 'high', CURRENT_DATE - 1),
    ('Проверить API в Postman', 'CRUD, фильтры, коды ошибок 400/404/409/422', 'in_progress', 'medium', CURRENT_DATE + 3),
    ('Оформить отчёт по лабораторной работе', 'Скриншоты Postman и листинги', 'todo', 'low', CURRENT_DATE + 7)
ON CONFLICT (title) DO NOTHING;
