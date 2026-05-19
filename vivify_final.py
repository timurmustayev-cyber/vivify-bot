"""
Vivify Bot — простая версия, один файл, без БД и Redis.
Данные хранятся в памяти (сбрасываются при перезапуске).

Установка:  pip install aiogram
Запуск:     python vivify_bot.py
"""

import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)

# ═══════════════════════════════════════════
#  ВСТАВЬ СВОЙ ТОКЕН СЮДА
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# ═══════════════════════════════════════════

REPLICATE_TOKEN = os.environ.get("REPLICATE_TOKEN", "")
FREE_DAILY_QUOTA = 3

logging.basicConfig(level=logging.INFO)
router = Router()

# Хранилище пользователей в памяти
users: dict[int, dict] = {}


def get_user(user_id: int) -> dict:
    if user_id not in users:
        users[user_id] = {
            "lang": "ru",
            "age_verified": False,
            "quota": FREE_DAILY_QUOTA,
            "tier": "free",
        }
    return users[user_id]


# ─── FSM ───

class S(StatesGroup):
    age_gate        = State()
    main_menu       = State()
    waiting_photo   = State()
    photo_received  = State()
    processing      = State()
    result          = State()
    paywall         = State()
    settings        = State()


# ─── Клавиатуры ───

def kb_age():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, мне 18+",  callback_data="age:yes")],
        [
            InlineKeyboardButton(text="🙅 Ещё нет",   callback_data="age:no"),
            InlineKeyboardButton(text="ℹ️ Зачем?",    callback_data="age:why"),
        ],
    ])

def kb_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Оживить портрет",  callback_data="feat:portrait")],
        [
            InlineKeyboardButton(text="🌅 Оживить сцену",  callback_data="feat:scene"),
            InlineKeyboardButton(text="🎞 Слайд-шоу",      callback_data="feat:slideshow"),
        ],
        [
            InlineKeyboardButton(text="✨ Реставрация",     callback_data="feat:restore"),
            InlineKeyboardButton(text="🌈 Колоризация",     callback_data="feat:color"),
        ],
        [
            InlineKeyboardButton(text="🎨 Стилизация",      callback_data="feat:style"),
            InlineKeyboardButton(text="🪄 Убрать фон",      callback_data="feat:bg"),
        ],
        [
            InlineKeyboardButton(text="📐 Апскейл",         callback_data="feat:upscale"),
            InlineKeyboardButton(text="📹 Текст → видео",   callback_data="feat:t2v"),
        ],
        [
            InlineKeyboardButton(text="💎 Тарифы",          callback_data="nav:pricing"),
            InlineKeyboardButton(text="⚙️ Настройки",       callback_data="nav:settings"),
        ],
    ])

def kb_reply():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Главное меню"), KeyboardButton(text="💎 Тарифы")],
            [KeyboardButton(text="⚙️ Настройки"),   KeyboardButton(text="🌐 EN")],
        ],
        resize_keyboard=True,
    )

def kb_upload():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📷 Камера",       callback_data="upload:cam"),
            InlineKeyboardButton(text="🖼 Из галереи",   callback_data="upload:gal"),
        ],
        [InlineKeyboardButton(text="← Назад в меню",     callback_data="nav:menu")],
    ])

def kb_anim():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="😊 Лёгкая улыбка",  callback_data="anim:smile"),
            InlineKeyboardButton(text="😉 Подмигнуть",     callback_data="anim:wink"),
        ],
        [
            InlineKeyboardButton(text="🎭 Поворот головы", callback_data="anim:turn"),
            InlineKeyboardButton(text="😱 Удивление",      callback_data="anim:surprise"),
        ],
        [
            InlineKeyboardButton(text="😂 Смех",           callback_data="anim:laugh"),
            InlineKeyboardButton(text="🤔 Задуматься",     callback_data="anim:think"),
        ],
        [InlineKeyboardButton(text="🎲 Случайная — удиви меня", callback_data="anim:random")],
    ])

def kb_processing():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Ускорить (Pro) →",  callback_data="nav:pricing")],
        [InlineKeyboardButton(text="✕ Отменить",           callback_data="gen:cancel")],
    ])

def kb_result():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Сохранить в галерею",    callback_data="result:save")],
        [
            InlineKeyboardButton(text="🔄 Ещё вариант",         callback_data="result:retry"),
            InlineKeyboardButton(text="📤 Поделиться",          callback_data="result:share"),
        ],
        [
            InlineKeyboardButton(text="🎬 Новое видео",         callback_data="result:new"),
            InlineKeyboardButton(text="⭐ Оценить",             callback_data="result:rate"),
        ],
    ])

def kb_paywall():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Подключить Pro — ₽499/мес", callback_data="buy:pro")],
        [
            InlineKeyboardButton(text="Lite ₽199",      callback_data="buy:lite"),
            InlineKeyboardButton(text="Premium ₽999",   callback_data="buy:premium"),
        ],
        [
            InlineKeyboardButton(text="🎁 Промокод",    callback_data="promo:enter"),
            InlineKeyboardButton(text="⏳ Подожду",     callback_data="paywall:skip"),
        ],
    ])

def kb_settings(lang="ru"):
    lang_label = "🌐 Switch to English" if lang == "ru" else "🌐 Переключить на Русский"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=lang_label,              callback_data="set:lang")],
        [InlineKeyboardButton(text="📊 Моя статистика",    callback_data="set:stats")],
        [InlineKeyboardButton(text="← Назад",               callback_data="nav:menu")],
    ])

def kb_back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← В главное меню", callback_data="nav:menu")],
    ])


# ─── Тексты ───

FEATURE_NAMES = {
    "portrait": "🎬 Оживить портрет",
    "scene": "🌅 Оживить сцену",
    "slideshow": "🎞 Слайд-шоу",
    "restore": "✨ Реставрация",
    "color": "🌈 Колоризация",
    "style": "🎨 Стилизация",
    "bg": "🪄 Убрать фон",
    "upscale": "📐 Апскейл",
    "t2v": "📹 Текст → видео",
}

def make_bar(pct: int, width: int = 13) -> str:
    filled = round(width * pct / 100)
    return "▓" * filled + "░" * (width - filled)


# ─── Хэндлеры ───

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if user["age_verified"]:
        await state.set_state(S.main_menu)
        await message.answer(
            f"<b>Что будем оживлять? 👀</b>\n\n"
            f"Тыкай в любую кнопку — расскажу подробнее.\n"
            f"Осталось <b>{user['quota']} бесплатных видео</b> сегодня.",
            reply_markup=kb_menu(),
        )
        await message.answer("⬆️", reply_markup=kb_reply())
        return

    await state.set_state(S.age_gate)
    await message.answer(
        "<b>Привет! Я — Vivify ✨</b>\n\n"
        "Превращаю обычные фотки в видосы, которые залипают:\n"
        "— оживляю портреты 😊\n"
        "— крашу старые ч/б 🎨\n"
        "— реставрирую бабушкины снимки 👵🏼\n"
        "— делаю слайд-шоу с переходами 🎬\n\n"
        "Прежде чем стартануть — тебе уже 18?"
    )
    await message.answer(
        "Это нужно по правилам Telegram и закона. Один раз — и больше не спрошу.",
        reply_markup=kb_age(),
    )


@router.callback_query(S.age_gate, F.data == "age:yes")
async def age_yes(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user = get_user(call.from_user.id)
    user["age_verified"] = True
    await call.message.edit_reply_markup(reply_markup=None)
    await state.set_state(S.main_menu)
    await call.message.answer(
        f"<b>Что будем оживлять? 👀</b>\n\n"
        f"Тыкай в любую кнопку — расскажу подробнее.\n"
        f"Осталось <b>{user['quota']} бесплатных видео</b> сегодня.",
        reply_markup=kb_menu(),
    )
    await call.message.answer("⬆️", reply_markup=kb_reply())


@router.callback_query(S.age_gate, F.data == "age:no")
async def age_no(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer("Возвращайся, когда исполнится 18 🤝")
    await state.clear()


@router.callback_query(S.age_gate, F.data == "age:why")
async def age_why(call: CallbackQuery):
    await call.answer(
        "Telegram требует подтверждения возраста для ботов с пользовательским контентом.",
        show_alert=True,
    )


# ─── Меню ───

async def show_menu(target: Message | CallbackQuery, state: FSMContext):
    user_id = target.from_user.id
    user = get_user(user_id)
    text = (
        f"<b>Что будем оживлять? 👀</b>\n\n"
        f"Тыкай в любую кнопку — расскажу подробнее.\n"
        f"Осталось <b>{user['quota']} бесплатных видео</b> сегодня."
    )
    await state.set_state(S.main_menu)
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=kb_menu())
    else:
        await target.answer(text, reply_markup=kb_menu())


@router.message(Command("menu"))
@router.message(F.text == "🎬 Главное меню")
async def cmd_menu(message: Message, state: FSMContext):
    await show_menu(message, state)


@router.callback_query(F.data == "nav:menu")
async def cb_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await show_menu(call, state)


# ─── Выбор фичи ───

@router.callback_query(F.data.startswith("feat:"))
async def cb_feature(call: CallbackQuery, state: FSMContext):
    feature = call.data.split(":")[1]
    await call.answer()
    user = get_user(call.from_user.id)

    if user["quota"] <= 0:
        await state.set_state(S.paywall)
        await call.message.answer(
            "<b>Упс 😅</b>\n\n"
            "Бесплатные 3 видео на сегодня закончились.\n"
            "Можно подождать до завтра — или подключить тариф 👇",
            reply_markup=kb_paywall(),
        )
        return

    await state.update_data(feature=feature)
    await state.set_state(S.waiting_photo)

    feat_name = FEATURE_NAMES.get(feature, feature)
    await call.message.answer(
        f"<b>Окей, погнали 🚀</b> — {feat_name}\n\n"
        "Кидай фотку сюда.\n\n"
        "<i>💡 Что зайдёт лучше всего:\n"
        "• лицо хорошо видно\n"
        "• без очков и масок\n"
        "• мин. разрешение 512×512</i>",
        reply_markup=kb_upload(),
    )


# ─── Загрузка фото ───

@router.message(S.waiting_photo, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(file_id=file_id)
    data = await state.get_data()
    feature = data.get("feature", "portrait")

    if feature == "portrait":
        await state.set_state(S.photo_received)
        await message.answer(
            "Огонь, фото принял ✅\nКакую <b>эмоцию</b> вдыхаем?",
            reply_markup=kb_anim(),
        )
    else:
        await start_generation(message, state)


@router.message(S.waiting_photo)
async def handle_no_photo(message: Message):
    await message.answer("Отправь фотографию 📸")


@router.callback_query(S.waiting_photo, F.data.in_({"upload:cam", "upload:gal"}))
async def cb_upload_hint(call: CallbackQuery):
    await call.answer("Просто отправь фото в чат 📸", show_alert=True)


# ─── Выбор анимации ───

ANIM_LABELS = {
    "smile": "😊 Лёгкая улыбка", "wink": "😉 Подмигнуть",
    "turn": "🎭 Поворот головы", "surprise": "😱 Удивление",
    "laugh": "😂 Смех", "think": "🤔 Задуматься", "random": "🎲 Случайная",
}

@router.callback_query(S.photo_received, F.data.startswith("anim:"))
async def cb_anim(call: CallbackQuery, state: FSMContext):
    anim = call.data.split(":")[1]
    await call.answer()
    await state.update_data(anim=anim)
    await start_generation(call.message, state, user_id=call.from_user.id)


# ─── Генерация (имитация с прогресс-баром) ───

async def run_replicate(file_id: str, feature: str, anim: str, bot: Bot) -> str | None:
    """Запустить генерацию через Replicate API."""
    import urllib.request, urllib.error, json, io

    # Скачать файл из Telegram
    file_info = await bot.get_file(file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    img_data = file_bytes.read() if hasattr(file_bytes, "read") else file_bytes

    # Конвертируем в base64 data URL
    import base64
    b64 = base64.b64encode(img_data).decode()
    data_url = f"data:image/jpeg;base64,{b64}"

    MODELS = {
        "portrait": ("stability-ai/stable-video-diffusion", {"input_frames": 25, "sizing_strategy": "maintain_aspect_ratio", "motion_bucket_id": 127, "cond_aug": 0.02}),
        "restore":  ("sczhou/codeformer", {"codeformer_fidelity": 0.7, "background_enhance": True, "face_upsample": True, "upscale": 2}),
        "color":    ("arielreplicate/deoldify_image", {"model_name": "Artistic", "render_factor": 35}),
        "upscale":  ("nightmareai/real-esrgan", {"scale": 4, "face_enhance": True}),
        "bg":       ("cjwbw/rembg", {"image": data_url}),
        "style":    ("tencentarc/photomaker-style", {"style_strength_radio": 20, "num_outputs": 1}),
    }

    model_id, extra_input = MODELS.get(feature, MODELS["portrait"])

    # Для portrait используем stable-video-diffusion
    if feature == "portrait":
        payload = {"version": "3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
                   "input": {"input_image": data_url, **extra_input}}
    elif feature == "restore":
        payload = {"version": "7de2ea26c616d5bf2245ad0d5e24f0ff9a6204578a5c876db53142edd9d2cd56",
                   "input": {"image": data_url, **extra_input}}
    elif feature == "color":
        payload = {"version": "0da600fab0c45a66211339f1c16b71345d22f26ef5fea3ddfdc21898f4d2e3e9",
                   "input": {"image": data_url, **extra_input}}
    elif feature == "upscale":
        payload = {"version": "42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73abf41610695738c1d7b",
                   "input": {"image": data_url, **extra_input}}
    elif feature == "bg":
        payload = {"version": "fb8af171cfa1616ddcf1242c093f9c46bcada5ad4cf6f2fbe8b81b330ec5c003",
                   "input": {"image": data_url}}
    else:
        payload = {"version": "3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
                   "input": {"input_image": data_url, "input_frames": 14, "sizing_strategy": "maintain_aspect_ratio"}}

    headers = {
        "Authorization": f"Token {REPLICATE_TOKEN}",
        "Content-Type": "application/json",
    }

    # Создать задачу
    req = urllib.request.Request(
        "https://api.replicate.com/v1/predictions",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            prediction = json.loads(resp.read())
        pred_id = prediction["id"]
    except Exception as e:
        logging.error(f"Replicate create failed: {e}")
        return None

    # Polling результата
    for _ in range(60):
        await asyncio.sleep(5)
        try:
            req2 = urllib.request.Request(
                f"https://api.replicate.com/v1/predictions/{pred_id}",
                headers=headers,
            )
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                result = json.loads(resp2.read())
            status = result.get("status")
            if status == "succeeded":
                output = result.get("output")
                if isinstance(output, list):
                    return output[0]
                return output
            elif status == "failed":
                logging.error(f"Replicate failed: {result.get('error')}")
                return None
        except Exception as e:
            logging.error(f"Replicate poll failed: {e}")

    return None


async def start_generation(message: Message, state: FSMContext, user_id: int = None):
    uid = user_id or message.chat.id
    user = get_user(uid)
    user["quota"] = max(0, user["quota"] - 1)

    await state.set_state(S.processing)

    data = await state.get_data()
    feature = data.get("feature", "portrait")
    anim = data.get("anim", "smile")
    feat_name = FEATURE_NAMES.get(feature, feature)
    file_id = data.get("file_id")

    prog_msg = await message.answer(
        f"<b>Делаю магию 🪄</b> — {feat_name}\n\n"
        f"<code>[{make_bar(0)}] 0%</code>\n"
        f"Осталось ~60 сек · позиция в очереди: 1",
        reply_markup=kb_processing(),
    )

    # Запускаем генерацию в фоне и обновляем прогресс-бар
    async def update_progress():
        steps = [(15, 50), (30, 40), (50, 30), (65, 20), (80, 10), (90, 5)]
        for pct, eta in steps:
            await asyncio.sleep(8)
            try:
                await prog_msg.edit_text(
                    f"<b>Делаю магию 🪄</b> — {feat_name}\n\n"
                    f"<code>[{make_bar(pct)}] {pct}%</code>\n"
                    f"Осталось ~{eta} сек · позиция в очереди: 1",
                    reply_markup=kb_processing(),
                )
            except Exception:
                pass

    progress_task = asyncio.create_task(update_progress())

    # Реальная генерация через Replicate
    result_url = None
    if file_id:
        result_url = await run_replicate(file_id, feature, anim, message.bot)

    progress_task.cancel()

    try:
        await prog_msg.edit_text("Загружаю результат... ⏳", reply_markup=None)
    except Exception:
        pass

    await state.set_state(S.result)
    quota_left = user["quota"]

    if result_url:
        # Отправить реальный результат
        try:
            if feature == "portrait" or result_url.endswith(".mp4") or result_url.endswith(".gif"):
                await message.answer_video(result_url,
                    caption=f"<b>Готово! 🎉</b>\nОсталось видео сегодня: <b>{quota_left}</b>",
                    reply_markup=kb_result())
            else:
                await message.answer_photo(result_url,
                    caption=f"<b>Готово! 🎉</b>\nОсталось видео сегодня: <b>{quota_left}</b>",
                    reply_markup=kb_result())
        except Exception:
            await message.answer(
                f"<b>Готово! 🎉</b>\n\n🔗 <a href=\"{result_url}\">Скачать результат</a>\n\nОсталось сегодня: <b>{quota_left}</b>",
                reply_markup=kb_result())
    else:
        await message.answer(
            f"<b>Что-то пошло не так 😢</b>\n\nReplicate не смог обработать фото. Попробуй другое фото или фичу.",
            reply_markup=kb_back_menu())


@router.callback_query(S.processing, F.data == "gen:cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Генерация отменена.", reply_markup=None)
    await state.set_state(S.main_menu)
    await call.message.answer("Вернись в меню 👇", reply_markup=kb_back_menu())


# ─── Результат ───

@router.callback_query(S.result, F.data == "result:new")
async def cb_new(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await show_menu(call, state)


@router.callback_query(S.result, F.data == "result:retry")
async def cb_retry(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await start_generation(call.message, state, user_id=call.from_user.id)


@router.callback_query(S.result, F.data == "result:save")
async def cb_save(call: CallbackQuery):
    await call.answer("Нажми и удержи видео → «Сохранить» 💾", show_alert=True)


@router.callback_query(S.result, F.data == "result:share")
async def cb_share(call: CallbackQuery):
    await call.answer()
    await call.message.answer("🔗 https://vivify.app/s/demo123")


@router.callback_query(S.result, F.data == "result:rate")
async def cb_rate(call: CallbackQuery):
    await call.answer()
    await call.message.answer(
        "Оцени качество ⭐",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=s, callback_data=f"rate:{i+1}")
            for i, s in enumerate(["⭐","⭐⭐","⭐⭐⭐","⭐⭐⭐⭐","⭐⭐⭐⭐⭐"])
        ]])
    )


@router.callback_query(F.data.startswith("rate:"))
async def cb_rate_val(call: CallbackQuery):
    stars = int(call.data.split(":")[1])
    await call.answer()
    await call.message.edit_text(f"Спасибо! {'⭐' * stars} Ценю 🙏")


# ─── Paywall ───

@router.message(Command("pricing"))
@router.message(F.text == "💎 Тарифы")
async def cmd_pricing(message: Message, state: FSMContext):
    await state.set_state(S.paywall)
    await message.answer(
        "<b>Тарифы Vivify 💎</b>\n\n"
        "┌ <b>Lite</b> — ₽199/мес\n"
        "│  20 видео · HD · водяной знак\n"
        "│\n"
        "├ <b>Pro ⭐</b> — ₽499/мес\n"
        "│  100 видео · FullHD · без знака · все стили\n"
        "│\n"
        "└ <b>Premium</b> — ₽999/мес\n"
        "   ∞ видео · 4K · приоритет · API\n\n"
        "Деньги возвращаем в течение 14 дней 🤝",
        reply_markup=kb_paywall(),
    )


@router.callback_query(F.data == "nav:pricing")
async def cb_pricing(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(S.paywall)
    await call.message.answer(
        "<b>Тарифы Vivify 💎</b>\n\n"
        "┌ <b>Lite</b> — ₽199/мес\n"
        "│  20 видео · HD · водяной знак\n"
        "│\n"
        "├ <b>Pro ⭐</b> — ₽499/мес\n"
        "│  100 видео · FullHD · без знака · все стили\n"
        "│\n"
        "└ <b>Premium</b> — ₽999/мес\n"
        "   ∞ видео · 4K · приоритет · API\n\n"
        "Деньги возвращаем в течение 14 дней 🤝",
        reply_markup=kb_paywall(),
    )


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery, state: FSMContext):
    tier = call.data.split(":")[1]
    prices = {"lite": "₽199", "pro": "₽499", "premium": "₽999"}
    await call.answer()
    await call.message.answer(
        f"💳 Оплата тарифа <b>{tier.capitalize()} {prices[tier]}/мес</b>\n\n"
        "Для подключения оплаты настрой YooKassa в BotFather:\n"
        "/mybots → Payments → ЮKassa\n\n"
        "<i>После настройки оплата будет работать прямо в боте.</i>",
        reply_markup=kb_back_menu(),
    )


@router.callback_query(F.data == "promo:enter")
async def cb_promo(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Введи промокод:")
    await state.set_state(S.settings)  # временно используем settings state


@router.callback_query(F.data == "paywall:skip")
async def cb_skip(call: CallbackQuery, state: FSMContext):
    await call.answer("Хорошо! Возвращайся завтра 🕐", show_alert=True)
    await show_menu(call, state)


# ─── Настройки ───

@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    await state.set_state(S.settings)
    await message.answer("<b>Настройки ⚙️</b>", reply_markup=kb_settings(user["lang"]))


@router.callback_query(F.data == "nav:settings")
async def cb_settings(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user = get_user(call.from_user.id)
    await state.set_state(S.settings)
    await call.message.answer("<b>Настройки ⚙️</b>", reply_markup=kb_settings(user["lang"]))


@router.callback_query(F.data == "set:lang")
async def cb_lang(call: CallbackQuery):
    await call.answer()
    user = get_user(call.from_user.id)
    user["lang"] = "en" if user["lang"] == "ru" else "ru"
    lang_name = "English 🇬🇧" if user["lang"] == "en" else "Русский 🇷🇺"
    await call.message.edit_text(
        f"Язык изменён: <b>{lang_name}</b>",
        reply_markup=kb_settings(user["lang"]),
    )


@router.callback_query(F.data == "set:stats")
async def cb_stats(call: CallbackQuery):
    await call.answer()
    user = get_user(call.from_user.id)
    await call.message.answer(
        f"📊 <b>Твоя статистика:</b>\n\n"
        f"Тариф: {user['tier'].capitalize()}\n"
        f"Осталось видео сегодня: {user['quota']}\n"
        f"Язык: {'RU' if user['lang'] == 'ru' else 'EN'}"
    )


# ─── Переключение языка через reply kbd ───

@router.message(F.text.in_({"🌐 EN", "🌐 RU"}))
async def toggle_lang(message: Message):
    user = get_user(message.from_user.id)
    user["lang"] = "en" if message.text == "🌐 EN" else "ru"
    lang_name = "English 🇬🇧" if user["lang"] == "en" else "Русский 🇷🇺"
    await message.answer(f"Язык: <b>{lang_name}</b>", reply_markup=kb_reply())


# ─── /help ───

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Vivify — помощь 🆘</b>\n\n"
        "/start — начать\n"
        "/menu — главное меню\n"
        "/pricing — тарифы\n"
        "/settings — настройки\n"
        "/help — эта справка\n\n"
        "По вопросам: @vivify_support"
    )


# ─── Запуск ───

async def main():
    if not BOT_TOKEN:
        print("❌ Вставь токен бота в переменную BOT_TOKEN в начале файла!")
        return

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    print("✅ Vivify бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
