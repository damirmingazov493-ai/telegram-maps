import asyncio
import os
import time
import random
import string
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from supabase import create_client, Client

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ База данных подключена")
except Exception as e:
    supabase = None
    print(f"❌ Ошибка БД: {e}")

# Генератор случайных кодов для приглашений (например, "ab12cd")
def generate_code():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

# --- API ДЛЯ КАРТЫ ---
async def handle_index(request):
    return web.FileResponse('./index.html')

# Обновление координат пользователя
async def handle_update_location(request):
    if not supabase: return web.json_response({"error": "DB error"}, status=500)
    data = await request.json()
    
    try:
        # Обновляем или вставляем координаты
        supabase.table("map_members").upsert({
            "room_id": data.get('room_id'),
            "user_id": data.get('user_id'),
            "first_name": data.get('first_name'),
            "latitude": data.get('latitude'),
            "longitude": data.get('longitude'),
            "updated_at": "now()"
        }, on_conflict="room_id,user_id").execute()
        
        return web.json_response({"status": "ok"})
    except Exception as e:
        print(f"Location error: {e}")
        return web.json_response({"error": str(e)}, status=500)

# Получение списка друзей в комнате
async def handle_get_friends(request):
    room_id = request.query.get('room_id')
    if not room_id or not supabase: return web.json_response([])
    
    try:
        res = supabase.table("map_members").select("*").eq("room_id", room_id).execute()
        return web.json_response(res.data)
    except Exception as e:
        return web.json_response([])

# Создание новой комнаты
async def handle_create_room(request):
    if not supabase: return web.json_response({"error": "DB error"}, status=500)
    data = await request.json()
    
    try:
        code = generate_code()
        res = supabase.table("map_rooms").insert({
            "invite_code": code,
            "creator_id": data.get('user_id')
        }).execute()
        
        return web.json_response({"room_id": res.data[0]['id'], "invite_code": code})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# Вход в комнату по коду
async def handle_join_room(request):
    invite_code = request.query.get('code')
    if not invite_code or not supabase: return web.json_response({"error": "Invalid code"}, status=404)
    
    try:
        res = supabase.table("map_rooms").select("id").eq("invite_code", invite_code).execute()
        if not res.data: return web.json_response({"error": "Комната не найдена"}, status=404)
        
        return web.json_response({"room_id": res.data[0]['id']})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_post('/api/location', handle_update_location)
    app.router.add_get('/api/friends', handle_get_friends)
    app.router.add_post('/api/create_room', handle_create_room)
    app.router.add_get('/api/join_room', handle_join_room)
    
    port = int(os.environ.get('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Сервер на порту {port}")

# --- БОТ ---
@dp.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(message: types.Message, command: CommandObject):
    # Если пользователь перешел по ссылке-приглашению
    invite_code = command.args
    web_app_url = f"{os.getenv('WEBAPP_URL')}?v={int(time.time())}&invite={invite_code}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Войти в комнату", web_app=WebAppInfo(url=web_app_url))]
    ])
    await message.answer(f"Тебя пригласили на карту! Жми кнопку, чтобы присоединиться.", reply_markup=keyboard)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    # Обычный запуск (создать новую карту)
    web_app_url = f"{os.getenv('WEBAPP_URL')}?v={int(time.time())}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Открыть Карту", web_app=WebAppInfo(url=web_app_url))]
    ])
    await message.answer("Привет! Открой карту, чтобы создать свою комнату или посмотреть, где ты находишься.", reply_markup=keyboard)

async def main():
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())