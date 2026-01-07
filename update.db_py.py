import sqlite3
import os


def update_database():
    """Bazani yangilash"""
    db_name = "quiz_bot.db"

    # Agar eski baza bo'lsa, o'chirish
    if os.path.exists(db_name):
        backup_name = f"quiz_bot_backup_{os.path.getmtime(db_name)}.db"
        os.rename(db_name, backup_name)
        print(f"✅ Eski baza backup qilindi: {backup_name}")

    # Yangi baza yaratish
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

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

    # Testlar jadvali (YANGILANGAN)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nomi TEXT,
            savollar_soni INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            channel_message_id TEXT,
            sent_to_channel INTEGER DEFAULT 0
        )
    ''')

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

    conn.commit()
    conn.close()
    print("✅ Yangi baza yaratildi!")

    # Admin uchun test qo'shish
    add_sample_test()


def add_sample_test():
    """Namuna test qo'shish"""
    conn = sqlite3.connect("quiz_bot.db")
    cursor = conn.cursor()

    # Test qo'shish
    cursor.execute('''
        INSERT INTO tests (nomi, savollar_soni, is_active) 
        VALUES (?, ?, ?)
    ''', ("Matematika Testi", 5, 1))
    test_id = cursor.lastrowid

    # Savollar qo'shish
    questions = [
        ("2 + 2 nechaga teng?", "3", "4", "5", "6", "B"),
        ("5 × 3 nechaga teng?", "10", "12", "15", "20", "C"),
        ("12 ÷ 4 nechaga teng?", "2", "3", "4", "5", "B"),
        ("9 - 5 nechaga teng?", "3", "4", "5", "6", "B"),
        ("7 + 8 nechaga teng?", "14", "15", "16", "17", "B"),
    ]

    for savol, a, b, c, d, togri in questions:
        cursor.execute('''
            INSERT INTO questions 
            (test_id, savol_matni, variant_a, variant_b, variant_c, variant_d, togri_javob)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (test_id, savol, a, b, c, d, togri))

    conn.commit()
    conn.close()
    print(f"✅ Namuna test qo'shildi (ID: {test_id})")


if __name__ == "__main__":
    update_database()