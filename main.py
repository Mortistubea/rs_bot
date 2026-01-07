import logging
import asyncio
import os
import json
from datetime import datetime

from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.utils import exceptions
from aiohttp import web
import aiohttp
import gspread
from google.oauth2.service_account import Credentials
from google.auth.exceptions import GoogleAuthError
import re

# ======================= CONFIG =======================
from data import BOT_TOKEN, ADMINS, SPREADSHEET_NAME, CREDENTIALS_FILE, HEADER_COLOR, SUCCESS_COLOR
from buttons import toshkent_tumanlari

API_TOKEN = BOT_TOKEN

# Render webhook sozlamalari
WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL", "https://rs-bot-6b9r.onrender.com")
WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Web server sozlamalari
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 5000))

logging.basicConfig(level=logging.INFO)

# ======================= KEEP ALIVE FUNKSIYASI =======================
async def keep_alive_pinger():
    """24/7 bot ishlashi uchun har 5 daqiqada 10 ta ping yuboradi"""
    await asyncio.sleep(60)  # Bot to'liq ishga tushguncha kutish
    
    ping_urls = [
        f"{WEBHOOK_HOST}/health",
        f"{WEBHOOK_HOST}/",
        f"{WEBHOOK_HOST}/sheet",
    ]
    
    ping_count = 0
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                # 10 ta ping yuborish
                for i in range(10):
                    for url in ping_urls:
                        try:
                            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                                if response.status == 200:
                                    ping_count += 1
                                    if ping_count % 30 == 0:  # Har 30 ta pingda log
                                        logging.info(f"✅ Keep-Alive: {ping_count} ping yuborildi | {datetime.now().strftime('%H:%M:%S')}")
                        except Exception as e:
                            logging.debug(f"Ping xatosi (normal): {e}")
                    
                    await asyncio.sleep(2)  # Har bir ping orasida 2 soniya
            
            # 5 daqiqa kutish (300 soniya)
            await asyncio.sleep(270)  # 270 + 30 (10 ping x 3 url x 2s) = ~300s
            
        except Exception as e:
            logging.error(f"❌ Keep-alive global xato: {e}")
            await asyncio.sleep(60)

# ======================= GOOGLE SHEETS SETUP =======================
class GoogleSheetsManager:
    def __init__(self):
        self.sheet = None
        self.worksheet = None
        self.connected = False
        self.connect()
    
    def connect(self):
        """Google Sheets ga ulanish"""
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive.file',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Environment variable dan JSON yuklab olish
            creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
            
            if creds_json:
                try:
                    creds_dict = json.loads(creds_json)
                    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
                    logging.info("✅ Credentials environment variable dan yuklandi")
                except json.JSONDecodeError as e:
                    logging.error(f"❌ JSON parse xatosi: {e}")
                    return False
            elif os.path.exists(CREDENTIALS_FILE):
                creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
                logging.info("✅ Credentials fayldan yuklandi")
            else:
                logging.error(f"❌ Credentials topilmadi! Environment variable yoki fayl kerak.")
                return False
            
            client = gspread.authorize(creds)
            
            # Spreadsheet ni ochish yoki yaratish
            try:
                self.sheet = client.open(SPREADSHEET_NAME)
            except gspread.SpreadsheetNotFound:
                self.sheet = client.create(SPREADSHEET_NAME)
                self.sheet.share('', perm_type='anyone', role='writer')
                logging.info(f"✅ Yangi spreadsheet yaratildi: {SPREADSHEET_NAME}")
            
            # Worksheet ni tekshirish yoki yaratish
            try:
                self.worksheet = self.sheet.get_worksheet(0)
            except:
                self.worksheet = self.sheet.add_worksheet(title="Foydalanuvchilar", rows=1000, cols=20)
            
            # Agar bo'sh bo'lsa, headerlar qo'shish
            if not self.worksheet.get('A1'):
                headers = [
                    ['№', 'Ism', 'Tuman', 'Telefon', 'User ID', 'To\'liq Ism', 
                     'Username', 'Ro\'yxatdan o\'tgan sana', 'Vaqt', 'Status']
                ]
                self.worksheet.update(values=headers, range_name='A1:J1')
                self.worksheet.format('A1:J1', {
                    "backgroundColor": {"red": 0.29, "green": 0.53, "blue": 0.91},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    "horizontalAlignment": "CENTER"
                })
                logging.info("✅ Google Sheets headerlar qo'shildi")
            
            self.connected = True
            logging.info("✅ Google Sheets ga muvaffaqiyatli ulandı")
            return True
            
        except GoogleAuthError as e:
            logging.error(f"❌ Google autentifikatsiya xatosi: {e}")
            return False
        except Exception as e:
            logging.error(f"❌ Google Sheets ga ulanishda xatolik: {e}")
            return False
    
    def add_user(self, user_data):
        """Yangi foydalanuvchini Google Sheets ga qo'shish"""
        if not self.connected or not self.worksheet:
            logging.error("❌ Google Sheets ga ulanmagan!")
            return False
        
        try:
            all_values = self.worksheet.get_all_values()
            next_row = len(all_values) + 1
            
            row_data = [
                next_row - 1,
                user_data['name'],
                user_data['location'],
                user_data['phone'],
                user_data['user_id'],
                user_data['full_name'],
                user_data['username'],
                datetime.now().strftime('%Y-%m-%d'),
                datetime.now().strftime('%H:%M:%S'),
                "✅ Ro'yxatdan o'tgan"
            ]
            
            # TUZATILGAN: named arguments ishlatildi
            self.worksheet.update(values=[row_data], range_name=f'A{next_row}:J{next_row}')
            
            self.worksheet.format(f'A{next_row}:J{next_row}', {
                "backgroundColor": {"red": 0.58, "green": 0.77, "blue": 0.49},
                "textFormat": {"bold": False}
            })
            
            logging.info(f"✅ Foydalanuvchi Google Sheets ga qo'shildi: {user_data['name']}")
            return True
            
        except Exception as e:
            logging.error(f"❌ Google Sheets ga yozishda xatolik: {e}")
            return False

gs_manager = GoogleSheetsManager()

# ======================= STATES =======================
class Register(StatesGroup):
    name = State()
    location = State()
    phone = State()

# ======================= BOT SETUP =======================
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=storage)

# ======================= HANDLERS =======================

@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    try:
        if message.from_user.id in ADMINS:
            current_state = await dp.current_state(user=message.from_user.id).get_state()
            if current_state:
                await dp.current_state(user=message.from_user.id).finish()
            
            await message.reply(
                f"👋 <b>Xush kelibsiz, Admin!</b>\n\n"
                f"🤖 <b>Admin panel:</b>\n"
                f"📊 /stats - Statistika\n"
                f"📁 /export - Google Sheets havolasi\n"
                f"👥 /users - Foydalanuvchilar\n\n"
                f"📈 <b>Holat:</b>\n"
                f"• Google Sheets: {'✅ Ulangan' if gs_manager.connected else '❌ Ulanmagan'}\n"
                f"• Keep-Alive: ✅ Faol\n",
                parse_mode="HTML"
            )
        else:
            await message.reply(
                f"Assalomu Alaykum, <b>{message.from_user.full_name}</b> 😊\n"
                "Autizm haqidagi qo'llanmani olish uchun 3 qadam qoldi 🤩 \n\n<b>1-qadam:</b>\n"
                "Ismingizni kiriting:",
                parse_mode="HTML"
            )
            await Register.name.set()
    except Exception as e:
        logging.error(f"❌ send_welcome xatosi: {e}")

@dp.message_handler(state=Register.name)
async def process_name(message: types.Message, state: FSMContext):
    try:
        name = message.text.strip()
        if not name.replace(" ", "").isalpha() or len(name) < 2:
            await message.reply("❌ Iltimos, to'g'ri ism kiriting (faqat harflardan iborat bo'lsin)")
            return
        await state.update_data(name=name)
        await Register.location.set()
        await message.reply(
            "📍 Toshkent shahrining qaysi tumanida yashaysiz?",
            reply_markup=toshkent_tumanlari
        )
    except Exception as e:
        logging.error(f"❌ process_name xatosi: {e}")

@dp.message_handler(state=Register.location)
async def process_location(message: types.Message, state: FSMContext):
    try:
        location = message.text
        await state.update_data(location=location)
        await Register.phone.set()
        
        contact_button = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        contact_button.add(types.KeyboardButton("📱 Telefon raqamini yuborish", request_contact=True))
        contact_button.add(types.KeyboardButton("✏️ Raqamni qo'lda kiritish"))
        
        await message.reply(
            "✅ <b>2-qadam:</b>\n\n"
            "Telefon raqamingizni kiriting:\n\n"
            "📱 <i>Telefon raqamini yuborish</i> tugmasini bosing yoki\n"
            "📝 <i>Raqamni qo'lda kiritish</i> tugmasini bosib, raqamingizni kiriting\n\n"
            "Namuna: <code>901234567</code>",
            parse_mode="HTML",
            reply_markup=contact_button
        )
    except Exception as e:
        logging.error(f"❌ process_location xatosi: {e}")

@dp.message_handler(content_types=['contact', 'text'], state=Register.phone)
async def process_phone(message: types.Message, state: FSMContext):
    try:
        phone = ""
        if message.contact:
            phone = message.contact.phone_number
            if phone.startswith('+'):
                phone = phone
            elif phone.startswith('998'):
                phone = f"+{phone}"
            else:
                phone = f"+998{phone[-9:]}"
        else:
            phone_text = message.text
            
            if phone_text == "✏️ Raqamni qo'lda kiritish":
                await message.reply(
                    "📝 Telefon raqamingizni kiriting:\n"
                    "Namuna: <code>901234567</code> yoki <code>+998901234567</code>",
                    parse_mode="HTML",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return
            
            phone_digits = re.sub(r'\D', '', phone_text)
            
            if len(phone_digits) == 9:
                phone = f"+998{phone_digits}"
            elif len(phone_digits) == 12 and phone_digits.startswith('998'):
                phone = f"+{phone_digits}"
            elif len(phone_digits) == 13 and phone_digits.startswith('998'):
                phone = f"+{phone_digits}"
            elif len(phone_digits) == 10 and phone_digits.startswith('8'):
                phone = f"+7{phone_digits[1:]}"
            elif phone_text.startswith('+'):
                phone = phone_text
            else:
                await message.reply(
                    "❌ Noto'g'ri telefon raqami formati!\n\n"
                    "✅ Qabul qilinadigan formatlar:\n"
                    "• <code>901234567</code>\n"
                    "• <code>+998901234567</code>\n"
                    "• <code>998901234567</code>",
                    parse_mode="HTML"
                )
                return
        
        data = await state.get_data()
        user_name = data.get('name')
        location = data.get('location')
        
        user_data = {
            "name": user_name,
            "location": location,
            "phone": phone,
            "user_id": message.from_user.id,
            "full_name": message.from_user.full_name,
            "username": message.from_user.username if message.from_user.username else '',
        }

        gs_success = gs_manager.add_user(user_data)
        
        admin_message = (
            f"🎯 <b>Yangi ro'yxatdan o'tish:</b>\n\n"
            f"👤 <b>Ism:</b> {user_name}\n"
            f"📍 <b>Tuman:</b> {location}\n"
            f"📱 <b>Telefon:</b> {phone}\n"
            f"🆔 <b>User ID:</b> {message.from_user.id}\n"
            f"📛 <b>To'liq ism:</b> {message.from_user.full_name}\n"
            f"👤 <b>Username:</b> @{message.from_user.username if message.from_user.username else 'yoq'}\n"
            f"📅 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📊 <b>Google Sheets:</b> {'✅ Saqlandi' if gs_success else '❌ Saqlanmadi'}\n\n"
            f"#yangi_royhat"
        )
        
        if not gs_success:
            admin_message += "\n\n⚠️ <b>Google Sheets ga saqlanmadi!</b>"
        
        if ADMINS:
            for admin_id in ADMINS:
                try:
                    await bot.send_message(admin_id, admin_message, parse_mode="HTML")
                except exceptions.TelegramAPIError as e:
                    logging.error(f"Admin {admin_id} ga xabar yuborishda xatolik: {e}")
        
        await state.finish()
        
        success_message = "✅ Siz muvaffaqiyatli ro'yxatdan o'tdingiz!\n\n"
        if not gs_success:
            success_message += "⚠️ <i>Ma'lumotlaringiz saqlanmadi. Admin bilan bog'laning.</i>\n\n"
        
        success_message += "📚 Marhamat, autizm haqidagi maxsus qo'llanma:"
        
        try:
            await message.reply(success_message, parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
            await message.reply_document(
                document=open("Autizm.pdf", "rb"),
                caption="",
                parse_mode="HTML"
            )
        except FileNotFoundError:
            await message.reply(
                f"{success_message}\n\n❌ Qo'llanma fayli hozirda mavjud emas.",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"PDF yuborishda xatolik: {e}")
            await message.reply(
                f"{success_message}\n\n❌ Qo'llanmani olishda texnik muammo yuz berdi.",
                parse_mode="HTML"
            )
    except Exception as e:
        logging.error(f"❌ process_phone xatosi: {e}")
        await message.reply("❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring yoki /start ni bosing.")

# ======================= ADMIN KOMANDALARI =======================
@dp.message_handler(commands=['admin'], user_id=ADMINS)
async def admin_panel(message: types.Message):
    try:
        await message.reply(
            f"👋 <b>Xush kelibsiz, Admin!</b>\n\n"
            f"🤖 <b>Admin panel:</b>\n"
            f"📊 /stats - Statistika ko'rish\n"
            f"📁 /export - Google Sheets havolasi\n"
            f"👥 /users - Foydalanuvchilar ro'yxati\n\n"
            f"📈 <b>Bot holati:</b>\n"
            f"• Google Sheets: {'✅ Ulangan' if gs_manager.connected else '❌ Ulanmagan'}\n"
            f"• Adminlar soni: {len(ADMINS)}\n"
            f"• Keep-Alive: ✅ Faol (24/7)\n"
            f"• Bot ishlayapti: ✅",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"❌ admin_panel xatosi: {e}")

@dp.message_handler(commands=['stats'], user_id=ADMINS)
async def get_stats(message: types.Message):
    try:
        if not gs_manager.connected or not gs_manager.worksheet:
            await message.reply("❌ Google Sheets ga ulanmagan!")
            return
        
        all_values = gs_manager.worksheet.get_all_values()
        total_users = len(all_values) - 1
        
        if total_users == 0:
            await message.reply("📊 <b>Statistika:</b>\n\n❌ Hali hech qanday foydalanuvchi ro'yxatdan o'tmagan.", parse_mode="HTML")
            return
        
        locations = {}
        for row in all_values[1:]:
            if len(row) > 2 and row[2]:
                tuman = row[2]
                locations[tuman] = locations.get(tuman, 0) + 1
        
        stats_message = f"📊 <b>Statistika:</b>\n\n"
        stats_message += f"👥 <b>Jami ro'yxatdan o'tganlar:</b> {total_users} ta\n\n"
        
        if locations:
            stats_message += f"📍 <b>Tumanlar bo'yicha:</b>\n"
            for tuman, count in sorted(locations.items(), key=lambda x: x[1], reverse=True):
                stats_message += f"  • {tuman}: {count} ta\n"
        
        stats_message += f"\n⏰ <b>Oxirgi 3 ta ro'yxatdan o'tgan:</b>\n"
        last_3 = all_values[-3:] if len(all_values) > 3 else all_values[1:]
        for i, row in enumerate(last_3, 1):
            if len(row) > 1:
                stats_message += f"  {i}. {row[1]} - {row[2]} - {row[3]}\n"
        
        await message.reply(stats_message, parse_mode="HTML")
        
    except Exception as e:
        logging.error(f"Statistika olishda xatolik: {e}")
        await message.reply(f"❌ Statistika olishda xatolik: {str(e)}")

@dp.message_handler(commands=['users'], user_id=ADMINS)
async def get_users(message: types.Message):
    try:
        if not gs_manager.connected or not gs_manager.worksheet:
            await message.reply("❌ Google Sheets ga ulanmagan!")
            return
        
        all_values = gs_manager.worksheet.get_all_values()
        if len(all_values) <= 1:
            await message.reply("📋 <b>Foydalanuvchilar ro'yxati:</b>\n\n❌ Hali hech qanday foydalanuvchi ro'yxatdan o'tmagan.", parse_mode="HTML")
            return
        
        users_list = "📋 <b>Oxirgi 10 ta foydalanuvchi:</b>\n\n"
        start_idx = max(1, len(all_values) - 10)
        
        for i, row in enumerate(all_values[start_idx:], start_idx):
            if len(row) > 3:
                users_list += f"<b>{row[0]}.</b> {row[1]} - {row[2]}\n"
                users_list += f"   📱 {row[3]}\n"
                users_list += f"   📅 {row[7]} {row[8]}\n"
                users_list += "   ────────\n"
        
        users_list += f"\n<b>Jami:</b> {len(all_values)-1} ta foydalanuvchi"
        
        await message.reply(users_list, parse_mode="HTML")
        
    except Exception as e:
        logging.error(f"Foydalanuvchilar ro'yxatini olishda xatolik: {e}")
        await message.reply(f"❌ Foydalanuvchilar ro'yxatini olishda xatolik: {str(e)}")

@dp.message_handler(commands=['export'], user_id=ADMINS)
async def export_data(message: types.Message):
    try:
        if not gs_manager.connected or not gs_manager.sheet:
            await message.reply("❌ Google Sheets ga ulanmagan!")
            return
        
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{gs_manager.sheet.id}"
        
        await message.reply(
            f"📊 <b>Ma'lumotlar Google Sheets da:</b>\n\n"
            f"🔗 <a href='{spreadsheet_url}'>Havolani ochish</a>\n\n"
            f"📋 Foydalanuvchilar ro'yxati ushbu havolada saqlanmoqda.",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logging.error(f"Exportda xatolik: {e}")
        await message.reply(f"❌ Export qilishda xatolik: {str(e)}")

@dp.message_handler(commands=['cancel'], state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    try:
        current_state = await state.get_state()
        if current_state is None:
            await message.reply("⚠️ Hozir hech qanday amal bajarilmagan.")
            return
        
        await state.finish()
        await message.reply(
            "❌ Ro'yxatdan o'tish bekor qilindi.\n\n"
            "Qaytadan boshlash uchun /start ni bosing.",
            reply_markup=types.ReplyKeyboardRemove()
        )
    except Exception as e:
        logging.error(f"❌ cancel_handler xatosi: {e}")

@dp.message_handler(commands=['restart'])
async def restart_handler(message: types.Message):
    await send_welcome(message)

@dp.message_handler(state='*')
async def handle_all_messages(message: types.Message):
    try:
        current_state = await dp.current_state().get_state()
        if current_state:
            await message.reply(
                "❌ Iltimos, kerakli amalni bajaring.\n"
                "Davom etish uchun kerakli ma'lumotni kiriting yoki\n"
                "Bekor qilish uchun /cancel ni bosing.",
                reply_markup=types.ReplyKeyboardRemove()
            )
    except Exception as e:
        logging.error(f"❌ handle_all_messages xatosi: {e}")

# ======================= WEBHOOK SETUP =======================
async def on_startup(dp):
    """Webhook o'rnatish va Keep-Alive ishga tushirish"""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
        await bot.set_webhook(WEBHOOK_URL)
        logging.info(f"✅ Webhook o'rnatildi: {WEBHOOK_URL}")
        
        # Keep-Alive task ni ishga tushirish
        asyncio.create_task(keep_alive_pinger())
        logging.info("✅ Keep-Alive task ishga tushdi (24/7 rejim)")
        
    except Exception as e:
        logging.error(f"❌ Webhook o'rnatishda xatolik: {e}")

async def on_shutdown(dp):
    """Webhook o'chirish"""
    try:
        await bot.delete_webhook()
        logging.info("✅ Webhook o'chirildi")
    except Exception as e:
        logging.error(f"❌ Webhook o'chirishda xatolik: {e}")

# ======================= WEB SERVER =======================
async def health_check(request):
    """Health check endpoint"""
    try:
        return web.json_response({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "google_sheets": gs_manager.connected,
            "keep_alive": "active"
        })
    except Exception as e:
        logging.error(f"❌ health_check xatosi: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def sheet_info(request):
    """Google Sheets info"""
    try:
        if gs_manager.connected and gs_manager.sheet:
            return web.Response(
                text=f'<h1>Google Sheets Status</h1>'
                     f'<p>✅ Connected</p>'
                     f'<p>Spreadsheet ID: {gs_manager.sheet.id}</p>'
                     f'<p><a href="https://docs.google.com/spreadsheets/d/{gs_manager.sheet.id}" target="_blank">Open Spreadsheet</a></p>'
                     f'<p>Keep-Alive: Active 24/7</p>',
                content_type='text/html'
            )
        return web.Response(text="Google Sheets ga ulanmagan")
    except Exception as e:
        logging.error(f"❌ sheet_info xatosi: {e}")
        return web.Response(text=f"Xatolik: {str(e)}", status=500)

async def root_handler(request):
    """Root endpoint"""
    return web.Response(
        text=f'<h1>Bot Status: Running ✅</h1>'
             f'<p>Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>'
             f'<p>Keep-Alive: Active 24/7 🔄</p>'
             f'<p><a href="/health">Health Check</a></p>'
             f'<p><a href="/sheet">Google Sheets</a></p>',
        content_type='text/html'
    )

# =================== MAIN ===================
if __name__ == "__main__":
    logging.info("🤖 Bot ishga tushmoqda (Webhook + Keep-Alive rejimida)...")
    logging.info("🔄 24/7 Keep-Alive: Har 5 daqiqada 10 ta ping yuboriladi")
    
    if not gs_manager.connected:
        logging.warning("⚠️ Google Sheets ga ulanmagan! Ma'lumotlar faqat Telegramda saqlanadi.")
    
    # Web app yaratish
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/health', health_check)
    app.router.add_get('/sheet', sheet_info)
    app.router.add_post(WEBHOOK_PATH, lambda request: executor.webhook_request_handler(dp, request))
    
    # TUZATILGAN: executor.start_polling O'RNIGA web.run_app ishlatamiz
    # Web serverni ishga tushirish
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)
    # Bot ishga tushirish
