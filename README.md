
Скрипт собирает последние 10 твитов с указанных источников, фильтрует их и отправляет в телеграм.

Запуск в docker:
- отредактировать app.py (указать там данные тг chat_id, token)
- docker build -t <имя_образа> .
- docker run -d --name <имя_контейнера> <имя_образа>