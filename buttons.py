# buttons.py - Tugmalar fayli
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Toshkent tumanlari uchun reply keyboard
toshkent_tumanlari = ReplyKeyboardMarkup(
    resize_keyboard=True,
    one_time_keyboard=True,
    row_width=2
)

tumanlar = [
    "Olmazor", "Bektemir", "Mirzo Ulug'bek", "Sergeli",
    "Yashnobod", "Chilonzor", "Yunusobod", "Shayxontohur",
    "Uchtepa", "Yakkasaroy", "Mirobod"
]

for tuman in tumanlar:
    toshkent_tumanlari.add(KeyboardButton(tuman))

# Telefon raqami uchun keyboard
phone_keyboard = ReplyKeyboardMarkup(
    resize_keyboard=True,
    one_time_keyboard=True
)
phone_keyboard.add(
    KeyboardButton("📱 Telefon raqamini yuborish", request_contact=True)
)
phone_keyboard.add(
    KeyboardButton("✏️ Raqamni qo'lda kiritish")
)

# Bekor qilish uchun
cancel_keyboard = ReplyKeyboardMarkup(
    resize_keyboard=True
)
cancel_keyboard.add(
    KeyboardButton("/cancel")
)

# Eksport qilish
__all__ = ['toshkent_tumanlari', 'phone_keyboard', 'cancel_keyboard']
