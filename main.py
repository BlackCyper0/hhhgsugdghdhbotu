import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import ast
import importlib.util
import subprocess
import os
import tempfile
import logging
import sqlite3
import time
from datetime import datetime
from collections import defaultdict

logging.basicConfig(filename='bot_log.txt', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = '8311193642:AAHhDg4RVlj-9I0ikDBoqv3jNOgkj14_5oA' 
ADMIN_ID = 5348572574

bot = telebot.TeleBot(BOT_TOKEN)

if not os.path.exists('files'):
    os.makedirs('files')

conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users
                  (user_id INTEGER PRIMARY KEY, username TEXT, join_date TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS banned_users
                  (user_id INTEGER PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS user_files
                  (user_id INTEGER, file_name TEXT, file_path TEXT, upload_date TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS bot_settings
                  (setting_name TEXT PRIMARY KEY, value TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS running_processes
                  (user_id INTEGER, file_name TEXT, pid INTEGER)''')

settings = {'bot_locked': 'False', 'paid_mode': 'False'}  # Sevo Team
for name, value in settings.items():
    cursor.execute("INSERT OR IGNORE INTO bot_settings (setting_name, value) VALUES (?, ?)", (name, value))
conn.commit()

def load_settings():
    cursor.execute("SELECT * FROM bot_settings")
    return {row[0]: row[1] for row in cursor.fetchall()}

settings = load_settings()

def update_setting(name, value):
    cursor.execute("UPDATE bot_settings SET value = ? WHERE setting_name = ?", (value, name))
    conn.commit()

def is_admin(user_id):
    return user_id == ADMIN_ID 

def admin_panel_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📊 عرض حالة البوت", callback_data="admin_bot_status"))
    markup.add(InlineKeyboardButton("🚫 حظر عضو", callback_data="admin_ban_user"),
               InlineKeyboardButton("✅ فك حظر عضو", callback_data="admin_unban_user"))
    markup.add(InlineKeyboardButton("🔐 قفل البوت", callback_data="admin_lock_bot"),
               InlineKeyboardButton("🔓 فتح البوت", callback_data="admin_unlock_bot"))
    markup.add(InlineKeyboardButton("📢 إذاعة للمستخدمين", callback_data="admin_broadcast"),
               InlineKeyboardButton("⏹️ إيقاف ملف", callback_data="admin_stop_file"))
    markup.add(InlineKeyboardButton("📂 رؤية ملفات المستخدمين", callback_data="admin_view_files"),
               InlineKeyboardButton("💰 تفعيل الوضع المدفوع", callback_data="admin_enable_paid"))
    markup.add(InlineKeyboardButton("🚫 إغلاق الوضع المدفوع", callback_data="admin_disable_paid"))
    return markup

def user_panel_markup(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📂 عرض ملفاتي", callback_data=f"user_view_my_files:{user_id}"))
    markup.add(InlineKeyboardButton("📤 رفع ملف جديد", callback_data="user_upload_file"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "غير معروف"
    join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)", (user_id, username, join_date))
    conn.commit()

    if settings['bot_locked'] == 'True' and not is_admin(user_id):
        bot.reply_to(message, "🚫 البوت مقفل حالياً. انتظر حتى يتم فتحه.")
        logging.info(f"محاولة وصول مستخدم محظور: {user_id}")
        return

    welcome_msg = f"🎉 اهلا {username}! دا بوت استضافة بايثون المتقدم.\n" \
                  f"يمكنك رفع ملفات .py، تثبيت مكتبات، وتشغيلها مباشرة.\n" \
                  f"ودي التحكم أدناه."

    if is_admin(user_id):
        bot.reply_to(message, welcome_msg, reply_markup=admin_panel_markup())
    else:
        bot.reply_to(message, welcome_msg, reply_markup=user_panel_markup(user_id))

    logging.info(f"مستخدم جديد أو موجود: {user_id} - {username}")

running_processes = {}  # Saif Hassan

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    data = call.data

    if data.startswith('admin_') and not is_admin(user_id):
        bot.answer_callback_query(call.id, "🚫 هذا الأمر للإداريين فقط.")
        logging.warning(f"محاولة وصول غير مصرح: {user_id} - {data}")
        return

    if data == "admin_ban_user":
        bot.send_message(call.message.chat.id, "📩 أرسل ID العضو لحظره.")
        bot.register_next_step_handler(call.message, admin_ban_user)
    elif data == "admin_unban_user":
        bot.send_message(call.message.chat.id, "📩 أرسل ID العضو لفك حظره.")
        bot.register_next_step_handler(call.message, admin_unban_user)
    elif data == "admin_lock_bot":
        update_setting('bot_locked', 'True')
        settings['bot_locked'] = 'True'
        bot.answer_callback_query(call.id, "🔒 تم قفل البوت.")
        logging.info("تم قفل البوت من قبل الإداري")
    elif data == "admin_unlock_bot":
        update_setting('bot_locked', 'False')
        settings['bot_locked'] = 'False'
        bot.answer_callback_query(call.id, "🔓 تم فتح البوت.")
        logging.info("تم فتح البوت من قبل الإداري")
    elif data == "admin_broadcast":
        bot.send_message(call.message.chat.id, "📝 أرسل الرسالة للإذاعة.")
        bot.register_next_step_handler(call.message, admin_broadcast_message)
    elif data == "admin_stop_file":
        bot.send_message(call.message.chat.id, "📩 أرسل ID المستخدم واسم الملف (مثال: 123456 file.py).")
        bot.register_next_step_handler(call.message, admin_stop_file)
    elif data == "admin_view_files":
        cursor.execute("SELECT * FROM user_files")
        files = cursor.fetchall()
        files_str = "\n".join([f"👤 User {f[0]}: {f[1]} (uploaded {f[3]})" for f in files]) or "لا توجد ملفات."
        bot.send_message(call.message.chat.id, f"📋 قائمة الملفات:\n{files_str}")
    elif data == "admin_enable_paid":
        update_setting('paid_mode', 'True')
        settings['paid_mode'] = 'True'
        bot.answer_callback_query(call.id, "💰 تم تفعيل الوضع المدفوع.")
        logging.info("تم تفعيل الوضع المدفوع")
    elif data == "admin_disable_paid":
        update_setting('paid_mode', 'False')
        settings['paid_mode'] = 'False'
        bot.answer_callback_query(call.id, "🚫 تم إغلاق الوضع المدفوع.")
        logging.info("تم إغلاق الوضع المدفوع")
    elif data == "admin_bot_status":
        status = f"حالة البوت:\n" \
                 f"قفل البوت: {'مفعل' if settings['bot_locked'] == 'True' else 'غير مفعل'}\n" \
                 f"الوضع المدفوع: {'مفعل' if settings['paid_mode'] == 'True' else 'غير مفعل'}\n" \
                 f"عدد المستخدمين: {cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]}\n" \
                 f"عدد الملفات: {cursor.execute('SELECT COUNT(*) FROM user_files').fetchone()[0]}"
        bot.send_message(call.message.chat.id, status)

    if data == "user_upload_file":
        bot.send_message(call.message.chat.id, "📤 أرسل الملف .py الذي تريد رفعه.")
    elif data.startswith("user_view_my_files:"):
        uid = int(data.split(':')[1])
        if uid != user_id:
            bot.answer_callback_query(call.id, "🚫 هذا ليس لك.")
            return
        cursor.execute("SELECT * FROM user_files WHERE user_id = ?", (user_id,))
        files = cursor.fetchall()
        if not files:
            bot.send_message(call.message.chat.id, "لا توجد ملفات مرفوعة لديك.")
            return
        markup = InlineKeyboardMarkup(row_width=2)
        for f in files:
            markup.add(InlineKeyboardButton(f"▶️ تشغيل {f[1]}", callback_data=f"run_file:{f[1]}:{user_id}"),
                       InlineKeyboardButton(f"🗑️ مسح {f[1]}", callback_data=f"delete_file:{f[1]}:{user_id}"))
        bot.send_message(call.message.chat.id, "📂 ملفاتك:", reply_markup=markup)
    elif data.startswith("run_file:"):
        parts = data.split(':')
        file_name = parts[1]
        uid = int(parts[2])
        if uid != user_id:
            bot.answer_callback_query(call.id, "🚫 هذا الملف ليس لك.")
            return
        cursor.execute("SELECT file_path FROM user_files WHERE user_id = ? AND file_name = ?", (user_id, file_name))
        path = cursor.fetchone()
        if path:
            path = path[0]
            key = (user_id, file_name)
            if key in running_processes:
                bot.send_message(call.message.chat.id, f"⚠️ الملف {file_name} جاري تشغيله بالفعل.")
                return
            try:
                # @nSEIF
                with open(path, 'r', encoding='utf-8') as f:
                    ast.parse(f.read())  # @S_S_F3
                process = subprocess.Popen(['python', path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                running_processes[key] = process
                cursor.execute("INSERT INTO running_processes (user_id, file_name, pid) VALUES (?, ?, ?)",
                               (user_id, file_name, process.pid))
                conn.commit()
                bot.send_message(call.message.chat.id, f"✅ تم تشغيل بوتك {file_name} بنجاح!")
                logging.info(f"تم تشغيل ملف {file_name} بواسطة {user_id} (PID: {process.pid})")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ خطأ في التشغيل: {str(e)}")
                logging.error(f"خطأ في تشغيل ملف {file_name}: {str(e)}")
        else:
            bot.answer_callback_query(call.id, "❌ الملف غير موجود.")
    elif data.startswith("delete_file:"):
        parts = data.split(':')
        file_name = parts[1]
        uid = int(parts[2])
        if uid != user_id:
            bot.answer_callback_query(call.id, "🚫 هذا الملف ليس لك.")
            return
        cursor.execute("SELECT file_path FROM user_files WHERE user_id = ? AND file_name = ?", (user_id, file_name))
        path = cursor.fetchone()
        if path:
            path = path[0]
            key = (user_id, file_name)
            if key in running_processes:
                running_processes[key].terminate()
                try:
                    running_processes[key].wait(timeout=5)
                except subprocess.TimeoutExpired:
                    running_processes[key].kill()
                del running_processes[key]
                cursor.execute("DELETE FROM running_processes WHERE user_id = ? AND file_name = ?", (user_id, file_name))
                conn.commit()
            os.remove(path) 
            cursor.execute("DELETE FROM user_files WHERE user_id = ? AND file_name = ?", (user_id, file_name))
            conn.commit()
            bot.answer_callback_query(call.id, f"🗑️ تم مسح {file_name}.")
            logging.info(f"تم مسح ملف {file_name} بواسطة {user_id}")
        else:
            bot.answer_callback_query(call.id, "❌ الملف غير موجود.")
    elif data.startswith('install_missing:'):
        file_name = data.split(':')[1]
        if user_id in pending_installs and pending_installs[user_id]['file_name'] == file_name:
            missing_libs = pending_installs[user_id]['missing_libs']
            installed = []
            failed = []
            for lib in missing_libs:
                try:
                    subprocess.run(["pip", "install", lib], check=True)
                    installed.append(lib)
                except subprocess.CalledProcessError as e:
                    failed.append(lib)
                    logging.error(f"فشل تثبيت المكتبة {lib}: {str(e)}")
            if failed:
                bot.send_message(call.message.chat.id, f"❌ فشل في تثبيت: {', '.join(failed)}")
            if installed:
                bot.send_message(call.message.chat.id, f"✅ تم تثبيت: {', '.join(installed)}")
            bot.answer_callback_query(call.id, "✅ تم تثبيت المكاتب المفقودة إن وجدت.")
            file_path = pending_installs[user_id]['file_path']
            upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO user_files (user_id, file_name, file_path, upload_date) VALUES (?, ?, ?, ?)",
                           (user_id, file_name, file_path, upload_date))
            conn.commit()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(f"▶️ تشغيل {file_name}", callback_data=f"run_file:{file_name}:{user_id}"))
            bot.send_message(call.message.chat.id, f"📤 تم رفع واستضافة الملف {file_name} بنجاح بعد التثبيت!", reply_markup=markup)
            logging.info(f"تم رفع ملف {file_name} بواسطة {user_id} بعد تثبيت المكتبات")
            del pending_installs[user_id]

def admin_ban_user(message):
    try:
        user_id = int(message.text)
        cursor.execute("INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        bot.reply_to(message, f"🚫 تم حظر العضو {user_id} بنجاح!")
        logging.info(f"تم حظر {user_id} بواسطة الإداري")
    except ValueError:
        bot.reply_to(message, "❌ خطأ: أدخل ID صحيح.")

def admin_unban_user(message):
    try:
        user_id = int(message.text)
        cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.reply_to(message, f"✅ تم فك حظر العضو {user_id} بنجاح!")
        logging.info(f"تم فك حظر {user_id} بواسطة الإداري")
    except ValueError:
        bot.reply_to(message, "❌ خطأ: أدخل ID صحيح.")

def admin_broadcast_message(message):
    broadcast_msg = message.text
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    sent_count = 0
    for u in users:
        try:
            bot.send_message(u[0], broadcast_msg)
            sent_count += 1
        except:
            pass 
    bot.reply_to(message, f"📢 تم الإذاعة لـ {sent_count} مستخدم بنجاح!")
    logging.info(f"إذاعة بواسطة الإداري: {broadcast_msg}")

def admin_stop_file(message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError
        uid = int(parts[0])
        fname = parts[1]
        cursor.execute("SELECT file_path FROM user_files WHERE user_id = ? AND file_name = ?", (uid, fname))
        path = cursor.fetchone()
        if path:
            key = (uid, fname)
            if key in running_processes:
                running_processes[key].terminate()
                try:
                    running_processes[key].wait(timeout=5)
                except subprocess.TimeoutExpired:
                    running_processes[key].kill()
                del running_processes[key]
                cursor.execute("DELETE FROM running_processes WHERE user_id = ? AND file_name = ?", (uid, fname))
                conn.commit()
            os.remove(path[0])
            cursor.execute("DELETE FROM user_files WHERE user_id = ? AND file_name = ?", (uid, fname))
            conn.commit()
            bot.reply_to(message, f"⏹️ تم إيقاف ومسح الملف {fname} للمستخدم {uid} بنجاح!")
            logging.info(f"تم إيقاف ملف {fname} لـ {uid} بواسطة الإداري")
        else:
            bot.reply_to(message, "❌ الملف أو المستخدم غير موجود.")
    except ValueError:
        bot.reply_to(message, "❌ خطأ: أدخل ID واسم الملف بشكل صحيح (مثال: 123456 file.py).")

rate_limits = defaultdict(list)
RATE_LIMIT_WINDOW = 60  
RATE_LIMIT_MAX = 5  

pending_installs = {} 
@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id

    now = time.time()
    rate_limits[user_id] = [t for t in rate_limits[user_id] if now - t < RATE_LIMIT_WINDOW]
    if len(rate_limits[user_id]) >= RATE_LIMIT_MAX:
        bot.reply_to(message, "🚫 تجاوزت حد الطلبات. انتظر قليلاً.")
        logging.warning(f"rate limit exceeded for user: {user_id}")
        return
    rate_limits[user_id].append(now)

    cursor.execute("SELECT * FROM banned_users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        bot.reply_to(message, "🚫 أنت محظور من استخدام البوت.")
        logging.warning(f"مستخدم محظور حاول رفع ملف: {user_id}")
        return

    if settings['bot_locked'] == 'True':
        bot.reply_to(message, "🔒 البوت مقفل حالياً.")
        return

    if settings['paid_mode'] == 'True' and not is_admin(user_id):
        bot.reply_to(message, "💰 الوضع المدفوع مفعل، غير متاح للمستخدمين العاديين.")
        return

    file_info = bot.get_file(message.document.file_id)
    file_name = message.document.file_name
    if not file_name.endswith('.py'):
        bot.reply_to(message, "❌ يرجى رفع ملف بايثون فقط (.py).")
        return

    if message.document.file_size > 1024 * 1024:
        bot.reply_to(message, "❌ الملف كبير جداً (حد أقصى 1MB).")
        return

    downloaded_file = bot.download_file(file_info.file_path)

    file_path = os.path.join('files', f"{user_id}_{file_name}")
    with open(file_path, 'wb') as f:
        f.write(downloaded_file)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        # Sevo Team
        ast.parse(code)

        imports = set()
        for node in ast.walk(ast.parse(code)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module.split('.')[0])

        missing_libs = [lib for lib in imports if importlib.util.find_spec(lib) is None]

        upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if missing_libs:
            missing_str = ', '.join(missing_libs)
            msg = f"⚠️ الملف {file_name} يحتوي على مكتبات غير مثبتة: {missing_str}."
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🛠️ تثبيت المكاتب المفقودة", callback_data=f"install_missing:{file_name}"))
            bot.reply_to(message, msg, reply_markup=markup)
            pending_installs[user_id] = {'file_name': file_name, 'missing_libs': missing_libs, 'file_path': file_path}
        else:
            cursor.execute("INSERT INTO user_files (user_id, file_name, file_path, upload_date) VALUES (?, ?, ?, ?)",
                           (user_id, file_name, file_path, upload_date))
            conn.commit()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(f"▶️ تشغيل {file_name}", callback_data=f"run_file:{file_name}:{user_id}"))
            bot.reply_to(message, f"📤 تم رفع واستضافة الملف {file_name} بنجاح!", reply_markup=markup)
            logging.info(f"تم رفع ملف {file_name} بواسطة {user_id}")
    except SyntaxError as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        bot.reply_to(message, f"❌ خطأ في صيغة الملف: {str(e)}")
        logging.error(f"خطأ في صيغة ملف {file_name}: {str(e)}")
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        bot.reply_to(message, f"❌ خطأ أثناء معالجة الملف: {str(e)}")
        logging.error(f"خطأ في رفع ملف {file_name}: {str(e)}")

#Saif Hassan
cursor.execute("SELECT user_id, file_name, pid FROM running_processes")
for row in cursor.fetchall():
    try:
        os.kill(row[2], 0)  # @nSEIF
    except OSError:
        cursor.execute("DELETE FROM running_processes WHERE pid = ?", (row[2],))
        conn.commit()

if __name__ == '__main__':
    logging.info("بدء تشغيل البوت...")
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        logging.error(f"خطأ عام في البوت: {str(e)}")
