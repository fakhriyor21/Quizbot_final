"""
Uzbek Quiz Bot - Hammasi bitta faylda
Rivojlangan: 2024
Dasturchi: Faxriyor Sadullayev
Texnologiyalar: aiogram 2.14, SQLite, FSM
Til: O'zbek tili (barcha interfeyslar)
"""

import asyncio
import sqlite3
import logging
import csv
import io
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery, Message, InputFile
)
from aiogram.utils import executor
from aiogram.utils.exceptions import BadRequest

# -------------------- KONFIGURATSIYA -------------------- #
BOT_TOKEN = "8595175650:AAGAPtiNeFf32kdPYrl6WA2DU6CV2SdP3ng"  # @BotFather dan oling
ADMIN_ID = 6777571934  # O'zingizning Telegram ID
CHANNEL_ID = "@testlar231"  # Kanal username yoki ID

# Uzbek viloyatlari
UZBEK_REGIONS = [
    "Toshkent shahri",
    "Toshkent viloyati",
    "Andijon viloyati",
    "Buxoro viloyati",
    "Farg'ona viloyati",
    "Jizzax viloyati",
    "Xorazm viloyati",
    "Namangan viloyati",
    "Navoiy viloyati",
    "Qashqadaryo viloyati",
    "Samarqand viloyati",
    "Sirdaryo viloyati",
    "Surxondaryo viloyati",
    "Qoraqalpog'iston Respublikasi"
]

# Stickerlar
STICKERS = {
    "correct": "CAACAgIAAxkBAAEL-Z5mM2-MC4_WN_j4b-y2Z4ZQ-_nP4wAC_QADVp29Cmg82SHSGBhUNAQ",
    "incorrect": "CAACAgIAAxkBAAEL-aBmM2-vqQOWHjDRg5Q2e0lY-hD4wQACFgADwZxgDGh6AAHp9XQY1zQE",
    "welcome": "CAACAgIAAxkBAAEL-aJmM3AQ2jVxVCMlSuWstmrwEwLAAgACbgADVp29Cg-F6_SQ52WuNAQ",
    "celebration": "CAACAgIAAxkBAAEL-aRmM3A0SHtQj60KKCJwG6q61qPvVAACKQADVp29CpVlbYcAAVJxLzQE",
    "leaderboard": "CAACAgIAAxkBAAEL-aZmM3Ba_gPyJtOAAXwUWiXm0HZQH_UAAlMAA1advQrKVs9R29YP5TQE",
    "new_test": "CAACAgIAAxkBAAEMAAFlmT5JjLazI74LmRO0FYK3SSTy5qIAAjEAA1advQrfvDIfq3peDTQE"
}

# Rangli progress bar uchun emojilar
PROGRESS_BAR = ["⬜", "⬜", "⬜", "⬜", "⬜", "⬜", "⬜", "⬜", "⬜", "⬜"]
FILLED_PROGRESS = "🟩"

# -------------------- HOLATLAR (FSM) -------------------- #
class RegistrationStates(StatesGroup):
    ism = State()
    familiya = State()
    telefon = State()
    maktab = State()
    oquv_markazi = State()
    viloyat = State()
    tuman = State()

# ==================== O'ZGARTIRISH: YANGI ADMIN HOLATLARI ==================== #
class AdminStates(StatesGroup):
    waiting_for_test_key = State()
    waiting_for_answer_key = State()
    # Eski holatlar (saqlab qo'yish uchun)
    test_nomi = State()
    test_savollari = State()
    savol_matni = State()
    variantlar = State()
    togri_javob = State()
    edit_test_choice = State()
    edit_savol = State()
    send_test_id = State()

class QuizStates(StatesGroup):
    javob_kutish = State()
    test_tanlash = State()

# -------------------- DATABASE CLASS -------------------- #
class Database:
    def __init__(self, db_name="quiz_bot.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        self.upgrade_database()  # Yangi maydonlarni qo'shish

    def create_tables(self):
        cursor = self.conn.cursor()

        # Foydalanuvchilar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                ism TEXT,
                familiya TEXT,
                telefon TEXT,
                maktab TEXT,
                oquv_markazi TEXT,
                viloyat TEXT,
                tuman TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Testlar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nomi TEXT,
                savollar_soni INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        ''')

        # sent_to_channel maydoni yo'qligini tekshirish va qo'shish
        try:
            cursor.execute("ALTER TABLE tests ADD COLUMN sent_to_channel INTEGER DEFAULT 0")
            print("✅ sent_to_channel maydoni qo'shildi")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"⚠️ sent_to_channel qo'shishda xato: {e}")

        # channel_message_id maydonini qo'shish
        try:
            cursor.execute("ALTER TABLE tests ADD COLUMN channel_message_id TEXT")
            print("✅ channel_message_id maydoni qo'shildi")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"⚠️ channel_message_id qo'shishda xato: {e}")

        # Savollar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER,
                savol_matni TEXT,
                variant_a TEXT,
                variant_b TEXT,
                variant_c TEXT,
                variant_d TEXT,
                togri_javob TEXT,
                FOREIGN KEY (test_id) REFERENCES tests (id)
            )
        ''')

        # Natijalar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                test_id INTEGER,
                togri_javoblar INTEGER,
                umumiy_savollar INTEGER,
                foiz REAL,
                vaqt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (telegram_id),
                FOREIGN KEY (test_id) REFERENCES tests (id)
            )
        ''')

        # User answers jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                test_id INTEGER,
                question_id INTEGER,
                user_answer TEXT,
                is_correct INTEGER,
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (telegram_id),
                FOREIGN KEY (test_id) REFERENCES tests (id),
                FOREIGN KEY (question_id) REFERENCES questions (id)
            )
        ''')

        self.conn.commit()

    def upgrade_database(self):
        """Mavjud bazani yangilash"""
        cursor = self.conn.cursor()

        # sent_to_channel maydonini qo'shish
        try:
            cursor.execute("SELECT sent_to_channel FROM tests LIMIT 1")
            print("✅ sent_to_channel maydoni mavjud")
        except sqlite3.OperationalError:
            try:
                cursor.execute("ALTER TABLE tests ADD COLUMN sent_to_channel INTEGER DEFAULT 0")
                print("✅ sent_to_channel maydoni qo'shildi")
            except Exception as e:
                print(f"⚠️ sent_to_channel qo'shishda xato: {e}")

        # channel_message_id maydonini qo'shish
        try:
            cursor.execute("SELECT channel_message_id FROM tests LIMIT 1")
            print("✅ channel_message_id maydoni mavjud")
        except sqlite3.OperationalError:
            try:
                cursor.execute("ALTER TABLE tests ADD COLUMN channel_message_id TEXT")
                print("✅ channel_message_id maydoni qo'shildi")
            except Exception as e:
                print(f"⚠️ channel_message_id qo'shishda xato: {e}")

        self.conn.commit()
        print("✅ Database muvaffaqiyatli yangilandi!")

    # ----------- Foydalanuvchilar ----------- #
    def add_user(self, telegram_id: int, ism: str, familiya: str, telefon: str,
                maktab: str, oquv_markazi: str, viloyat: str, tuman: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (telegram_id, ism, familiya, telefon, maktab, oquv_markazi, viloyat, tuman)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (telegram_id, ism, familiya, telefon, maktab, oquv_markazi, viloyat, tuman))
        self.conn.commit()
        return cursor.lastrowid

    def get_user(self, telegram_id: int):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return cursor.fetchone()

    def is_user_registered(self, telegram_id: int):
        return self.get_user(telegram_id) is not None

    def get_all_users(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY id DESC")
        return cursor.fetchall()

    # ----------- Testlar ----------- #
    def add_test(self, nomi: str, savollar_soni: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO tests (nomi, savollar_soni) VALUES (?, ?)
        ''', (nomi, savollar_soni))
        self.conn.commit()
        return cursor.lastrowid

    def update_test_channel_message(self, test_id: int, message_id: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE tests SET channel_message_id = ?, sent_to_channel = 1 WHERE id = ?
        ''', (message_id, test_id))
        self.conn.commit()

    def mark_test_sent(self, test_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE tests SET sent_to_channel = 1 WHERE id = ?
        ''', (test_id,))
        self.conn.commit()

    def add_question(self, test_id: int, savol_matni: str, variant_a: str,
                    variant_b: str, variant_c: str, variant_d: str, togri_javob: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO questions 
            (test_id, savol_matni, variant_a, variant_b, variant_c, variant_d, togri_javob)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (test_id, savol_matni, variant_a, variant_b, variant_c, variant_d, togri_javob))
        self.conn.commit()
        return cursor.lastrowid

    def get_all_tests(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tests ORDER BY id DESC")
        return cursor.fetchall()

    def get_active_tests(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tests WHERE is_active = 1 ORDER BY id DESC")
        return cursor.fetchall()

    def get_test(self, test_id: int):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tests WHERE id = ?", (test_id,))
        return cursor.fetchone()

    def get_questions(self, test_id: int):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM questions WHERE test_id = ? ORDER BY id", (test_id,))
        return cursor.fetchall()

    def get_question(self, question_id: int):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
        return cursor.fetchone()

    def update_question(self, question_id: int, savol_matni: str, variant_a: str,
                       variant_b: str, variant_c: str, variant_d: str, togri_javob: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE questions 
            SET savol_matni = ?, variant_a = ?, variant_b = ?, variant_c = ?, variant_d = ?, togri_javob = ?
            WHERE id = ?
        ''', (savol_matni, variant_a, variant_b, variant_c, variant_d, togri_javob, question_id))
        self.conn.commit()

    def delete_test(self, test_id: int):
        cursor = self.conn.cursor()
        # Testga bog'liq savollarni o'chirish
        cursor.execute("DELETE FROM questions WHERE test_id = ?", (test_id,))
        # Natijalarni o'chirish
        cursor.execute("DELETE FROM results WHERE test_id = ?", (test_id,))
        # User answers ni o'chirish
        cursor.execute("DELETE FROM user_answers WHERE test_id = ?", (test_id,))
        # Testni o'chirish
        cursor.execute("DELETE FROM tests WHERE id = ?", (test_id,))
        self.conn.commit()

    def delete_question(self, question_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        self.conn.commit()

    # ----------- User Answers ----------- #
    def save_user_answer(self, user_id: int, test_id: int, question_id: int,
                        user_answer: str, is_correct: bool):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO user_answers 
            (user_id, test_id, question_id, user_answer, is_correct)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, test_id, question_id, user_answer, 1 if is_correct else 0))
        self.conn.commit()

    def get_user_test_answers(self, user_id: int, test_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT ua.*, q.savol_matni, q.togri_javob
            FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = ? AND ua.test_id = ?
            ORDER BY ua.answered_at
        ''', (user_id, test_id))
        return cursor.fetchall()

    # ----------- Natijalar ----------- #
    def save_result(self, user_id: int, test_id: int, togri_javoblar: int, umumiy_savollar: int):
        foiz = (togri_javoblar / umumiy_savollar) * 100 if umumiy_savollar > 0 else 0
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO results (user_id, test_id, togri_javoblar, umumiy_savollar, foiz)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, test_id, togri_javoblar, umumiy_savollar, foiz))
        self.conn.commit()
        return foiz

    def get_user_results(self, user_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT r.*, t.nomi as test_nomi 
            FROM results r 
            JOIN tests t ON r.test_id = t.id 
            WHERE r.user_id = ? 
            ORDER BY r.vaqt DESC
        ''', (user_id,))
        return cursor.fetchall()

    def get_test_results(self, test_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT r.*, u.ism, u.familiya, u.maktab
            FROM results r
            JOIN users u ON r.user_id = u.telegram_id
            WHERE r.test_id = ?
            ORDER BY r.foiz DESC, r.vaqt ASC
        ''', (test_id,))
        return cursor.fetchall()

    def get_leaderboard(self, test_id: int = None, limit: int = 10):
        cursor = self.conn.cursor()
        if test_id:
            cursor.execute('''
                SELECT u.ism, u.familiya, r.togri_javoblar, r.umumiy_savollar, 
                       r.foiz, r.vaqt, u.maktab
                FROM results r
                JOIN users u ON r.user_id = u.telegram_id
                WHERE r.test_id = ?
                ORDER BY r.foiz DESC, r.vaqt ASC
                LIMIT ?
            ''', (test_id, limit))
        else:
            cursor.execute('''
                SELECT u.ism, u.familiya, 
                       SUM(r.togri_javoblar) as total_correct,
                       SUM(r.umumiy_savollar) as total_questions,
                       AVG(r.foiz) as avg_percentage,
                       u.maktab,
                       u.telegram_id
                FROM results r
                JOIN users u ON r.user_id = u.telegram_id
                GROUP BY r.user_id
                HAVING total_questions > 0
                ORDER BY avg_percentage DESC, total_correct DESC
                LIMIT ?
            ''', (limit,))
        return cursor.fetchall()

    def get_user_position(self, user_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT ranking FROM (
                SELECT u.telegram_id, 
                       AVG(r.foiz) as avg_percentage,
                       ROW_NUMBER() OVER (ORDER BY AVG(r.foiz) DESC) as ranking
                FROM results r
                JOIN users u ON r.user_id = u.telegram_id
                GROUP BY r.user_id
                HAVING COUNT(r.id) > 0
            ) WHERE telegram_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_today_stats(self):
        cursor = self.conn.cursor()
        today = datetime.now().date().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT 
                COUNT(DISTINCT user_id) as active_users,
                COUNT(*) as tests_taken
            FROM results
            WHERE DATE(vaqt) = ?
        ''', (today,))
        result = cursor.fetchone()
        return {'active_users': result[0] if result else 0,
                'tests_taken': result[1] if result else 0}

    def get_total_stats(self):
        cursor = self.conn.cursor()

        # Foydalanuvchilar soni
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        # Testlar soni
        cursor.execute("SELECT COUNT(*) FROM tests")
        total_tests = cursor.fetchone()[0]

        # Natijalar soni
        cursor.execute("SELECT COUNT(*) FROM results")
        total_results = cursor.fetchone()[0]

        # Sent to channel testlar soni
        try:
            cursor.execute("SELECT COUNT(*) FROM tests WHERE sent_to_channel = 1")
            sent_tests = cursor.fetchone()[0]
        except:
            sent_tests = 0

        return {
            'total_users': total_users,
            'total_tests': total_tests,
            'total_results': total_results,
            'sent_tests': sent_tests
        }

    # ----------- Eksport ----------- #
    def export_users_csv(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY id")
        users = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)

        # Sarlavhalar
        writer.writerow(['ID', 'Telegram ID', 'Ism', 'Familiya', 'Telefon',
                        'Maktab', 'O\'quv Markazi', 'Viloyat', 'Tuman', 'Ro\'yxatdan o\'tgan sana'])

        # Ma'lumotlar
        for user in users:
            writer.writerow([
                user['id'], user['telegram_id'], user['ism'], user['familiya'],
                user['telefon'], user['maktab'], user['oquv_markazi'],
                user['viloyat'], user['tuman'], user['registered_at']
            ])

        return output.getvalue()

    def export_results_csv(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT r.*, u.ism, u.familiya, t.nomi as test_nomi
            FROM results r
            JOIN users u ON r.user_id = u.telegram_id
            JOIN tests t ON r.test_id = t.id
            ORDER BY r.vaqt DESC
        ''')
        results = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)

        # Sarlavhalar
        writer.writerow(['ID', 'User ID', 'Test ID', 'Test Nomi', 'Ism', 'Familiya',
                        'To\'g\'ri javoblar', 'Umumiy savollar', 'Foiz', 'Vaqt'])

        # Ma'lumotlar
        for result in results:
            writer.writerow([
                result['id'], result['user_id'], result['test_id'], result['test_nomi'],
                result['ism'], result['familiya'], result['togri_javoblar'],
                result['umumiy_savollar'], f"{result['foiz']:.1f}%", result['vaqt']
            ])

        return output.getvalue()

# ==================== ASOSIY BOT CLASS - FAQAT TEST YARATISH O'ZGARTIRILDI ==================== #
class UzbekQuizBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(self.bot, storage=self.storage)
        self.db = Database()
        self.user_sessions = {}  # {user_id: {current_test: x, current_question: y, answers: []}}
        self.setup_handlers()

    def setup_handlers(self):
        # Start command
        self.dp.register_message_handler(self.start_command, commands=['start'])

        # Registration handlers
        self.dp.register_message_handler(self.start_registration, commands=['register'])
        self.dp.register_message_handler(self.process_ism, state=RegistrationStates.ism)
        self.dp.register_message_handler(self.process_familiya, state=RegistrationStates.familiya)
        self.dp.register_message_handler(self.process_telefon, state=RegistrationStates.telefon)
        self.dp.register_message_handler(self.process_maktab, state=RegistrationStates.maktab)
        self.dp.register_message_handler(self.process_oquv_markazi, state=RegistrationStates.oquv_markazi)
        self.dp.register_message_handler(self.process_viloyat, state=RegistrationStates.viloyat)
        self.dp.register_message_handler(self.process_tuman, state=RegistrationStates.tuman)

        # Quiz handlers
        self.dp.register_message_handler(self.show_main_menu, commands=['menu'])
        self.dp.register_callback_query_handler(self.handle_callback, lambda c: True)
        self.dp.register_message_handler(self.process_answer, state=QuizStates.javob_kutish)

        # ==================== O'ZGARTIRISH: YANGI ADMIN HANDLERLAR ==================== #
        # YANGI: Test yaratish (sizning formatda)
        self.dp.register_message_handler(self.cmd_create_test, commands=['create_test'])
        self.dp.register_message_handler(self.test_key_received, state=AdminStates.waiting_for_test_key)
        self.dp.register_message_handler(self.answer_key_received, state=AdminStates.waiting_for_answer_key)
        
        # ESKI: Test yaratish (savol-savol) - nomini o'zgartirish
        self.dp.register_message_handler(self.create_test_start_old, commands=['create_test_old'])
        
        # Qolgan admin handlerlar o'zgarmasligi kerak
        self.dp.register_message_handler(self.admin_panel_command, commands=['admin'])
        self.dp.register_message_handler(self.admin_list_tests_command, commands=['list_tests'])
        self.dp.register_message_handler(self.admin_edit_tests_command, commands=['edit_tests'])
        self.dp.register_message_handler(self.admin_send_test_command, commands=['send_test'])

        # Eski admin state handlers (saqlab qo'yish uchun)
        self.dp.register_message_handler(self.process_test_nomi, state=AdminStates.test_nomi)
        self.dp.register_message_handler(self.process_savol_soni, state=AdminStates.test_savollari)
        self.dp.register_message_handler(self.process_savol_matni, state=AdminStates.savol_matni)
        self.dp.register_message_handler(self.process_variantlar, state=AdminStates.variantlar)
        self.dp.register_message_handler(self.process_togri_javob, state=AdminStates.togri_javob)

        # Statistics
        self.dp.register_message_handler(self.show_stats_command, commands=['stats'])
        self.dp.register_message_handler(self.show_my_results_command, commands=['myresults'])
        self.dp.register_message_handler(self.show_leaderboard_command, commands=['leaderboard'])

    def is_admin(self, user_id: int):
        """Foydalanuvchi admin ekanligini tekshirish"""
        return user_id == ADMIN_ID

    # ==================== YANGI TEST YARATISH FUNKSIYALARI ==================== #
    async def cmd_create_test(self, message: types.Message):
        """Yangi test yaratish (sizning formatda)"""
        if not self.is_admin(message.from_user.id):
            await message.answer("❌ *Siz admin emassiz!*", parse_mode="Markdown")
            return
        
        await message.reply("Test kalitini kiriting (masalan: FRONTEND-01).")
        await AdminStates.waiting_for_test_key.set()

    async def test_key_received(self, message: types.Message, state: FSMContext):
        """Test kalitini qabul qilish"""
        text = message.text.strip().upper()
        await state.update_data(test_key=text)
        await message.reply("To'g'ri javob kalitini yuboring (masalan: 1a2b3c).")
        await AdminStates.waiting_for_answer_key.set()

    async def answer_key_received(self, message: types.Message, state: FSMContext):
        """Javob kalitini qabul qilish"""
        data = await state.get_data()
        test_key = data.get("test_key")
        answer_key = message.text.strip()
        
        # Bazaga test nomi sifatida test_key ni saqlash
        ok = self.db.add_test(test_key, 0)  # savollar_soni=0, keyin qo'shiladi
        
        if ok:
            # Test ID ni olish
            test = self.db.get_test(ok)
            if test:
                await message.reply(f"✅ Test {test_key} saqlandi.\n\n"
                                  f"🔑 Test kaliti: {test_key}\n"
                                  f"🔐 Javob kaliti: {answer_key}\n"
                                  f"🆔 Test ID: {ok}\n\n"
                                  f"📝 Endi savollar qo'shish uchun /edit_tests buyrug'idan foydalanib, "
                                  f"'{test_key}' testini tanlang va savollar qo'shing.")
            else:
                await message.reply(f"✅ Test {test_key} saqlandi.")
        else:
            await message.reply(f"❌ Test {test_key} saqlanmadi — ehtimol mavjud.")
        
        await state.finish()

    async def create_test_start_old(self, message: types.Message):
        """Eski usulda test yaratish (savol-savol) - nomi o'zgardi"""
        if not self.is_admin(message.from_user.id):
            await message.answer("❌ *Siz admin emassiz!*", parse_mode="Markdown")
            return
        
        await message.answer("📝 *Yangi test yaratish (eski usul)*\n\nTest nomini kiriting:", 
                           parse_mode="Markdown")
        await AdminStates.test_nomi.set()

    # ==================== QOLGAN FUNKSIYALAR O'ZGARMADI ==================== #
    # Quyidagi barcha funksiyalar sizning asl kodingizdan o'zgarmasdan qoladi
    
    async def start_command(self, message: types.Message):
        """Botni ishga tushirish"""
        user_id = message.from_user.id

        # Check if coming from channel link
        if len(message.text.split()) > 1:
            command = message.text.split()[1]
            if command.startswith('test_'):
                try:
                    test_id = int(command.split('_')[1])
                    if self.db.is_user_registered(user_id):
                        await self.start_test(message, test_id)
                        return
                except:
                    pass

        if self.db.is_user_registered(user_id):
            await self.send_welcome_message(message)
        else:
            await self.start_registration(message)

    async def send_welcome_message(self, message: types.Message):
        """Ro'yxatdan o'tgan foydalanuvchilarga xush kelibsiz xabari"""
        try:
            await self.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=STICKERS["welcome"]
            )
        except:
            pass

        user = self.db.get_user(message.from_user.id)
        results = self.db.get_user_results(message.from_user.id)
        position = self.db.get_user_position(message.from_user.id)

        welcome_text = f"""
        👋 *Xush kelibsiz, {user['ism']} {user['familiya']}!*

        🎯 *Quiz Botga xush kelibsiz!*

        📊 *Sizning statistikangiz:*
        • Testlar soni: {len(results)}
        • Reyting: #{position if position else "Hali test topshirmagansiz"}

        🎮 *Mavjud funksiyalar:*
        /menu - Asosiy menyu
        /myresults - Mening natijalarim
        /stats - Statistika
        /leaderboard - Reyting jadvali

        🏆 *Test topshirish orqali bilimingizni sinab ko'ring va yetakchilar jadvalida o'z o'rningizni oling!*
        """

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📝 Test topshirish", callback_data="start_quiz"),
            InlineKeyboardButton("🏆 Reyting", callback_data="leaderboard"),
            InlineKeyboardButton("📊 Mening natijalarim", callback_data="my_results"),
            InlineKeyboardButton("ℹ️ Yordam", callback_data="help")
        )

        await message.answer(welcome_text, parse_mode="Markdown", reply_markup=keyboard)

    async def start_registration(self, message: types.Message):
        """Ro'yxatdan o'tishni boshlash"""
        welcome_text = """
        👋 *Assalomu alaykum!*

        🤖 *Uzbek Quiz Bot* ga xush kelibsiz!

        📝 Botdan to'liq foydalanish uchun ro'yxatdan o'tishingiz kerak.
        Iltimos, quyidagi ma'lumotlarni kiriting:

        🎓 *Bu bot nima qiladi?*
        • Turli fanlar bo'yicha testlar
        • Bilimingizni o'lchash
        • Do'stlaringiz bilan raqobatlashish
        • Reyting jadvalida o'rin olish

        *Ro'yxatdan o'tishni boshlaymiz!*
        """

        await message.answer(welcome_text, parse_mode="Markdown")
        await message.answer("📛 *Ismingizni kiriting:*", parse_mode="Markdown")
        await RegistrationStates.ism.set()

    async def process_ism(self, message: types.Message, state: FSMContext):
        """Ismni qayta ishlash"""
        await state.update_data(ism=message.text)
        await message.answer("📛 *Familiyangizni kiriting:*", parse_mode="Markdown")
        await RegistrationStates.familiya.set()

    async def process_familiya(self, message: types.Message, state: FSMContext):
        """Familiyani qayta ishlash"""
        await state.update_data(familiya=message.text)

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        contact_button = KeyboardButton("📱 Telefon raqamimni yuborish", request_contact=True)
        keyboard.add(contact_button)

        await message.answer(
            "📱 *Telefon raqamingizni yuboring:*\n\n"
            "*(«Telefon raqamimni yuborish» tugmasini bosing yoki raqamni +998XXXXXXXXX formatida yozing)*",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await RegistrationStates.telefon.set()

    async def process_telefon(self, message: types.Message, state: FSMContext):
        """Telefon raqamini qayta ishlash"""
        if message.contact:
            telefon = message.contact.phone_number
        else:
            telefon = message.text

        if not telefon.startswith('+'):
            telefon = '+' + telefon

        await state.update_data(telefon=telefon)
        await message.answer(
            "🏫 *Qaysi maktabda o'qiysiz?*\n\n"
            "*(Maktab nomi va raqamini kiriting)*",
            parse_mode="Markdown",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await RegistrationStates.maktab.set()

    async def process_maktab(self, message: types.Message, state: FSMContext):
        """Maktab nomini qayta ishlash"""
        await state.update_data(maktab=message.text)
        await message.answer(
            "🎓 *Qaysi o'quv markazida o'qiysiz?*\n\n"
            "*(Agar o'quv markazida o'qimasangiz, «Yo'q» deb yozing)*",
            parse_mode="Markdown"
        )
        await RegistrationStates.oquv_markazi.set()

    async def process_oquv_markazi(self, message: types.Message, state: FSMContext):
        """O'quv markazini qayta ishlash"""
        await state.update_data(oquv_markazi=message.text)

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
        for region in UZBEK_REGIONS:
            keyboard.add(KeyboardButton(region))

        await message.answer(
            "📍 *Qaysi viloyatda yashaysiz?*",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await RegistrationStates.viloyat.set()

    async def process_viloyat(self, message: types.Message, state: FSMContext):
        """Viloyatni qayta ishlash"""
        await state.update_data(viloyat=message.text)
        await message.answer(
            "🏘️ *Qaysi tumanda yashaysiz?*\n\n"
            "*(Tuman nomini kiriting)*",
            parse_mode="Markdown",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await RegistrationStates.tuman.set()

    async def process_tuman(self, message: types.Message, state: FSMContext):
        """Tumannni qayta ishlash va ro'yxatni yakunlash"""
        data = await state.get_data()

        # Ma'lumotlarni bazaga saqlash
        self.db.add_user(
            telegram_id=message.from_user.id,
            ism=data['ism'],
            familiya=data['familiya'],
            telefon=data['telefon'],
            maktab=data['maktab'],
            oquv_markazi=data['oquv_markazi'],
            viloyat=data['viloyat'],
            tuman=message.text
        )

        # Tabriklash xabari
        try:
            await self.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=STICKERS["celebration"]
            )
        except:
            pass

        completion_text = f"""
        ✅ *Ro'yxatdan o'tish muvaffaqiyatli yakunlandi!*

        👤 *Sizning ma'lumotlaringiz:*
        • Ism: {data['ism']}
        • Familiya: {data['familiya']}
        • Telefon: {data['telefon']}
        • Maktab: {data['maktab']}
        • O'quv markazi: {data['oquv_markazi']}
        • Manzil: {data['viloyat']}, {message.text}

        🎮 *Endi test topshirishni boshlashingiz mumkin!*

        /menu - Asosiy menyuni ochish
        """

        await message.answer(completion_text, parse_mode="Markdown")
        await state.finish()

        # Admin ga bildirishnoma
        try:
            total_users = self.db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            admin_msg = f"""
            📊 *Yangi foydalanuvchi ro'yxatdan o'tdi!*

            👤 Foydalanuvchi: {data['ism']} {data['familiya']}
            📱 Telefon: {data['telefon']}
            🏫 Maktab: {data['maktab']}
            📍 Manzil: {data['viloyat']}, {message.text}
            👥 Umumiy foydalanuvchilar: {total_users}
            """
            await self.bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Adminga xabar yuborishda xato: {e}")

    # -------------------- ASOSIY MENYU VA QUIZ -------------------- #
    async def show_main_menu(self, message: types.Message):
        """Asosiy menyuni ko'rsatish"""
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📝 Test topshirish", callback_data="start_quiz"),
            InlineKeyboardButton("🏆 Reyting", callback_data="leaderboard"),
            InlineKeyboardButton("📊 Mening natijalarim", callback_data="my_results"),
            InlineKeyboardButton("📈 Bugungi statistika", callback_data="today_stats"),
            InlineKeyboardButton("ℹ️ Yordam", callback_data="help"),
            InlineKeyboardButton("👤 Profil", callback_data="profile")
        )

        await message.answer(
            "🎮 *Asosiy Menyu*\n\n"
            "Quyidagi tugmalardan birini tanlang:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    async def handle_callback(self, callback_query: CallbackQuery):
        """Callback query larni qayta ishlash"""
        await callback_query.answer()

        data = callback_query.data

        if data == "start_quiz":
            await self.show_available_tests(callback_query.message)
        elif data == "leaderboard":
            await self.show_leaderboard(callback_query.message)
        elif data == "my_results":
            await self.show_user_results(callback_query.message)
        elif data == "today_stats":
            await self.show_today_stats(callback_query.message)
        elif data == "help":
            await self.show_help(callback_query.message)
        elif data == "profile":
            await self.show_profile(callback_query.message)
        elif data == "menu_back":
            await self.show_main_menu(callback_query.message)
        elif data.startswith("test_"):
            test_id = int(data.split("_")[1])
            await self.start_test(callback_query.message, test_id)
        elif data == "cancel_quiz":
            await self.cancel_quiz(callback_query.message)

        # Admin callbacks
        elif data == "admin_panel":
            await self.admin_panel(callback_query.message)
        elif data == "admin_export":
            await self.admin_export(callback_query.message)
        elif data == "export_users":
            await self.admin_export_users_csv(callback_query.message)
        elif data == "export_results":
            await self.admin_export_results_csv(callback_query.message)
        elif data == "admin_users":
            await self.admin_view_users(callback_query.message)
        elif data == "admin_results":
            await self.admin_view_results(callback_query.message)
        elif data == "admin_new_test":
            await self.cmd_create_test(callback_query.message)  # O'ZGARDI
        elif data == "admin_refresh":
            await self.admin_panel(callback_query.message)
        elif data == "admin_list":
            await self.admin_list_tests(callback_query.message)
        elif data == "admin_edit":
            await self.admin_edit_tests(callback_query.message)
        elif data == "admin_send":
            await self.admin_send_test(callback_query.message)
        elif data == "admin_back":
            await self.admin_panel(callback_query.message)
        elif data.startswith("edit_test_"):
            test_id = int(data.split("_")[2])
            await self.edit_test_questions(callback_query.message, test_id)
        elif data.startswith("delete_test_"):
            test_id = int(data.split("_")[2])
            await self.delete_test_confirmation(callback_query.message, test_id)
        elif data.startswith("confirm_delete_"):
            test_id = int(data.split("_")[2])
            await self.delete_test(callback_query.message, test_id)
        elif data.startswith("cancel_delete_"):
            await self.admin_edit_tests(callback_query.message)
        elif data.startswith("view_test_"):
            test_id = int(data.split("_")[2])
            await self.view_test_details(callback_query.message, test_id)
        elif data.startswith("edit_question_"):
            parts = data.split("_")
            question_id = int(parts[2])
            await self.edit_question_start(callback_query.message, question_id)
        elif data.startswith("delete_question_"):
            parts = data.split("_")
            question_id = int(parts[2])
            await self.delete_question(callback_query.message, question_id)
        elif data.startswith("send_test_"):
            test_id = int(data.split("_")[2])
            await self.send_test_to_channel(test_id)
            await callback_query.message.answer(f"✅ Test #{test_id} kanalga yuborildi!")

    async def show_available_tests(self, message: types.Message):
        """Mavjud testlarni ko'rsatish"""
        tests = self.db.get_active_tests()

        if not tests:
            await message.answer(
                "ℹ️ *Hozircha testlar mavjud emas.*\n\n"
                "Administrator yangi testlar qo'shishi kutilmoqda.",
                parse_mode="Markdown"
            )
            return

        keyboard = InlineKeyboardMarkup(row_width=1)
        for test in tests:
            # sent_to_channel maydonini tekshirish
            sent_to_channel = test['sent_to_channel'] if 'sent_to_channel' in dict(test).keys() else 0
            sent_status = "📢" if sent_to_channel else "📝"
            keyboard.add(
                InlineKeyboardButton(
                    f"{sent_status} {test['nomi']} ({test['savollar_soni']} savol)",
                    callback_data=f"test_{test['id']}"
                )
            )

        keyboard.add(InlineKeyboardButton("🔙 Orqaga", callback_data="menu_back"))

        await message.answer(
            "📚 *Mavjud Testlar:*\n\n"
            "📢 - Kanalga yuborilgan\n"
            "📝 - Faqat botda mavjud\n\n"
            "Quyidagi testlardan birini tanlang:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    async def start_test(self, message: types.Message, test_id: int):
        """Testni boshlash"""
        user_id = message.chat.id

        # Testni olish
        test = self.db.get_test(test_id)
        if not test:
            await message.answer("❌ Test topilmadi!")
            return

        # Test faolmi?
        if test['is_active'] != 1:
            await message.answer("❌ Bu test hozir mavjud emas!")
            return

        # User session ni boshlash
        self.user_sessions[user_id] = {
            'test_id': test_id,
            'current_question': 0,
            'answers': [],
            'correct_answers': 0,
            'start_time': datetime.now()
        }

        # Birinchi savolni ko'rsatish
        await self.show_next_question(message)

    async def show_next_question(self, message: types.Message):
        """Keyingi savolni ko'rsatish"""
        user_id = message.chat.id
        session = self.user_sessions.get(user_id)

        if not session:
            return

        test_id = session['test_id']
        questions = self.db.get_questions(test_id)

        if session['current_question'] >= len(questions):
            # Test yakunlandi
            await self.finish_test(message)
            return

        question = questions[session['current_question']]

        # Progress bar
        progress = self.create_progress_bar(session['current_question'], len(questions))

        # Savolni ko'rsatish
        question_text = f"""
{progress}

❓ *Savol #{session['current_question'] + 1}:*
{question['savol_matni']}

📋 *Variantlar:*
A) {question['variant_a']}
B) {question['variant_b']}
C) {question['variant_c']}
D) {question['variant_d']}

📝 *Javobingizni (A, B, C, D) formatida yuboring:*
        """

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("❌ Testni bekor qilish", callback_data="cancel_quiz"))

        await message.answer(question_text, parse_mode="Markdown", reply_markup=keyboard)
        await QuizStates.javob_kutish.set()

    async def process_answer(self, message: types.Message, state: FSMContext):
        """Foydalanuvchi javobini qayta ishlash"""
        user_id = message.chat.id
        session = self.user_sessions.get(user_id)

        if not session:
            await state.finish()
            return

        answer = message.text.upper().strip()

        # Javobni tekshirish
        if answer not in ['A', 'B', 'C', 'D']:
            await message.answer("⚠️ *Iltimos, faqat A, B, C, D harflaridan birini yuboring!*", parse_mode="Markdown")
            return

        # To'g'ri javobni olish
        test_id = session['test_id']
        questions = self.db.get_questions(test_id)
        question = questions[session['current_question']]
        correct_answer = question['togri_javob']

        # Javobni saqlash
        is_correct = (answer == correct_answer)

        # User answer ni bazaga saqlash
        self.db.save_user_answer(
            user_id=user_id,
            test_id=test_id,
            question_id=question['id'],
            user_answer=answer,
            is_correct=is_correct
        )

        session['answers'].append({
            'question_id': question['id'],
            'user_answer': answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct
        })

        if is_correct:
            session['correct_answers'] += 1
            # Tabriklash sticker
            try:
                await self.bot.send_sticker(
                    chat_id=message.chat.id,
                    sticker=STICKERS["correct"]
                )
            except:
                pass

            feedback = "✅ *To'g'ri!* Ajoyib javob! 🎉"
        else:
            # Xato uchun sticker
            try:
                await self.bot.send_sticker(
                    chat_id=message.chat.id,
                    sticker=STICKERS["incorrect"]
                )
            except:
                pass

            feedback = f"❌ *Noto'g'ri.* To'g'ri javob: *{correct_answer}*"

        # Feedback yuborish
        await message.answer(feedback, parse_mode="Markdown")

        # 2 soniya kutib, keyingi savol
        await asyncio.sleep(1.5)

        # Keyingi savol
        session['current_question'] += 1
        await self.show_next_question(message)

    async def finish_test(self, message: types.Message):
        """Testni yakunlash va natijalarni ko'rsatish"""
        user_id = message.chat.id
        session = self.user_sessions.pop(user_id, None)

        if not session:
            return

        test = self.db.get_test(session['test_id'])
        questions = self.db.get_questions(session['test_id'])
        total_questions = len(questions)

        # Natijalarni bazaga saqlash
        percentage = self.db.save_result(
            user_id=user_id,
            test_id=session['test_id'],
            togri_javoblar=session['correct_answers'],
            umumiy_savollar=total_questions
        )

        # Reytingdagi o'rni
        position = self.db.get_user_position(user_id)

        # Tabriklash xabari
        try:
            await self.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=STICKERS["celebration"]
            )
        except:
            pass

        # Natija xabari
        result_text = f"""
🎉 *Test yakunlandi!*

📊 *Sizning natijalaringiz:*
• Test nomi: *{test['nomi']}*
• To'g'ri javoblar: *{session['correct_answers']}/{total_questions}*
• Foiz: *{percentage:.1f}%*
• Reytingdagi o'rningiz: *#{position if position else "Hali reytingda emas"}*

🏆 *Sizning yutuqlaringiz:*
        """

        # Qo'shimcha motivatsion xabar
        if percentage >= 90:
            result_text += "\n🎖️ *A'lo baho! Siz ajoyib natija ko'rsatdingiz!*"
        elif percentage >= 70:
            result_text += "\n👍 *Yaxshi natija! Davom eting!*"
        elif percentage >= 50:
            result_text += "\n👌 *Qoniqarli natija. Yana bir bor urinib ko'ring!*"
        else:
            result_text += "\n💪 *Qo'rqmang! Keyingi safar yaxshiroq natija ko'rsatasiz!*"

        result_text += "\n\n📈 *Keyingi bosqich:* /menu - Yangi test topshirish"

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📊 Batafsil natijalar", callback_data="my_results"),
            InlineKeyboardButton("🏆 Reyting", callback_data="leaderboard"),
            InlineKeyboardButton("📝 Yangi test", callback_data="start_quiz")
        )

        await message.answer(result_text, parse_mode="Markdown", reply_markup=keyboard)
        await QuizStates.javob_kutish.set()  # Holatni tozalash

        # Admin ga bildirishnoma
        try:
            user = self.db.get_user(user_id)
            admin_msg = f"""
            📊 *Yangi test natijasi!*

            👤 Foydalanuvchi: {user['ism']} {user['familiya']}
            📝 Test: {test['nomi']}
            ✅ To'g'ri javoblar: {session['correct_answers']}/{total_questions}
            📈 Foiz: {percentage:.1f}%
            🏫 Maktab: {user['maktab']}
            """
            await self.bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Adminga natija xabarida xato: {e}")

    async def cancel_quiz(self, message: types.Message):
        """Testni bekor qilish"""
        user_id = message.chat.id
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]

        await message.answer(
            "❌ *Test bekor qilindi.*\n\n"
            "Asosiy menyuga qaytish: /menu",
            parse_mode="Markdown"
        )
        await QuizStates.javob_kutish.set()  # Holatni tozalash

    # -------------------- REYTING (LEADERBOARD) -------------------- #
    async def show_leaderboard(self, message: types.Message):
        """Reyting jadvalini ko'rsatish"""
        try:
            await self.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=STICKERS["leaderboard"]
            )
        except:
            pass

        leaderboard = self.db.get_leaderboard(limit=10)

        if not leaderboard:
            await message.answer(
                "📊 *Hozircha reyting jadvali bo'sh.*\n\n"
                "Birinchi bo'lib test topshirish orqali yetakchi bo'ling!",
                parse_mode="Markdown"
            )
            return

        leaderboard_text = "🏆 *TOP 10 O'QUVCHILAR:*\n\n"

        emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        for i, student in enumerate(leaderboard):
            if i < len(emojis):
                medal = emojis[i]
            else:
                medal = f"{i+1}."

            avg_percentage = student.get('avg_percentage', student.get('foiz', 0))
            leaderboard_text += f"""
{medal} *{student['ism']} {student['familiya']}*
   📊 {avg_percentage:.1f}%
   🏫 {student['maktab']}
            """

        # Userning o'z o'rni
        user_id = message.chat.id
        position = self.db.get_user_position(user_id)
        user = self.db.get_user(user_id)

        if position:
            leaderboard_text += f"\n\n📈 *Sizning o'rningiz: #{position}*"
            if user:
                leaderboard_text += f"\n👤 {user['ism']} {user['familiya']}"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔄 Yangilash", callback_data="leaderboard"))

        await message.answer(leaderboard_text, parse_mode="Markdown", reply_markup=keyboard)

    async def show_leaderboard_command(self, message: types.Message):
        """Komanda orqali reytingni ko'rsatish"""
        await self.show_leaderboard(message)

    # -------------------- NATIJALAR -------------------- #
    async def show_user_results(self, message: types.Message):
        """Foydalanuvchi natijalarini ko'rsatish"""
        user_id = message.chat.id
        results = self.db.get_user_results(user_id)

        if not results:
            await message.answer(
                "📝 *Siz hali test topshirmagansiz.*\n\n"
                "Birinchi testni topshirish uchun: /menu",
                parse_mode="Markdown"
            )
            return

        user = self.db.get_user(user_id)
        total_tests = len(results)
        total_correct = sum(r['togri_javoblar'] for r in results)
        total_questions = sum(r['umumiy_savollar'] for r in results)
        avg_percentage = (total_correct / total_questions * 100) if total_questions > 0 else 0

        summary_text = f"""
📊 *SIZNING UMUMIY STATISTIKANGIZ:*

👤 Ism: {user['ism']} {user['familiya']}
🏫 Maktab: {user['maktab']}
📈 Testlar soni: {total_tests}
✅ Umumiy to'g'ri javoblar: {total_correct}/{total_questions}
📊 O'rtacha foiz: {avg_percentage:.1f}%
🏆 Reytingdagi o'rningiz: #{self.db.get_user_position(user_id) or "Noma'lum"}
        """

        await message.answer(summary_text, parse_mode="Markdown")

        # Har bir test natijasi (faqat oxirgi 5 tasi)
        for result in results[:5]:
            try:
                date_obj = datetime.strptime(result['vaqt'], '%Y-%m-%d %H:%M:%S')
                date = date_obj.strftime('%d.%m.%Y %H:%M')
            except:
                date = result['vaqt']

            result_text = f"""
📝 *Test:* {result['test_nomi']}
📅 *Sana:* {date}
✅ *To'g'ri javoblar:* {result['togri_javoblar']}/{result['umumiy_savollar']}
📊 *Foiz:* {result['foiz']:.1f}%
            """

            # Progress bar
            percentage = result['foiz']
            progress_bar = self.create_progress_bar(int(percentage/10), 10, show_percentage=True)

            await message.answer(f"{result_text}\n{progress_bar}", parse_mode="Markdown")

        if total_tests > 5:
            await message.answer(f"📖 *Yana {total_tests - 5} ta test natijasi mavjud...*", parse_mode="Markdown")

    async def show_my_results_command(self, message: types.Message):
        """Komanda orqali natijalarni ko'rsatish"""
        await self.show_user_results(message)

    # -------------------- STATISTIKA -------------------- #
    async def show_today_stats(self, message: types.Message):
        """Bugungi statistika"""
        stats = self.db.get_today_stats()
        total_stats = self.db.get_total_stats()

        stats_text = f"""
📊 *BUGUNGI STATISTIKA:*

👥 Faol foydalanuvchilar: {stats['active_users']}
📝 Topshirilgan testlar: {stats['tests_taken']}

📈 *UMUMIY STATISTIKA:*
👤 Ro'yxatdan o'tganlar: {total_stats['total_users']}
📚 Testlar soni: {total_stats['total_tests']}
🎯 Bajarilgan testlar: {total_stats['total_results']}
📢 Kanalga yuborilgan testlar: {total_stats['sent_tests']}

⏰ *Statistika har soat yangilanadi.*
        """

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔄 Yangilash", callback_data="today_stats"))

        await message.answer(stats_text, parse_mode="Markdown", reply_markup=keyboard)

    async def show_stats_command(self, message: types.Message):
        """Umumiy statistika"""
        await self.show_today_stats(message)

    # -------------------- PROFIL -------------------- #
    async def show_profile(self, message: types.Message):
        """Foydalanuvchi profilini ko'rsatish"""
        user_id = message.chat.id
        user = self.db.get_user(user_id)

        if not user:
            await message.answer("❌ *Siz ro'yxatdan o'tmagansiz!*\n\n/register - Ro'yxatdan o'tish", parse_mode="Markdown")
            return

        results = self.db.get_user_results(user_id)
        total_tests = len(results)
        total_correct = sum(r['togri_javoblar'] for r in results) if results else 0
        total_questions = sum(r['umumiy_savollar'] for r in results) if results else 0
        avg_percentage = (total_correct / total_questions * 100) if total_questions > 0 else 0

        profile_text = f"""
👤 *SIZNING PROFILINGIZ:*

📛 *Ism:* {user['ism']}
📛 *Familiya:* {user['familiya']}
📱 *Telefon:* {user['telefon']}
🏫 *Maktab:* {user['maktab']}
🎓 *O'quv markazi:* {user['oquv_markazi']}
📍 *Manzil:* {user['viloyat']}, {user['tuman']}
📅 *Ro'yxatdan o'tgan sana:* {user['registered_at'][:10]}

📊 *STATISTIKA:*
📈 Testlar soni: {total_tests}
✅ To'g'ri javoblar: {total_correct}/{total_questions}
📊 O'rtacha foiz: {avg_percentage:.1f}%
🏆 Reyting: #{self.db.get_user_position(user_id) or "Hali test topshirmagansiz"}
        """

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("✏️ Ma'lumotlarni yangilash", callback_data="update_profile"),
            InlineKeyboardButton("📊 Natijalar", callback_data="my_results"),
            InlineKeyboardButton("🏆 Reyting", callback_data="leaderboard")
        )

        await message.answer(profile_text, parse_mode="Markdown", reply_markup=keyboard)

    # -------------------- YORDAM -------------------- #
    async def show_help(self, message: types.Message):
        """Yordam menyusi"""
        help_text = """
ℹ️ *QUIZ BOT YORDAM MENYUSI*

🎯 *Bot nima qiladi?*
• Turli fanlar bo'yicha testlar
• Bilimingizni sinash
• Do'stlaringiz bilan raqobatlashish
• Reyting jadvalida o'rin olish

📋 *ASOSIY BUYRUQLAR:*
/start - Botni ishga tushirish
/menu - Asosiy menyu
/register - Ro'yxatdan o'tish (agar ro'yxatdan o'tmagan bo'lsangiz)
/myresults - Mening natijalarim
/stats - Statistika
/leaderboard - Reyting jadvali

🎮 *TEST TOPSHIRISH:*
1. /menu - Asosiy menyu
2. "Test topshirish" tugmasi
3. Testni tanlang
4. Har bir savolga javob bering (A, B, C, D)
5. Natijalaringizni ko'ring

⚠️ *DIQQAT:*
• Har bir savolga 2 daqiqa vaqt beriladi
• Testni bekor qilish mumkin
• Har bir testni faqat bir marta topshirish mumkin

📞 *QO'LLAB-QUVVATLASH:*
Agar muammo yuzaga kelsa, administratorga murojaat qiling.
        """

        await message.answer(help_text, parse_mode="Markdown")

    # -------------------- ADMIN PANEL -------------------- #
    async def admin_panel_command(self, message: types.Message):
        """Admin panelini ko'rsatish (command)"""
        if not self.is_admin(message.from_user.id):
            await message.answer("❌ *Siz admin emassiz!*", parse_mode="Markdown")
            return

        await self.admin_panel(message)

    async def admin_panel(self, message: types.Message):
        """Admin panelini ko'rsatish"""
        total_stats = self.db.get_total_stats()
        today_stats = self.db.get_today_stats()

        admin_text = f"""
👑 *ADMIN PANELI*

📊 *STATISTIKA:*
👥 Foydalanuvchilar: {total_stats['total_users']}
📝 Testlar: {total_stats['total_tests']}
🎯 Natijalar: {total_stats['total_results']}
📢 Kanalga yuborilgan: {total_stats['sent_tests']}
👤 Bugun faol: {today_stats['active_users']}
📊 Bugun testlar: {today_stats['tests_taken']}

⚙️ *BUYRUQLAR:*
/create_test - Yangi test yaratish (kalit bilan)
/create_test_old - Eski usulda test yaratish
/list_tests - Testlar ro'yxati
/edit_tests - Testlarni tahrirlash
/send_test - Testni kanalga yuborish

🔧 *TEZKOR TUGMALAR:*
        """

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📤 Eksport (CSV)", callback_data="admin_export"),
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users"),
            InlineKeyboardButton("📊 Natijalar", callback_data="admin_results"),
            InlineKeyboardButton("📝 Yangi test", callback_data="admin_new_test"),
            InlineKeyboardButton("📋 Testlar ro'yxati", callback_data="admin_list"),
            InlineKeyboardButton("✏️ Testlarni tahrirlash", callback_data="admin_edit"),
            InlineKeyboardButton("📢 Kanalga yuborish", callback_data="admin_send"),
            InlineKeyboardButton("🔄 Yangilash", callback_data="admin_refresh")
        )

        await message.answer(admin_text, parse_mode="Markdown", reply_markup=keyboard)

    # ==================== QOLGAN FUNKSIYALAR O'ZGARMADI ==================== #
    # Quyidagi barcha funksiyalar sizning asl kodingizdan o'zgarmasdan qoladi
    
    async def admin_export(self, message: types.Message):
        """Ma'lumotlarni eksport qilish"""
        if not self.is_admin(message.from_user.id):
            await message.answer("❌ *Siz admin emassiz!*", parse_mode="Markdown")
            return

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("👥 Foydalanuvchilar (CSV)", callback_data="export_users"),
            InlineKeyboardButton("📊 Natijalar (CSV)", callback_data="export_results"),
            InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")
        )

        await message.answer("📤 *Eksport qilish:*\n\nQaysi ma'lumotlarni eksport qilmoqchisiz?",
                           parse_mode="Markdown", reply_markup=keyboard)

    async def admin_export_users_csv(self, message: types.Message):
        """Foydalanuvchilarni CSV formatda eksport qilish"""
        if not self.is_admin(message.from_user.id):
            return

        csv_data = self.db.export_users_csv()

        # CSV faylini yaratish
        file = io.BytesIO(csv_data.encode('utf-8'))
        file.name = f'users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        await message.answer_document(
            document=InputFile(file, filename=file.name),
            caption=f"📊 *Foydalanuvchilar ro'yxati*\n\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="Markdown"
        )

    async def admin_export_results_csv(self, message: types.Message):
        """Natijalarni CSV formatda eksport qilish"""
        if not self.is_admin(message.from_user.id):
            return

        csv_data = self.db.export_results_csv()

        # CSV faylini yaratish
        file = io.BytesIO(csv_data.encode('utf-8'))
        file.name = f'results_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        await message.answer_document(
            document=InputFile(file, filename=file.name),
            caption=f"📊 *Test natijalari*\n\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="Markdown"
        )

    async def admin_view_users(self, message: types.Message):
        """Foydalanuvchilarni ko'rish"""
        if not self.is_admin(message.from_user.id):
            return

        users = self.db.get_all_users()

        if not users:
            await message.answer("👥 *Foydalanuvchilar topilmadi*", parse_mode="Markdown")
            return

        # Faqat birinchi 5 ta foydalanuvchini ko'rsatish
        users_text = "👥 *SONGI 5 FOYDALANUVCHI:*\n\n"

        for user in users[:5]:
            users_text += f"""
👤 *{user['ism']} {user['familiya']}*
📱 {user['telefon']}
🏫 {user['maktab']}
📍 {user['viloyat']}, {user['tuman']}
📅 {user['registered_at'][:10]}
━━━━━━━━━━━━━━━━━━
            """

        if len(users) > 5:
            users_text += f"\n📖 *Jami: {len(users)} ta foydalanuvchi*"
            users_text += f"\n📤 Barchasini olish uchun: Eksport (CSV)"

        await message.answer(users_text, parse_mode="Markdown")

    async def admin_view_results(self, message: types.Message):
        """Natijalarni ko'rish"""
        if not self.is_admin(message.from_user.id):
            return

        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT r.*, u.ism, u.familiya, t.nomi as test_nomi
            FROM results r
            JOIN users u ON r.user_id = u.telegram_id
            JOIN tests t ON r.test_id = t.id
            ORDER BY r.vaqt DESC
            LIMIT 5
        ''')
        results = cursor.fetchall()

        if not results:
            await message.answer("📊 *Natijalar topilmadi*", parse_mode="Markdown")
            return

        results_text = "📊 *SONGI 5 NATIJA:*\n\n"

        for result in results:
            date = result['vaqt'][:16] if result['vaqt'] else "Noma'lum"
            results_text += f"""
👤 {result['ism']} {result['familiya']}
📝 {result['test_nomi']}
✅ {result['togri_javoblar']}/{result['umumiy_savollar']}
📊 {result['foiz']:.1f}%
📅 {date}
━━━━━━━━━━━━━━━━━━
            """

        cursor.execute("SELECT COUNT(*) FROM results")
        total_results = cursor.fetchone()[0]

        if total_results > 5:
            results_text += f"\n📖 *Jami: {total_results} ta natija*"
            results_text += f"\n📤 Barchasini olish uchun: Eksport (CSV)"

        await message.answer(results_text, parse_mode="Markdown")

    # -------------------- ESKI TEST YARATISH (SAQLAB QO'YILDI) -------------------- #
    async def create_test_start(self, message: types.Message):
        """Yangi test yaratishni boshlash (eski) - callback uchun"""
        await self.create_test_start_old(message)

    async def process_test_nomi(self, message: types.Message, state: FSMContext):
        """Test nomini qayta ishlash (eski)"""
        await state.update_data(test_nomi=message.text)
        await message.answer("🔢 *Savollar sonini kiriting:*\n\n(Masalan: 10, 20, 30)", parse_mode="Markdown")
        await AdminStates.test_savollari.set()

    async def process_savol_soni(self, message: types.Message, state: FSMContext):
        """Savollar sonini qayta ishlash (eski)"""
        try:
            savollar_soni = int(message.text)
            if savollar_soni <= 0 or savollar_soni > 50:
                await message.answer("⚠️ *Iltimos, 1 dan 50 gacha bo'lgan son kiriting!*", parse_mode="Markdown")
                return

            await state.update_data(savollar_soni=savollar_soni)

            # Testni bazaga qo'shish
            data = await state.get_data()
            test_id = self.db.add_test(data['test_nomi'], savollar_soni)

            await state.update_data(test_id=test_id, current_savol=0)

            await message.answer(f"✅ *Test yaratildi! ID: {test_id}*\n\n"
                               f"Endi 1-savolni kiriting:", parse_mode="Markdown")
            await AdminStates.savol_matni.set()

        except ValueError:
            await message.answer("⚠️ *Iltimos, faqat raqam kiriting!*", parse_mode="Markdown")

    async def process_savol_matni(self, message: types.Message, state: FSMContext):
        """Savol matnini qayta ishlash (eski)"""
        await state.update_data(savol_matni=message.text)
        await message.answer(
            "📋 *Variantlarni kiriting:*\n\n"
            "Quyidagi formatda kiriting:\n"
            "A) Birinchi variant\n"
            "B) Ikkinchi variant\n"
            "C) Uchinchi variant\n"
            "D) To'rtinchi variant",
            parse_mode="Markdown"
        )
        await AdminStates.variantlar.set()

    async def process_variantlar(self, message: types.Message, state: FSMContext):
        """Variantlarni qayta ishlash (eski)"""
        lines = message.text.strip().split('\n')

        if len(lines) < 4:
            await message.answer("⚠️ *Iltimos, barcha 4 variantni kiriting!*", parse_mode="Markdown")
            return

        # Variantlarni ajratish
        variants = {}
        for line in lines:
            if ') ' in line:
                key, value = line.split(') ', 1)
                variants[key.strip().upper()] = value.strip()

        if len(variants) != 4 or not all(k in variants for k in ['A', 'B', 'C', 'D']):
            await message.answer("⚠️ *Format noto'g'ri! A, B, C, D variantlarini kiriting.*", parse_mode="Markdown")
            return

        await state.update_data(variants=variants)

        await message.answer(
            "✅ *To'g'ri javobni kiriting:*\n\n"
            "(A, B, C, D harflaridan biri)",
            parse_mode="Markdown"
        )
        await AdminStates.togri_javob.set()

    async def process_togri_javob(self, message: types.Message, state: FSMContext):
        """To'g'ri javobni qayta ishlash (eski)"""
        togri_javob = message.text.upper().strip()

        if togri_javob not in ['A', 'B', 'C', 'D']:
            await message.answer("⚠️ *Iltimos, faqat A, B, C, D harflaridan birini kiriting!*", parse_mode="Markdown")
            return

        # Barcha ma'lumotlarni olish
        data = await state.get_data()

        # Savolni bazaga qo'shish
        self.db.add_question(
            test_id=data['test_id'],
            savol_matni=data['savol_matni'],
            variant_a=data['variants']['A'],
            variant_b=data['variants']['B'],
            variant_c=data['variants']['C'],
            variant_d=data['variants']['D'],
            togri_javob=togri_javob
        )

        # Keyingi savolga o'tish
        current_savol = data['current_savol'] + 1

        if current_savol < data['savollar_soni']:
            await state.update_data(current_savol=current_savol)
            await message.answer(f"✅ *{current_savol}-savol saqlandi!*\n\n"
                               f"Endi {current_savol + 1}-savolni kiriting:", parse_mode="Markdown")
            await AdminStates.savol_matni.set()
        else:
            # Barcha savollar saqlandi
            await message.answer(
                f"🎉 *Test muvaffaqiyatli yaratildi!*\n\n"
                f"📝 *Test nomi:* {data['test_nomi']}\n"
                f"🔢 *Savollar soni:* {data['savollar_soni']}\n"
                f"🆔 *Test ID:* {data['test_id']}\n\n"
                f"✅ Test endi foydalanuvchilar uchun mavjud!\n"
                f"📢 Kanalga ham yuborilmoqda...",
                parse_mode="Markdown"
            )

            # Testni kanalga yuborish
            await self.send_test_to_channel(data['test_id'])

            await state.finish()

    # -------------------- KANALGA TEST YUBORISH -------------------- #
    async def send_test_to_channel(self, test_id: int):
        """Testni kanalga yuborish"""
        try:
            test = self.db.get_test(test_id)
            questions = self.db.get_questions(test_id)

            if not test or not questions:
                print(f"❌ Test yoki savollar topilmadi: {test_id}")
                return

            print(f"📢 Test #{test_id} kanalga yuborilmoqda...")

            # Yangi test uchun sticker
            try:
                await self.bot.send_sticker(
                    chat_id=CHANNEL_ID,
                    sticker=STICKERS["new_test"]
                )
            except Exception as e:
                print(f"❌ Sticker yuborishda xato: {e}")

            # Test haqida post
            test_info = f"""
🎉 *YANGI TEST QO'SHILDI!* 🎉

📝 *Test nomi:* {test['nomi']}
📊 *Savollar soni:* {test['savollar_soni']}
⏰ *Yaratilgan sana:* {test['created_at'][:10]}
🏆 *Test ID:* {test_id}

📌 *Test topshirish uchun:*
1️⃣ Quyidagi tugmani bosing
2️⃣ "{test['nomi']}" testini tanlang
3️⃣ Har bir savolga javob bering

🔔 *Diqqat:* Testni faqat bir marta topshirishingiz mumkin!

👇 *Testni boshlash uchun quyidagi tugmani bosing:*
            """

            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton(
                    "🚀 Testni boshlash",
                    url=f"https://t.me/{self.bot.username}?start=test_{test_id}"
                )
            )

            # Kanalga xabar yuborish va message_id ni saqlash
            message = await self.bot.send_message(
                CHANNEL_ID,
                test_info,
                parse_mode="Markdown",
                reply_markup=keyboard
            )

            # Message ID ni bazaga saqlash
            self.db.update_test_channel_message(test_id, str(message.message_id))

            # Namuna savollari
            await self.bot.send_message(
                CHANNEL_ID,
                "📚 *Namuna savollari:*\n\n"
                "Quyida testdan bir nechta namuna savollari:",
                parse_mode="Markdown"
            )

            # Birinchi 2 ta savolni namuna sifatida
            for i, question in enumerate(questions[:2]):
                question_text = f"""
❓ *Savol #{i+1}:*
{question['savol_matni']}

A) {question['variant_a']}
B) {question['variant_b']}
C) {question['variant_c']}
D) {question['variant_d']}

🔍 *Javob:* Testni boshlang va to'g'ri javobni bilib oling!
                """

                await self.bot.send_message(
                    CHANNEL_ID,
                    question_text,
                    parse_mode="Markdown"
                )

            # Qolgan savollar soni haqida
            if len(questions) > 2:
                await self.bot.send_message(
                    CHANNEL_ID,
                    f"📖 *Va yana {len(questions)-2} ta savol...*\n\n"
                    f"Barcha savollarni ko'rish va testni topshirish uchun yuqoridagi tugmani bosing!",
                    parse_mode="Markdown"
                )

            print(f"✅ Test #{test_id} kanalga muvaffaqiyatli yuborildi!")

            # Admin ga xabar
            try:
                await self.bot.send_message(
                    ADMIN_ID,
                    f"✅ *Test kanalga yuborildi!*\n\n"
                    f"Test: {test['nomi']}\n"
                    f"ID: {test_id}\n"
                    f"Savollar soni: {len(questions)}\n"
                    f"Kanal: {CHANNEL_ID}",
                    parse_mode="Markdown"
                )
            except:
                pass

        except Exception as e:
            print(f"❌ Kanalga test yuborishda xato: {e}")
            # Admin ga xabar
            try:
                await self.bot.send_message(
                    ADMIN_ID,
                    f"❌ *Kanalga test yuborishda xato!*\n\n"
                    f"Test ID: {test_id}\n"
                    f"Xato: {str(e)[:100]}",
                    parse_mode="Markdown"
                )
            except:
                pass

    # -------------------- ADMIN TESTLAR RO'YXATI -------------------- #
    async def admin_list_tests_command(self, message: types.Message):
        """Testlar ro'yxatini ko'rsatish (command)"""
        if not self.is_admin(message.from_user.id):
            await message.answer("❌ *Siz admin emassiz!*", parse_mode="Markdown")
            return

        await self.admin_list_tests(message)

    async def admin_list_tests(self, message: types.Message):
        """Testlar ro'yxatini ko'rsatish"""
        tests = self.db.get_all_tests()

        if not tests:
            await message.answer("📭 *Hozircha testlar mavjud emas.*", parse_mode="Markdown")
            return

        tests_text = "📋 *BARCHA TESTLAR:*\n\n"

        for test in tests:
            status = "🟢 Faol" if test['is_active'] == 1 else "🔴 Nofaol"

            # sent_to_channel maydonini tekshirish
            sent_to_channel = test['sent_to_channel'] if 'sent_to_channel' in dict(test).keys() else 0
            sent = "📢 Yuborilgan" if sent_to_channel == 1 else "📝 Yuborilmagan"

            questions = self.db.get_questions(test['id'])
            questions_count = len(questions)

            tests_text += f"""
🆔 *ID:* {test['id']}
📝 *Nomi:* {test['nomi']}
📊 *Savollar:* {questions_count}/{test['savollar_soni']}
📅 *Sana:* {test['created_at'][:10]}
🔧 *Holat:* {status}
📢 *Kanal:* {sent}
━━━━━━━━━━━━━━━━━━
            """

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✏️ Tahrirlash", callback_data="admin_edit"),
            InlineKeyboardButton("📢 Kanalga yuborish", callback_data="admin_send"),
            InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")
        )

        await message.answer(tests_text, parse_mode="Markdown", reply_markup=keyboard)

    async def admin_edit_tests_command(self, message: types.Message):
        """Testlarni tahrirlash menyusi (command)"""
        if not self.is_admin(message.from_user.id):
            await message.answer("❌ *Siz admin emassiz!*", parse_mode="Markdown")
            return

        await self.admin_edit_tests(message)

    async def admin_edit_tests(self, message: types.Message):
        """Testlarni tahrirlash menyusi"""
        tests = self.db.get_all_tests()

        if not tests:
            await message.answer("📭 *Hozircha testlar mavjud emas.*", parse_mode="Markdown")
            return

        keyboard = InlineKeyboardMarkup(row_width=2)
        for test in tests:
            status = "🟢" if test['is_active'] == 1 else "🔴"
            sent = "📢" if ('sent_to_channel' in dict(test).keys() and test['sent_to_channel'] == 1) else ""

            keyboard.add(
                InlineKeyboardButton(
                    f"{status} {sent} {test['nomi']}",
                    callback_data=f"edit_test_{test['id']}"
                ),
                InlineKeyboardButton(
                    f"🗑️",
                    callback_data=f"delete_test_{test['id']}"
                )
            )

        keyboard.add(InlineKeyboardButton("👁️ Barchasini ko'rish", callback_data="admin_list"),
                     InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back"))

        await message.answer(
            "✏️ *TESTLARNI TAHRIRLASH:*\n\n"
            "Tahrirlash yoki o'chirish uchun testni tanlang:\n"
            "🟢 - Faol test\n"
            "🔴 - Nofaol test\n"
            "📢 - Kanalga yuborilgan",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    async def edit_test_questions(self, message: types.Message, test_id: int):
        """Test savollarini tahrirlash"""
        if not self.is_admin(message.from_user.id):
            return

        test = self.db.get_test(test_id)
        if not test:
            await message.answer("❌ Test topilmadi!")
            return

        questions = self.db.get_questions(test_id)

        if not questions:
            await message.answer(f"❌ Testda savollar topilmadi!")
            return

        test_info = f"""
✏️ *TESTNI TAHRIRLASH:*

📝 *Nomi:* {test['nomi']}
🔢 *Savollar soni:* {len(questions)}/{test['savollar_soni']}
📅 *Yaratilgan:* {test['created_at'][:10]}
🔧 *Holat:* {'🟢 Faol' if test['is_active'] == 1 else '🔴 Nofaol'}
📢 *Kanal:* {'✅ Yuborilgan' if ('sent_to_channel' in dict(test).keys() and test['sent_to_channel'] == 1) else '❌ Yuborilmagan'}
        """

        await message.answer(test_info, parse_mode="Markdown")

        # Har bir savolni alohida ko'rsatish
        for i, question in enumerate(questions, 1):
            question_text = f"""
📝 *Savol #{i}:*
{question['savol_matni']}

A) {question['variant_a']}
B) {question['variant_b']}
C) {question['variant_c']}
D) {question['variant_d']}
✅ To'g'ri javob: {question['togri_javob']}
            """

            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_question_{question['id']}"),
                InlineKeyboardButton("🗑️ O'chirish", callback_data=f"delete_question_{question['id']}")
            )

            await message.answer(question_text, parse_mode="Markdown", reply_markup=keyboard)

        # Orqaga tugmasi
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔙 Testlar ro'yxati", callback_data="admin_edit"))

        await message.answer(
            "📋 *Savollarni tahrirlash:*\n\n"
            "Har bir savolni alohida tahrirlash yoki o'chirish mumkin.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    async def delete_test_confirmation(self, message: types.Message, test_id: int):
        """Testni o'chirishni tasdiqlash"""
        if not self.is_admin(message.from_user.id):
            return

        test = self.db.get_test(test_id)
        if not test:
            await message.answer("❌ Test topilmadi!")
            return

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ HA, o'chirish", callback_data=f"confirm_delete_{test_id}"),
            InlineKeyboardButton("❌ BEKOR QILISH", callback_data=f"cancel_delete_{test_id}")
        )

        await message.answer(
            f"⚠️ *DIQQAT! Testni o'chirish* ⚠️\n\n"
            f"Test: *{test['nomi']}*\n"
            f"ID: {test_id}\n"
            f"Savollar soni: {test['savollar_soni']}\n\n"
            f"❌ *Bu amalni orqaga qaytarib bo'lmaydi!*\n"
            f"Barcha savollar, natijalar va javoblar o'chib ketadi.\n\n"
            f"Testni rostdan ham o'chirmoqchimisiz?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    async def delete_test(self, message: types.Message, test_id: int):
        """Testni o'chirish"""
        if not self.is_admin(message.from_user.id):
            return

        test = self.db.get_test(test_id)
        if not test:
            await message.answer("❌ Test topilmadi!")
            return

        # Testni o'chirish
        self.db.delete_test(test_id)

        await message.answer(
            f"✅ *Test muvaffaqiyatli o'chirildi!*\n\n"
            f"Test: {test['nomi']}\n"
            f"ID: {test_id}\n\n"
            f"Barcha savollar, natijalar va javoblar o'chirildi.",
            parse_mode="Markdown"
        )

        # Admin panelga qaytish
        await self.admin_edit_tests(message)

    async def delete_question(self, message: types.Message, question_id: int):
        """Savolni o'chirish"""
        if not self.is_admin(message.from_user.id):
            return

        question = self.db.get_question(question_id)
        if not question:
            await message.answer("❌ Savol topilmadi!")
            return

        # Savolni o'chirish
        self.db.delete_question(question_id)

        await message.answer(
            f"✅ *Savol o'chirildi!*\n\n"
            f"Test ID: {question['test_id']}\n"
            f"Savol ID: {question_id}",
            parse_mode="Markdown"
        )

        # Test sahifasiga qaytish
        await self.edit_test_questions(message, question['test_id'])

    async def edit_question_start(self, message: types.Message, question_id: int):
        """Savolni tahrirlashni boshlash"""
        if not self.is_admin(message.from_user.id):
            return

        question = self.db.get_question(question_id)
        if not question:
            await message.answer("❌ Savol topilmadi!")
            return

        # Savol ma'lumotlarini state ga saqlash
        state = self.dp.current_state(user=message.from_user.id)

        await state.update_data(
            edit_question_id=question_id,
            edit_test_id=question['test_id']
        )

        await message.answer(
            f"✏️ *Savolni tahrirlash:*\n\n"
            f"Joriy savol matni:\n"
            f"{question['savol_matni']}\n\n"
            f"Yangi savol matnini kiriting:",
            parse_mode="Markdown"
        )

        await AdminStates.savol_matni.set()

    async def admin_send_test_command(self, message: types.Message):
        """Testni kanalga yuborish menyusi (command)"""
        if not self.is_admin(message.from_user.id):
            await message.answer("❌ *Siz admin emassiz!*", parse_mode="Markdown")
            return

        await self.admin_send_test(message)

    async def admin_send_test(self, message: types.Message):
        """Testni kanalga yuborish menyusi"""
        tests = self.db.get_all_tests()

        if not tests:
            await message.answer("📭 *Hozircha testlar mavjud emas.*", parse_mode="Markdown")
            return

        keyboard = InlineKeyboardMarkup(row_width=1)
        for test in tests:
            sent = "✅ " if ('sent_to_channel' in dict(test).keys() and test['sent_to_channel'] == 1) else ""
            keyboard.add(
                InlineKeyboardButton(
                    f"{sent}{test['nomi']} (ID: {test['id']})",
                    callback_data=f"send_test_{test['id']}"
                )
            )

        keyboard.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back"))

        await message.answer(
            "📢 *TESTNI KANALGA YUBORISH:*\n\n"
            "Kanalga yubormoqchi bo'lgan testingizni tanlang:\n"
            "✅ - Avval yuborilgan\n"
            "📝 - Yangi yuborish",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    async def view_test_details(self, message: types.Message, test_id: int):
        """Test tafsilotlarini ko'rish"""
        if not self.is_admin(message.from_user.id):
            return

        test = self.db.get_test(test_id)
        if not test:
            await message.answer("❌ Test topilmadi!")
            return

        questions = self.db.get_questions(test_id)
        results = self.db.get_test_results(test_id)

        test_info = f"""
📊 *TEST TAFSILOTLARI:*

📝 *Nomi:* {test['nomi']}
🆔 *ID:* {test_id}
🔢 *Savollar soni:* {len(questions)}/{test['savollar_soni']}
📅 *Yaratilgan:* {test['created_at'][:10]}
🔧 *Holat:* {'🟢 Faol' if test['is_active'] == 1 else '🔴 Nofaol'}
📢 *Kanal:* {'✅ Yuborilgan' if ('sent_to_channel' in dict(test).keys() and test['sent_to_channel'] == 1) else '❌ Yuborilmagan'}

📈 *STATISTIKA:*
👥 Topshirganlar: {len(results)}
📊 O'rtacha foiz: {sum(r['foiz'] for r in results)/len(results):.1f}% if results else 0
        """

        await message.answer(test_info, parse_mode="Markdown")

        # Natijalar ro'yxati
        if results:
            results_text = "\n🏆 *ENG YAXSHI 5 NATIJA:*\n\n"

            for i, result in enumerate(results[:5], 1):
                results_text += f"""
{i}. {result['ism']} {result['familiya']}
   ✅ {result['togri_javoblar']}/{result['umumiy_savollar']}
   📊 {result['foiz']:.1f}%
   🏫 {result['maktab']}
                """

            await message.answer(results_text, parse_mode="Markdown")

    # -------------------- YORDAMCHI FUNKSIYALAR -------------------- #
    def create_progress_bar(self, current: int, total: int, show_percentage: bool = False):
        """Progress bar yaratish"""
        if total == 0:
            return ""

        filled_count = int((current / total) * 10)
        bar = ""

        for i in range(10):
            if i < filled_count:
                bar += "🟩"
            else:
                bar += "⬜"

        if show_percentage:
            percentage = (current / total) * 100 if total > 0 else 0
            return f"{bar} {percentage:.0f}%"
        else:
            return f"{bar} {current + 1}/{total}"

    # -------------------- BOTNI ISHGA TUSHIRISH -------------------- #
    async def on_startup(self, dp):
        """Bot ishga tushganda"""
        print("=" * 50)
        print("🤖 UZBEK QUIZ BOT ISHGA TUSHDI!")
        print("=" * 50)
        print(f"👑 Admin ID: {ADMIN_ID}")
        print(f"📢 Kanal ID: {CHANNEL_ID}")

        # Bazadagi ma'lumotlarni olish
        try:
            users_count = self.db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            tests_count = self.db.conn.execute("SELECT COUNT(*) FROM tests").fetchone()[0]
            print(f"📊 Foydalanuvchilar: {users_count}")
            print(f"📝 Testlar: {tests_count}")
        except:
            print("📊 Foydalanuvchilar: 0")
            print("📝 Testlar: 0")

        print("=" * 50)

        # Admin ga xabar
        try:
            total_stats = self.db.get_total_stats()
            await self.bot.send_message(
                ADMIN_ID,
                f"✅ *Bot ishga tushdi!*\n\n"
                f"⏰ Vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"👤 Foydalanuvchilar: {total_stats['total_users']}\n"
                f"📝 Testlar: {total_stats['total_tests']}\n"
                f"📊 Natijalar: {total_stats['total_results']}\n"
                f"📢 Kanal: {CHANNEL_ID}",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Adminga start xabarida xato: {e}")

    async def on_shutdown(self, dp):
        """Bot to'xtatilganda"""
        print("🤖 Bot to'xtatildi!")
        await self.bot.close()

    def run(self):
        """Botni ishga tushirish"""
        executor.start_polling(
            self.dp,
            skip_updates=True,
            on_startup=self.on_startup,
            on_shutdown=self.on_shutdown
        )

# -------------------- ASOSIY DASTUR -------------------- #
if __name__ == "__main__":
    # Loglarni sozlash
    logging.basicConfig(level=logging.INFO)

    print("=" * 50)
    print("UZBEK QUIZ BOT - ISHGA TUSHIRILMOQDA...")
    print("=" * 50)
    print("🤖 Versiya: 3.0 (Test yaratish funksiyasi o'zgardi)")
    print("📅 Sana: 2024")
    print("🌐 Til: O'zbek")
    print("👨‍💻 Dasturchi: Faxriyor Sadullayev")
    print("=" * 50)

    # Token tekshirish
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ XATO: Bot tokenini kiriting!")
        print("BOT_TOKEN o'zgaruvchisiga o'z tokeningizni qo'ying")
        print("Token olish uchun: @BotFather")
        exit(1)

    if ADMIN_ID == 123456789:
        print("⚠️ DIQQAT: Admin ID ni o'zgartiring!")
        print("ADMIN_ID o'zgaruvchisiga o'zingizning Telegram ID ingizni qo'ying")
        print("ID olish uchun: @userinfobot")

    try:
        # Botni ishga tushirish
        bot = UzbekQuizBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n🤖 Bot to'xtatildi (Ctrl+C)")
    except Exception as e:
        print(f"❌ Xato: {e}")
        print("Bot ishlamayapti. Token va Admin ID ni tekshiring.")