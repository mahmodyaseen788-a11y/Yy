from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError, PhoneCodeInvalidError, PasswordHashInvalidError
import json
import os
import asyncio

API_ID = 34553302
API_HASH = "062754e6a468d6f60b74e8abfe492664"
BOT_TOKEN = "8744705153:AAERTeIInGod9S_CY95tP71NFVDBxBW6wUA"
ADMIN_ID = 8283353929

CONFIG_FILE = "config3.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"session": None, "group_id": None, "wasta_ids": [], "reply_text": "س"}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


config = load_config()
state = {}
temp_login = {}

bot = TelegramClient("panel3_session", API_ID, API_HASH)
user_client = None


def main_menu():
    status = "متصل ✅" if config["session"] else "غير متصل ❌"
    group = str(config["group_id"]) if config["group_id"] else "غير محدد"
    wasta_count = len(config["wasta_ids"])
    return [
        [Button.inline(f"🔐 حساب الوسيط: {status}", b"login")],
        [Button.inline(f"👥 القروب: {group}", b"group")],
        [Button.inline(f"🧑‍💼 الوسطاء ({wasta_count})", b"wasta")],
        [Button.inline(f"💬 الرد: {config['reply_text']}", b"reply")],
    ]


async def show_menu(event):
    await event.respond("لوحة تحكم بوت الوسيط", buttons=main_menu())


@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    if event.sender_id != ADMIN_ID:
        return
    state.pop(event.sender_id, None)
    await show_menu(event)


@bot.on(events.CallbackQuery)
async def callback(event):
    if event.sender_id != ADMIN_ID:
        return
    data = event.data.decode()

    if data == "login":
        if config["session"]:
            await event.answer("الحساب متصل مسبقا", alert=True)
            return
        state[event.sender_id] = {"step": "phone"}
        await event.answer()
        await event.respond("أرسل رقم الهاتف مع رمز الدولة, مثال:\n+9665xxxxxxx")
        return

    if data == "group":
        if not config["session"]:
            await event.answer("سجل حساب الوسيط أولا", alert=True)
            return
        state[event.sender_id] = {"step": "group_id"}
        await event.answer()
        await event.respond(
            "حوّل أي رسالة من داخل قروب الوسطاء لهون وبحدد القروب تلقائي\n"
            "أو ابعت آيدي القروب مباشرة, مثال:\n-1001234567890"
        )
        return

    if data == "wasta":
        buttons = []
        for wid in config["wasta_ids"]:
            buttons.append([Button.inline(f"❌ {wid}", f"delw_{wid}".encode())])
        buttons.append([Button.inline("➕ إضافة وسيط", b"addw")])
        await event.answer()
        await event.respond("قائمة الوسطاء, اضغط على أي اسم لحذفه", buttons=buttons)
        return

    if data == "addw":
        if not config["session"]:
            await event.answer("سجل حساب الوسيط أولا", alert=True)
            return
        state[event.sender_id] = {"step": "add_wasta"}
        await event.answer()
        await event.respond("أرسل آيدي الوسيط رقم أو يوزره @username")
        return

    if data.startswith("delw_"):
        wid = int(data.split("_", 1)[1])
        if wid in config["wasta_ids"]:
            config["wasta_ids"].remove(wid)
            save_config(config)
        await event.answer("تم الحذف", alert=True)
        return

    if data == "reply":
        state[event.sender_id] = {"step": "reply_text"}
        await event.answer()
        await event.respond("أرسل نص الرد الجديد")
        return


@bot.on(events.NewMessage)
async def messages(event):
    if event.sender_id != ADMIN_ID:
        return
    st = state.get(event.sender_id)
    if not st:
        return
    step = st["step"]
    text = event.raw_text.strip()

    if step == "phone":
        old_client = temp_login.get("client")
        if old_client and old_client.is_connected():
            await old_client.disconnect()
        temp_login.clear()
        temp_login["phone"] = text
        temp_login["client"] = TelegramClient(StringSession(), API_ID, API_HASH)
        await temp_login["client"].connect()
        sent = await temp_login["client"].send_code_request(text)
        temp_login["hash"] = sent.phone_code_hash
        st["step"] = "code"
        await event.respond("أرسل كود التفعيل, وحط بين كل رقم ورقم مسافة أو نقطة, مثال:\n1 2 3 4 5")
        return

    if step == "code":
        code = "".join(ch for ch in text if ch.isdigit())
        try:
            await temp_login["client"].sign_in(temp_login["phone"], code, phone_code_hash=temp_login["hash"])
        except SessionPasswordNeededError:
            st["step"] = "password"
            await event.respond("الحساب محمي بكلمة مرور, أرسلها")
            return
        except (PhoneCodeExpiredError, PhoneCodeInvalidError):
            await restart_login(event, "الكود منتهي أو غلط, أرسل رقم الهاتف من جديد")
            return
        await finish_login(event)
        return

    if step == "password":
        try:
            await temp_login["client"].sign_in(password=text)
        except PasswordHashInvalidError:
            await event.respond("كلمة المرور غلط, أرسلها من جديد")
            return
        await finish_login(event)
        return

    if step == "group_id":
        gid = None
        if event.forward and event.forward.chat_id:
            gid = event.forward.chat_id
        else:
            try:
                gid = int(text)
            except ValueError:
                gid = None
        if gid is None:
            await event.respond("تعذر تحديد القروب, ابعت آيدي صحيح أو حوّل رسالة من داخل القروب")
            return
        config["group_id"] = gid
        save_config(config)
        state.pop(event.sender_id, None)
        await start_userbot()
        await event.respond("تم تحديد القروب وتشغيل الرد")
        await show_menu(event)
        return

    if step == "add_wasta":
        wid = await resolve_wasta(text)
        if wid is None:
            await event.respond("تعذر تحديد الآيدي, حاول مرة أخرى")
            return
        if wid not in config["wasta_ids"]:
            config["wasta_ids"].append(wid)
            save_config(config)
        state.pop(event.sender_id, None)
        await event.respond("تمت الإضافة")
        await show_menu(event)
        return

    if step == "reply_text":
        config["reply_text"] = text
        save_config(config)
        state.pop(event.sender_id, None)
        await event.respond("تم تحديث الرد")
        await show_menu(event)
        return


async def restart_login(event, message):
    old_client = temp_login.get("client")
    if old_client and old_client.is_connected():
        await old_client.disconnect()
    temp_login.clear()
    state[event.sender_id] = {"step": "phone"}
    await event.respond(message)


async def finish_login(event):
    session_str = temp_login["client"].session.save()
    config["session"] = session_str
    save_config(config)
    await temp_login["client"].disconnect()
    temp_login.clear()
    state.pop(event.sender_id, None)
    await event.respond("تم تسجيل الدخول بنجاح")
    await start_userbot()
    await show_menu(event)


async def resolve_wasta(text):
    try:
        if text.startswith("@"):
            entity = await user_client.get_entity(text)
            return entity.id
        return int(text)
    except Exception:
        return None


async def start_userbot():
    global user_client
    if user_client and user_client.is_connected():
        return
    user_client = TelegramClient(StringSession(config["session"]), API_ID, API_HASH)
    await user_client.start()

    @user_client.on(events.NewMessage())
    async def handler(event):
        if not config["group_id"] or event.chat_id != config["group_id"]:
            return
        text = (event.raw_text or "").strip()
        if text != "وسيط":
            return
        if event.sender_id in config["wasta_ids"]:
            return
        await event.reply(config["reply_text"])

    asyncio.create_task(user_client.run_until_disconnected())


async def main():
    await bot.start(bot_token=BOT_TOKEN)
    if config["session"] and config["group_id"]:
        await start_userbot()
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
