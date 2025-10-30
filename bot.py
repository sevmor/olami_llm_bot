import telebot
import ollama
import json
import logging
from datetime import datetime
from typing import Dict, List
import os
import venv

# Настройки
BOT_TOKEN = MY_TOKEN
MODEL_NAME = 'qwen2.5:3b'
LOG_FILE = 'chat_history.log'
FAQ_FILE = 'faq.txt'

# Параметры модели (можно настраивать)
MODEL_OPTIONS = {
    'temperature': 0.8,  # Креативность (0.0-2.0)
    'num_ctx': 4096,  # Размер контекста (память)
    'top_p': 0.9,  # Nucleus sampling
    'top_k': 40,  # Top-K sampling
    'repeat_penalty': 1.1,  # Штраф за повторения
    'seed': 42  # Для воспроизводимости (опционально)
}

# Хранилище истории чатов для каждого пользователя
chat_histories: Dict[int, List[Dict]] = {}

# Глобальная переменная для хранения FAQ
FAQ_CONTENT = ""

# Настройка логирования
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    encoding='utf-8'
)

bot = telebot.TeleBot(BOT_TOKEN)


def load_faq() -> str:
    """Загрузка FAQ из файла"""
    global FAQ_CONTENT
    try:
        if os.path.exists(FAQ_FILE):
            with open(FAQ_FILE, 'r', encoding='utf-8') as f:
                FAQ_CONTENT = f.read().strip()
            print(f"✅ FAQ загружен из {FAQ_FILE} ({len(FAQ_CONTENT)} символов)")
            return FAQ_CONTENT
        else:
            print(f"⚠️ Файл {FAQ_FILE} не найден. Создайте его для добавления базы знаний.")
            FAQ_CONTENT = ""
            return ""
    except Exception as e:
        print(f"❌ Ошибка при загрузке FAQ: {str(e)}")
        FAQ_CONTENT = ""
        return ""


def log_message(user_id: int, username: str, role: str, content: str):
    """Логирование сообщений в файл"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'user_id': user_id,
        'username': username,
        'role': role,
        'content': content
    }
    logging.info(json.dumps(log_entry, ensure_ascii=False))


def get_chat_history(user_id: int) -> List[Dict]:
    """Получение истории чата пользователя с системным промптом"""
    if user_id not in chat_histories:
        # Инициализация истории с системным промптом
        system_prompt = "Ты - полезный AI-ассистент. Отвечай на вопросы подробно и точно."

        # Если FAQ загружен, добавляем его в системный промпт
        if FAQ_CONTENT:
            system_prompt = f"""Ты - полезный AI-ассистент. 

Используй следующую информацию из базы знаний для ответов на вопросы:

=== БАЗА ЗНАНИЙ ===
{FAQ_CONTENT}
===================

Если ответ есть в базе знаний, используй эту информацию.
Если информации нет в базе знаний, можешь использовать свои общие знания.
Отвечай на русском языке, четко и понятно."""

        chat_histories[user_id] = [
            {
                'role': 'system',
                'content': system_prompt
            }
        ]

    return chat_histories[user_id]


def add_to_history(user_id: int, role: str, content: str):
    """Добавление сообщения в историю"""
    history = get_chat_history(user_id)
    history.append({
        'role': role,
        'content': content
    })

    # Ограничение истории (последние 20 сообщений + системный промпт)
    # Системное сообщение всегда первое, поэтому сохраняем его
    if len(history) > 21:  # 1 system + 20 сообщений
        # Удаляем второе сообщение (первое пользовательское)
        history.pop(1)


@bot.message_handler(commands=['start'])
def start_command(message):
    """Команда /start"""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    faq_status = "✅ Загружена" if FAQ_CONTENT else "⚠️ Не загружена"

    welcome_text = (
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        f"Я AI-бот на основе модели {MODEL_NAME}.\n\n"
        f"База знаний: {faq_status}\n\n"
        f"Текущие параметры:\n"
        f"• Температура: {MODEL_OPTIONS['temperature']}\n"
        f"• Контекст: {MODEL_OPTIONS['num_ctx']} токенов\n\n"
        f"Доступные команды:\n"
        f"/start - Начало работы\n"
        f"/clear - Очистить историю\n"
        f"/params - Показать параметры\n"
        f"/settemp <значение> - Установить температуру (0.0-2.0)\n"
        f"/reload_faq - Перезагрузить базу знаний\n"
        f"/faq_status - Статус базы знаний"
    )

    bot.reply_to(message, welcome_text)
    log_message(user_id, username, 'system', '/start command')


@bot.message_handler(commands=['clear'])
def clear_history(message):
    """Очистка истории чата"""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    if user_id in chat_histories:
        # Удаляем историю, при следующем обращении создастся новая с системным промптом
        del chat_histories[user_id]

    bot.reply_to(message, "✅ История чата очищена!")
    log_message(user_id, username, 'system', 'History cleared')


@bot.message_handler(commands=['params'])
def show_params(message):
    """Показать текущие параметры модели"""
    params_text = "⚙️ Текущие параметры модели:\n\n"
    for key, value in MODEL_OPTIONS.items():
        params_text += f"• {key}: {value}\n"

    bot.reply_to(message, params_text)


@bot.message_handler(commands=['settemp'])
def set_temperature(message):
    """Установить температуру модели"""
    try:
        temp = float(message.text.split()[1])
        if 0.0 <= temp <= 2.0:
            MODEL_OPTIONS['temperature'] = temp
            bot.reply_to(message, f"✅ Температура установлена: {temp}")
        else:
            bot.reply_to(message, "❌ Температура должна быть от 0.0 до 2.0")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Использование: /settemp <значение>\nПример: /settemp 0.7")


@bot.message_handler(commands=['reload_faq'])
def reload_faq_command(message):
    """Перезагрузка базы знаний из файла"""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    # Перезагружаем FAQ
    load_faq()

    # Сбрасываем все истории чатов, чтобы обновить системный промпт
    chat_histories.clear()

    if FAQ_CONTENT:
        response_text = f"✅ База знаний перезагружена!\n📄 Размер: {len(FAQ_CONTENT)} символов"
    else:
        response_text = f"⚠️ Файл {FAQ_FILE} пуст или не найден."

    bot.reply_to(message, response_text)
    log_message(user_id, username, 'system', 'FAQ reloaded')


@bot.message_handler(commands=['faq_status'])
def faq_status_command(message):
    """Показать статус базы знаний"""
    if FAQ_CONTENT:
        lines = FAQ_CONTENT.count('\n') + 1
        status_text = (
            f"📚 Статус базы знаний:\n\n"
            f"✅ Загружена\n"
            f"📄 Файл: {FAQ_FILE}\n"
            f"📝 Размер: {len(FAQ_CONTENT)} символов\n"
            f"📋 Строк: {lines}\n\n"
            f"Первые 200 символов:\n{FAQ_CONTENT[:200]}..."
        )
    else:
        status_text = (
            f"📚 Статус базы знаний:\n\n"
            f"⚠️ Не загружена\n"
            f"📄 Ожидаемый файл: {FAQ_FILE}\n\n"
            f"Создайте файл {FAQ_FILE} с вашей информацией."
        )

    bot.reply_to(message, status_text)


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Обработка всех текстовых сообщений"""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user_message = message.text

    # Логирование входящего сообщения
    log_message(user_id, username, 'user', user_message)

    # Добавление в историю
    add_to_history(user_id, 'user', user_message)

    # Отправка "печатает..."
    bot.send_chat_action(message.chat.id, 'typing')

    try:
        # Получение истории для контекста
        history = get_chat_history(user_id)

        # Запрос к Ollama
        response = ollama.chat(
            model=MODEL_NAME,
            messages=history,
            options=MODEL_OPTIONS,
            stream=False
        )

        ai_response = response['message']['content']

        # Добавление ответа в историю
        add_to_history(user_id, 'assistant', ai_response)

        # Логирование ответа
        log_message(user_id, username, 'assistant', ai_response)

        # Отправка ответа
        bot.reply_to(message, ai_response)

    except Exception as e:
        error_message = f"❌ Ошибка: {str(e)}"
        bot.reply_to(message, error_message)
        log_message(user_id, username, 'error', str(e))


if __name__ == '__main__':
    print(f"🚀 Бот запущен с моделью {MODEL_NAME}")
    print(f"📝 Логи сохраняются в {LOG_FILE}")

    # Загружаем FAQ при старте
    load_faq()

    print("⏳ Запуск бота...")
    bot.infinity_polling()
