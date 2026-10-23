# ====================================================================================================
# 🤖 BLACK STORE KEY - AUTOMATION SYSTEM (ULTIMATE UPDATE)
# ====================================================================================================

import asyncio
import sqlite3
import logging
import time
import aiohttp
import base64
from datetime import datetime
from typing import Any, Dict

from aiogram import Bot, Dispatcher, F, html
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ====================================================================================================
# [ កំណត់រចនាសម្ព័ន្ធទូទៅ ]
# ====================================================================================================

BOT_TOKEN = "8805862462:AAH0KyXj7F7TZRfQIJICPpQ2tjtqpEyVUxY"
OWNER_ID = 8371081776

# 🚀 ABA API CONFIGURATION
ABA_API_KEY = "sk_98c99cdfff01a78707b83590dd181d709c04869a721ce304"
ABA_MERCHANT_ID = "567011"
ABA_CREATE_URL = "https://khmer-system.com/aba-api/generate-qr"
ABA_CHECK_URL = "https://khmer-system.com/aba-api/check-payment"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("BLACK KEY STORE")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

background_tasks = set()
def run_bg_task(coro):
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

# ====================================================================================================
# [ មូលដ្ឋានទិន្នន័យ (DATABASE) ]
# ====================================================================================================

def init_db():
    conn = sqlite3.connect('zento_store.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, is_admin INTEGER DEFAULT 0, is_reseller INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, icon TEXT, media_data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INTEGER, name TEXT, price REAL, reseller_price REAL, icon TEXT, post_media TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stock (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, key_data TEXT, is_sold INTEGER DEFAULT 0, type TEXT DEFAULT 'text')''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    c.execute('INSERT OR IGNORE INTO users (id, is_admin) VALUES (?, 1)', (OWNER_ID,))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('contact_admin', '@Babysupport1'))
    conn.commit()
    conn.close()

def execute_db(query, params=(), fetch=False, fetchall=False):
    conn = sqlite3.connect('black_store.db', timeout=30)
    c = conn.cursor()
    try:
        c.execute(query, params)
        if fetchall: res = c.fetchall()
        elif fetch: res = c.fetchone()
        else: 
            conn.commit()
            res = c.lastrowid
        return res
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None
    finally:
        conn.close()

init_db()

# ====================================================================================================
# [ CUSTOM UI HELPERS ]
# ====================================================================================================

def IBtn(text, callback_data=None, style=None, icon_custom_emoji_id=None, url=None):
    btn = InlineKeyboardButton(text=text, url=url) if url else InlineKeyboardButton(text=text, callback_data=callback_data)
    if style: object.__setattr__(btn, 'style', style)
    if icon_custom_emoji_id and any(c.isdigit() for c in str(icon_custom_emoji_id)): 
        object.__setattr__(btn, 'icon_custom_emoji_id', str(icon_custom_emoji_id))
    return btn

def RBtn(text, style=None, icon_custom_emoji_id=None):
    btn = KeyboardButton(text=text)
    if style: object.__setattr__(btn, 'style', style)
    if icon_custom_emoji_id and any(c.isdigit() for c in str(icon_custom_emoji_id)): 
        object.__setattr__(btn, 'icon_custom_emoji_id', str(icon_custom_emoji_id))
    return btn

def cancel_inline():
    return InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="❌ បោះបង់", callback_data="cancel_action", style="danger")]])

def get_setting(key, default=None):
    res = execute_db('SELECT value FROM settings WHERE key=?', (key,), fetch=True)
    return res[0] if res else default

async def alert_to_channel(text):
    chan_id = get_setting('channel_id')
    if chan_id:
        try: await bot.send_message(chan_id, text)
        except: pass

def get_emoji_str(icon_id, fallback=""):
    return f"<tg-emoji emoji-id='{icon_id}'>{fallback}</tg-emoji>" if icon_id else fallback

# ====================================================================================================
# [ ABA API FUNCTIONS ]
# ====================================================================================================

async def aba_generate_qr_async(amount, ref_id):
    payload = {"api_key": ABA_API_KEY, "merchant_id": ABA_MERCHANT_ID, "username": str(ref_id)[:64], "amount": round(float(amount), 2)}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ABA_CREATE_URL, json=payload, timeout=25) as resp:
                return await resp.json()
    except Exception as e:
        return None

async def aba_check_paid_async(payment_id):
    payload = {"api_key": ABA_API_KEY, "merchant_id": ABA_MERCHANT_ID, "payment_id": payment_id}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ABA_CHECK_URL, json=payload, timeout=20) as resp:
                data = await resp.json()
                st = str(data.get("status") or (data.get("data") or {}).get("status") or "").upper()
                return "PAID" in st or "SUCCESS" in st or data.get("paid") is True
    except: return False

# ====================================================================================================
# [ FSM STATES ]
# ====================================================================================================

class OrderFSM(StatesGroup): custom_qty = State()
class AdminAddCat(StatesGroup): name = State(); icon = State()
class AdminAddItem(StatesGroup): cat_id = State(); name = State(); price = State(); reseller_price = State(); icon = State()
class AdminAddStock(StatesGroup): item_id = State(); keys = State()
class AdminBroadcast(StatesGroup): msg = State()
class AdminReseller(StatesGroup): add_id = State(); del_id = State()
class AdminChannel(StatesGroup): channel_id = State()
class AdminStartMedia(StatesGroup): media = State()
class AdminCatMedia(StatesGroup): cat_id = State(); media = State()
class AdminPostMedia(StatesGroup): item_id = State(); media = State()
class AdminContact(StatesGroup): link = State()

# ====================================================================================================
# [ ផ្នែក USER - មីនុយទូទៅ ]
# ====================================================================================================

@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    
    user_exists = execute_db('SELECT id FROM users WHERE id=?', (msg.from_user.id,), fetch=True)
    if not user_exists:
        execute_db('INSERT INTO users (id) VALUES (?)', (msg.from_user.id,))
        # Alert to channel
        u_name = msg.from_user.first_name or "Unknown"
        u_user = f"@{msg.from_user.username}" if msg.from_user.username else "គ្មាន"
        alert_text = f"🎉មានអ្នកចុះឈ្មោះចូលបតទៀតហើយ!\n-  ID  : <code>{msg.from_user.id}</code>\n- Name : {u_name}\n- Username : {u_user}\n- សូមបងប្រើប្រាស់បតញុមតាមសម្បាយចុះ !"
        await alert_to_channel(alert_text)

    is_admin = execute_db('SELECT is_admin FROM users WHERE id=?', (msg.from_user.id,), fetch=True)[0]
    
    # ជួសជុលកន្លែងនេះ: style="primary" ជំនួសអោយ "secondary"
    kb = [
        [RBtn(text="BUY NOW", style="primary", icon_custom_emoji_id="5312361253610475399"),
         RBtn(text="Contact Admin", style="primary", icon_custom_emoji_id="6138899547625102613")]
    ]
    if is_admin or msg.from_user.id == OWNER_ID:
        kb.append([RBtn(text="Admin Panel", style="danger", icon_custom_emoji_id="5890864241388293875")])
        
    text = """<tg-emoji emoji-id="5440431182602842059">💎</tg-emoji> <b>BLACK STIRE KEY</b>
    
សូមស្វាគមន៍មកកាន់ប្រព័ន្ធទិញទំនិញស្វ័យប្រវត្តិ! សូមជ្រើសរើសមុខងារខាងក្រោម៖"""
    
    start_media = get_setting('start_media')
    if start_media:
        m_type, m_id = start_media.split(':', 1)
        if m_type == 'photo': await msg.answer_photo(m_id, caption=text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
        elif m_type == 'video': await msg.answer_video(m_id, caption=text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    else:
        await msg.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text == "Contact Admin")
async def contact_admin_btn(msg: Message):
    link = get_setting('contact_Admin', '@BLACK_Khmer')
    url = f"https://t.me/{link.replace('@','')}" if '@' in link else link
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Contact Admin", url=url, style="primary", icon_custom_emoji_id="6138899547625102613")]])
    await msg.answer("👇 សូមចុចប៊ូតុងខាងក្រោមដើម្បីទាក់ទង Admin:", reply_markup=kb)

# ----------------- SHOP FLOW -----------------
@dp.message(F.text == "BUY NOW")
async def shop_categories(msg: Message, state: FSMContext):
    await state.clear()
    await send_categories(msg)

async def send_categories(event):
    cats = execute_db('SELECT id, name, icon FROM categories', fetchall=True)
    if not cats:
        txt = "មិនទាន់មានទំនិញទេ!"
        if isinstance(event, CallbackQuery): return await event.message.edit_text(txt)
        return await event.answer(txt)
    
    kb = []
    for c in cats:
        kb.append([IBtn(text=c[1], callback_data=f"sel_cat_{c[0]}", style="primary", icon_custom_emoji_id=c[2])])
        
    text = "<tg-emoji emoji-id=\"5312361253610475399\">🛒</tg-emoji> <b>Close & Category៖</b>"
    if isinstance(event, CallbackQuery):
        try: await event.message.delete()
        except: pass
        await bot.send_message(event.message.chat.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await event.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("sel_cat_"))
async def shop_items(call: CallbackQuery):
    cat_id = int(call.data.split("_")[2])
    cat = execute_db('SELECT name, media_data FROM categories WHERE id=?', (cat_id,), fetch=True)
    items = execute_db('SELECT id, name, icon, price FROM items WHERE cat_id=?', (cat_id,), fetchall=True)
    
    kb = []
    for i in items:
        kb.append([IBtn(text=f"{i[1]} - ${i[3]}", callback_data=f"sel_item_{i[0]}", style="success", icon_custom_emoji_id=i[2])])
    kb.append([IBtn(text="Back ( Category )", callback_data="back_to_cat", style="danger", icon_custom_emoji_id="5352759161945867747")])
    
    text = f"<b>{cat[0]}</b>\n\nSelect the item below៖"
    
    try: await call.message.delete()
    except: pass

    if cat[1]:
        m_type, m_id = cat[1].split(':', 1)
        if m_type == 'photo': await bot.send_photo(call.message.chat.id, m_id, caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        elif m_type == 'video': await bot.send_video(call.message.chat.id, m_id, caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await bot.send_message(call.message.chat.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data == "back_to_cat")
async def back_to_cat_handler(call: CallbackQuery):
    await send_categories(call)
    await call.answer()

@dp.callback_query(F.data.startswith("sel_item_"))
async def pre_checkout_item(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split("_")[2])
    await render_checkout(call, item_id, 1, is_edit=True)

@dp.callback_query(F.data.startswith("setqty_"))
async def ask_custom_qty(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split("_")[1])
    await state.update_data(item_id=item_id, msg_id=call.message.message_id)
    await call.message.edit_text("✏️ សូមវាយបញ្ចូលចំនួនដែលអ្នកចង់ទិញ (ជាលេខ):", reply_markup=cancel_inline())
    await state.set_state(OrderFSM.custom_qty)
    await call.answer()

@dp.message(OrderFSM.custom_qty)
async def process_custom_qty(msg: Message, state: FSMContext):
    data = await state.get_data()
    try:
        qty = int(msg.text)
        if qty <= 0: raise ValueError
        await msg.delete()
        await render_checkout(msg, data['item_id'], qty, is_edit=False, old_msg_id=data['msg_id'])
        await state.clear()
    except:
        await msg.answer("❌ សូមបញ្ចូលចំនួនជាលេខត្រឹមត្រូវ!", reply_markup=cancel_inline())

async def render_checkout(event, item_id, qty, is_edit=True, old_msg_id=None):
    uid = event.from_user.id
    is_res = execute_db('SELECT is_reseller FROM users WHERE id=?', (uid,), fetch=True)[0]
    
    item = execute_db('SELECT name, price, reseller_price, cat_id FROM items WHERE id=?', (item_id,), fetch=True)
    u_price = item[2] if is_res else item[1]
    total = u_price * qty
    
    text = f"""📝 <b>ផ្ទៀងផ្ទាត់ការទិញ (CONFIRM ORDER)</b>

<tg-emoji emoji-id="5379808153011502648">📦</tg-emoji> ឈ្មោះទំនិញ: <b>{item[0]}</b>
<tg-emoji emoji-id="6264750868311056563">🔢</tg-emoji> ចំនួន (Qty): <b>{qty}</b>
<tg-emoji emoji-id="6228765605080605101">💵</tg-emoji> តម្លៃសរុប: <b>${total:.2f}</b>

❓ តើអ្នកពិតជាចង់ទិញមុខទំនិញនេះមែនដែរឬទេ?"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="កំណត់ចំនួនខ្លួនឯង", callback_data=f"setqty_{item_id}", style="primary", icon_custom_emoji_id="5258215635996908355")],
        [IBtn(text="ABA PAY", callback_data=f"abapay_{item_id}_{qty}", style="success", icon_custom_emoji_id="6316599954026535998")],
        [IBtn(text="Back", callback_data=f"sel_cat_{item[3]}", style="danger", icon_custom_emoji_id="5352759161945867747")]
    ])
    
    if is_edit and isinstance(event, CallbackQuery):
        try: await event.message.delete()
        except: pass
        await bot.send_message(event.message.chat.id, text, reply_markup=kb)
        await event.answer()
    else:
        if old_msg_id:
            try: await bot.delete_message(event.chat.id, old_msg_id)
            except: pass
        await event.answer(text, reply_markup=kb)

# ----------------- ABA CHECKOUT FLOW -----------------
@dp.callback_query(F.data.startswith("abapay_"))
async def handle_aba_pay(call: CallbackQuery):
    parts = call.data.split("_")
    item_id, qty = int(parts[1]), int(parts[2])
    uid = call.from_user.id
    
    stock_qty = execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (item_id,), fetch=True)[0]
    if qty > stock_qty:
        return await call.answer(f"❌ ស្តុកមិនគ្រប់គ្រាន់ទេ! (មាន {stock_qty})", show_alert=True)
        
    is_res = execute_db('SELECT is_reseller FROM users WHERE id=?', (uid,), fetch=True)[0]
    item = execute_db('SELECT name, price, reseller_price FROM items WHERE id=?', (item_id,), fetch=True)
    total = (item[2] if is_res else item[1]) * qty
    
    loading_msg = await call.message.edit_text("<tg-emoji emoji-id=\"6316599954026535998\">🏦</tg-emoji> <b>QR កំពង់តែទាញយកពីរAPIសូមរង់ចាំ…..</b>")
    
    ref_id = f"znt_{uid}_{int(time.time())}"
    res = await aba_generate_qr_async(total, ref_id)
    
    if not res:
        return await loading_msg.edit_text("❌ មានបញ្ហាក្នុងការទាញយក QR ពី API! សូមសាកល្បងម្ដងទៀត។")
        
    payment_id = res.get("payment_id") or (res.get("data") or {}).get("payment_id")
    qr_base64 = res.get("qr_image") or (res.get("data") or {}).get("qr_image")
    pay_url = res.get("pay_url") or (res.get("data") or {}).get("pay_url")
    
    cap = f"""<tg-emoji emoji-id="6314519407443845610">🏦</tg-emoji> <b>ABA PAY WAY</b> 
- <tg-emoji emoji-id="6228765605080605101">💵</tg-emoji> ចំនួនត្រូវផេរ : <b>${total:.2f}</b>
- <tg-emoji emoji-id="5379808153011502648">📦</tg-emoji> ទំនិញ : <b>{item[0]}</b> x{qty}
- <tg-emoji emoji-id="6102645363607349418">🧾</tg-emoji> Ref : <code>{payment_id}</code>
- <tg-emoji emoji-id="6316599954026535998">🏦</tg-emoji> សូមអ្នកយកQRទៅផេរលុយក្នុងធានាគារណាមួយទៅអាចផេរបានទាំងអស់ ។ 
- <tg-emoji emoji-id="6102563003314479651">⚡</tg-emoji> ពេលដែលបងផេររួចនឹងលូតទំនិញអូតូស្វ័យប្រវត្តិមង ។"""

    kb_arr = []
    if pay_url: kb_arr.append([IBtn(text="បើកទំព័រទូរទាត់", url=pay_url, style="success", icon_custom_emoji_id="5258073068852485953")])
    kb_arr.append([IBtn(text="បោះបង់ QR / Cancell", callback_data="cancel_action", style="danger", icon_custom_emoji_id="6102914615107133393")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_arr)

    await loading_msg.delete()
    
    if qr_base64:
        try:
            img_data = base64.b64decode(qr_base64.split(",")[1] if "," in qr_base64 else qr_base64)
            sent_msg = await bot.send_photo(call.message.chat.id, photo=BufferedInputFile(img_data, filename="qr.png"), caption=cap, reply_markup=kb)
        except:
            sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb)
    else:
        sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb)
        
    run_bg_task(poll_payment(call, uid, call.message.chat.id, payment_id, item_id, qty, sent_msg.message_id, total, item[0]))
    await call.answer()

async def poll_payment(call, uid, chat_id, payment_id, item_id, qty, msg_id, total_paid, item_name):
    timeout = time.time() + 180
    while time.time() < timeout:
        paid = await aba_check_paid_async(payment_id)
        if paid:
            await deliver_item(call, uid, chat_id, item_id, qty, msg_id, total_paid, item_name)
            return
        await asyncio.sleep(5)
    try: await bot.delete_message(chat_id, msg_id)
    except: pass
    await bot.send_message(chat_id, "⌛ QR ទូទាត់របស់អ្នកបានផុតកំណត់ហើយ។")

async def deliver_item(call, uid, chat_id, item_id, qty, msg_id, total_paid, item_name):
    stocks = execute_db('SELECT id, key_data, type FROM stock WHERE item_id=? AND is_sold=0 LIMIT ?', (item_id, qty), fetchall=True)
    if len(stocks) < qty:
        return await bot.send_message(chat_id, "❌ ស្តុកត្រូវបានទិញអស់លឿនពេក! សូមទាក់ទង Admin។")
        
    key_text = ""
    for s in stocks:
        execute_db('UPDATE stock SET is_sold=1 WHERE id=?', (s[0],))
        if s[2] == 'text':
            key_text += f"- <tg-emoji emoji-id=\"5257969839313526622\">🔑</tg-emoji> <code>{s[1]}</code>\n"
        else:
            m_type, m_id = s[1].split(':', 1)
            try:
                if m_type == 'photo': await bot.send_photo(chat_id, m_id, caption="នេះគឺជាឯកសាររបស់អ្នក!")
                elif m_type == 'video': await bot.send_video(chat_id, m_id, caption="នេះគឺជាឯកសាររបស់អ្នក!")
                elif m_type == 'document': await bot.send_document(chat_id, m_id, caption="នេះគឺជាឯកសាររបស់អ្នក!")
            except: pass
        
    msg = f"""<tg-emoji emoji-id="5258389041006518073">✅</tg-emoji> <b>ទំនិញបានកម្មង់ជោគជ័យហើយ!</b> 

<tg-emoji emoji-id="6102645363607349418">📦</tg-emoji> ទំនិញ/Key/File : 
{key_text}
<tg-emoji emoji-id="5258179403652801593">🙏</tg-emoji> <b>សូមអរគុណសម្រាប់ការគាំទ្រ!</b>"""

    try: await bot.delete_message(chat_id, msg_id)
    except: pass
    await bot.send_message(chat_id, msg)
    
    # Check post-purchase media
    post_media = execute_db('SELECT post_media FROM items WHERE id=?', (item_id,), fetch=True)[0]
    if post_media:
        m_type, content = post_media.split(':', 1)
        try:
            if m_type == 'photo': await bot.send_photo(chat_id, content)
            elif m_type == 'video': await bot.send_video(chat_id, content)
            elif m_type == 'document': await bot.send_document(chat_id, content)
            elif m_type == 'audio': await bot.send_audio(chat_id, content)
            elif m_type == 'voice': await bot.send_voice(chat_id, content)
            elif m_type == 'text': await bot.send_message(chat_id, content)
        except: pass

    # Alert to channel
    user = call.from_user
    u_name = user.first_name or "Unknown"
    u_user = f"@{user.username}" if user.username else "គ្មាន"
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    alert_txt = f"មានការបព្ជាទិញថ្មីៗនេះ!\n- ម៉ោង : {date_str}\n- ទំនិញ : {item_name}\n- តម្លៃ : ${total_paid:.2f}\n- ទិញចំនួន : {qty}\n- ID : <code>{uid}</code>\n- Name : {u_name}\n- Username : {u_user}\nសូមអរគុណបងសម្រាប់ការគាំទ្របតខាងប្អូន !"
    await alert_to_channel(alert_txt)

    # Low Stock Check
    rem_stock = execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (item_id,), fetch=True)[0]
    if rem_stock <= 3:
        alert = f"""<tg-emoji emoji-id="6143084439204275121">🚨</tg-emoji> សេចក្ដីជូនដំណឹង—ស្តុកជិតអស់ហើយ !
- ទំនិញ : {item_name}
- <tg-emoji emoji-id="6138675041094606406">📦</tg-emoji> ស្តុកនៅសល់ : <b>{rem_stock}</b> ប៉ុណ្ណោះ
<tg-emoji emoji-id="6138702889662554181">⏳</tg-emoji> រួសរាល់ឡើងដើម្បីទិញទាន់នៅមានស្តុកខ្លះ"""
        if rem_stock == 0: alert = alert.replace("ស្តុកជិតអស់ហើយ", "ស្តុកត្រូវបានលក់អស់ហើយ")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="BUY NOW", callback_data="buy_now_direct", style="primary", icon_custom_emoji_id="5312361253610475399")]])
        users = execute_db('SELECT id FROM users', fetchall=True)
        for u in users:
            try: await bot.send_message(u[0], alert, reply_markup=kb)
            except: pass

@dp.callback_query(F.data == "buy_now_direct")
async def buy_now_direct_btn(call: CallbackQuery):
    await send_categories(call)
    await call.answer()

# ====================================================================================================
# [ ផ្នែក ADMIN PANEL ]
# ====================================================================================================

@dp.message(F.text == "Abmin Panel")
async def open_admin(msg: Message):
    is_admin = execute_db('SELECT is_admin FROM users WHERE id=?', (msg.from_user.id,), fetch=True)[0]
    if not is_admin and msg.from_user.id != OWNER_ID: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="គ្រុបគ្រងផលលិតផល", callback_data="adm_manage_products", style="primary", icon_custom_emoji_id="5312361253610475399")],
        [IBtn(text="មើលស្តុក ( Views Stock )", callback_data="adm_view_stock", style="primary", icon_custom_emoji_id="6138721800403559725")],
        [IBtn(text="គ្រប់គ្រងស្តុក ( Abb/Delete )", callback_data="adm_manage_stock", style="success", icon_custom_emoji_id="6138856219995021560")],
        [IBtn(text="Broadcast", callback_data="adm_broadcast", style="primary", icon_custom_emoji_id="5260268501515377807")],
        [IBtn(text="គ្រប់គ្រង់ ( Reseller )", callback_data="adm_reseller", style="primary", icon_custom_emoji_id="6136265963873511020")],
        [IBtn(text="កំណត់ Group/Chanel វិក្កយប័ត្រ", callback_data="adm_channel", style="primary", icon_custom_emoji_id="5445221832074483553")],
        [IBtn(text="ដាក់វីដេអូ/រូបភាព /start", callback_data="adm_start_media", style="primary", icon_custom_emoji_id="6138556641731159070")],
        [IBtn(text="កែបូតុង Contact Admin", callback_data="adm_edit_contact", style="primary", icon_custom_emoji_id="6151989590036065945")]
    ])
    await msg.answer("<tg-emoji emoji-id=\"5890864241388293875\">⚙️</tg-emoji> <b>ផ្ទាំងគ្របគ្រង់អេតមីនឆ្លាតវ័យ</b>\nសូមជ្រើសរើសមុខងារខាងក្រោម៖", reply_markup=kb)

# --- VIEW STOCK ---
@dp.callback_query(F.data == "adm_view_stock")
async def view_stock_cmd(call: CallbackQuery):
    items = execute_db('SELECT id, name FROM items', fetchall=True)
    if not items: return await call.answer("មិនមានទំនិញទេ!", show_alert=True)
    text = "📊 <b>របាយការណ៍ស្តុកទំនិញ:</b>\n\n"
    for i in items:
        count = execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (i[0],), fetch=True)[0]
        text += f"- {i[1]}: <b>{count}</b>\n"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Back", callback_data="back_admin", style="danger")]]))
    await call.answer()

@dp.callback_query(F.data == "back_admin")
async def back_to_admin(call: CallbackQuery):
    await call.message.delete()
    await open_admin(call.message)
    await call.answer()

# --- MANAGE PRODUCTS ---
@dp.callback_query(F.data == "adm_manage_products")
async def adm_products(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="បង្កើត ផលលិតផល ថ្មី", callback_data="adm_add_cat", style="success")],
        [IBtn(text="លុប ផលលិតផល", callback_data="adm_del_cat", style="danger", icon_custom_emoji_id="5258130763148172425")],
        [IBtn(text="ដាក់វីដេអូ ឬ រូបភាព (Category)", callback_data="adm_add_cat_media", style="primary")],
        [IBtn(text="លុបវីដេអូ ឬ រូបភាព", callback_data="adm_del_cat_media", style="danger")],
        [IBtn(text="បន្ថែម ទំនិញ ថ្មី", callback_data="adm_add_item", style="success")],
        [IBtn(text="លុបទំនិញ", callback_data="adm_del_item", style="danger", icon_custom_emoji_id="5258130763148172425")],
        [IBtn(text="ដាក់ File/Link ពេលទិញរួច", callback_data="adm_add_post_media", style="primary")],
        [IBtn(text="លុប File/Link ពេលទិញរួច", callback_data="adm_del_post_media", style="danger")],
        [IBtn(text="Back", callback_data="back_admin", style="danger")]
    ])
    await call.message.edit_text("🛒 <b>គ្រប់គ្រងផលិតផល និងទំនិញ</b>", reply_markup=kb)
    await call.answer()

# --- VALIDATE EMOJI FUNCTION ---
def extract_emoji(msg: Message):
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "custom_emoji":
                return ent.custom_emoji_id
    if msg.text and msg.text.strip().isdigit():
        return msg.text.strip()
    return None

# --- ADD CATEGORY ---
@dp.callback_query(F.data == "adm_add_cat")
async def adm_add_cat_1(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 សូមបញ្ចូល ឈ្មោះផលិតផល (Category):", reply_markup=cancel_inline())
    await state.set_state(AdminAddCat.name)
    await call.answer()

@dp.message(AdminAddCat.name)
async def adm_add_cat_2(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await msg.answer("✨ សូមបញ្ចូល Emoji Premium ឬ ID សម្រាប់ផលិតផលនេះ:", reply_markup=cancel_inline())
    await state.set_state(AdminAddCat.icon)

@dp.message(AdminAddCat.icon)
async def adm_add_cat_3(msg: Message, state: FSMContext):
    icon_id = extract_emoji(msg)
    if not icon_id: return await msg.answer("❌ ខុសហើយ! សូមផ្ញើជា Premium Emoji ពិតៗ ឬជាលេខ ID របស់វា:", reply_markup=cancel_inline())
    data = await state.get_data()
    execute_db('INSERT INTO categories (name, icon) VALUES (?, ?)', (data['name'], icon_id))
    await msg.answer("✅ បង្កើតផលិតផលជោគជ័យ!")
    await state.clear()

# --- DEL CATEGORY ---
@dp.callback_query(F.data == "adm_del_cat")
async def adm_del_cat(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    kb = [[IBtn(text=f"🗑 {c[1]}", callback_data=f"docdelcat_{c[0]}", style="danger")] for c in cats]
    await call.message.edit_text("ជ្រើសរើសផលិតផលដើម្បីលុប:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("docdelcat_"))
async def doc_del_cat(call: CallbackQuery):
    execute_db('DELETE FROM categories WHERE id=?', (int(call.data.split("_")[1]),))
    await call.answer("✅ លុបរួចរាល់!", show_alert=True)
    await call.message.delete()

# --- ADD ITEM ---
@dp.callback_query(F.data == "adm_add_item")
async def adm_add_item_1(call: CallbackQuery, state: FSMContext):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    if not cats: return await call.answer("ត្រូវបង្កើតផលិតផល (Category) ជាមុនសិន!", show_alert=True)
    kb = [[IBtn(text=c[1], callback_data=f"setcat_{c[0]}", style="primary")] for c in cats]
    await call.message.edit_text("📂 ជ្រើសរើស ផលិតផល ដែលចង់បន្ថែមទំនិញចូល:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("setcat_"))
async def adm_add_item_2(call: CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=int(call.data.split("_")[1]))
    await call.message.edit_text("📝 សូមបញ្ចូល ឈ្មោះទំនិញ:", reply_markup=cancel_inline())
    await state.set_state(AdminAddItem.name)
    await call.answer()

@dp.message(AdminAddItem.name)
async def adm_add_item_3(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await msg.answer("💵 សូមបញ្ចូល តម្លៃទូទៅ (ឧ. 5.5):", reply_markup=cancel_inline())
    await state.set_state(AdminAddItem.price)

@dp.message(AdminAddItem.price)
async def adm_add_item_4(msg: Message, state: FSMContext):
    try:
        await state.update_data(price=float(msg.text))
        await msg.answer("🏷 សូមបញ្ចូល តម្លៃ Reseller (ឧ. 4.0):", reply_markup=cancel_inline())
        await state.set_state(AdminAddItem.reseller_price)
    except: await msg.answer("❌ លេខមិនត្រឹមត្រូវ!")

@dp.message(AdminAddItem.reseller_price)
async def adm_add_item_5(msg: Message, state: FSMContext):
    try:
        await state.update_data(reseller_price=float(msg.text))
        await msg.answer("✨ សូមបញ្ចូល Emoji Premium ឬ ID សម្រាប់ទំនិញនេះ:", reply_markup=cancel_inline())
        await state.set_state(AdminAddItem.icon)
    except: await msg.answer("❌ លេខមិនត្រឹមត្រូវ!")

@dp.message(AdminAddItem.icon)
async def adm_add_item_6(msg: Message, state: FSMContext):
    icon_id = extract_emoji(msg)
    if not icon_id: return await msg.answer("❌ ខុសហើយ! សូមផ្ញើជា Premium Emoji ពិតៗ ឬជាលេខ ID របស់វា:", reply_markup=cancel_inline())
    d = await state.get_data()
    execute_db('INSERT INTO items (cat_id, name, price, reseller_price, icon) VALUES (?,?,?,?,?)', 
               (d['cat_id'], d['name'], d['price'], d['reseller_price'], icon_id))
    await msg.answer("✅ បន្ថែមទំនិញជោគជ័យ!")
    await state.clear()

# --- DEL ITEM ---
@dp.callback_query(F.data == "adm_del_item")
async def adm_del_item(call: CallbackQuery):
    items = execute_db('SELECT id, name FROM items', fetchall=True)
    kb = [[IBtn(text=f"🗑 {i[1]}", callback_data=f"docdelitem_{i[0]}", style="danger")] for i in items]
    await call.message.edit_text("ជ្រើសរើសទំនិញដើម្បីលុប:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("docdelitem_"))
async def doc_del_item(call: CallbackQuery):
    execute_db('DELETE FROM items WHERE id=?', (int(call.data.split("_")[1]),))
    await call.answer("✅ លុបរួចរាល់!", show_alert=True)
    await call.message.delete()

# --- CATEGORY MEDIA ---
@dp.callback_query(F.data == "adm_add_cat_media")
async def set_cat_media(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    kb = [[IBtn(text=c[1], callback_data=f"setcatmd_{c[0]}", style="primary")] for c in cats]
    await call.message.edit_text("ជ្រើសរើស Category ដើម្បីដាក់វីដេអូ/រូបភាព:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()
@dp.callback_query(F.data.startswith("setcatmd_"))
async def set_cat_media2(call: CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=int(call.data.split("_")[1]))
    await call.message.edit_text("ផ្ញើ វីដេអូ ឬ រូបភាពមកទីនេះ:", reply_markup=cancel_inline())
    await state.set_state(AdminCatMedia.media)
    await call.answer()
@dp.message(AdminCatMedia.media)
async def set_cat_media3(msg: Message, state: FSMContext):
    cat_id = (await state.get_data())['cat_id']
    if msg.photo: val = f"photo:{msg.photo[-1].file_id}"
    elif msg.video: val = f"video:{msg.video.file_id}"
    else: return await msg.answer("❌ សូមផ្ញើតែរូបភាព ឬ វីដេអូប៉ុណ្ណោះ!", reply_markup=cancel_inline())
    execute_db('UPDATE categories SET media_data=? WHERE id=?', (val, cat_id))
    await msg.answer("✅ ដាក់ជោគជ័យ!")
    await state.clear()
@dp.callback_query(F.data == "adm_del_cat_media")
async def del_cat_media(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    kb = [[IBtn(text=c[1], callback_data=f"delcatmd_{c[0]}", style="danger")] for c in cats]
    await call.message.edit_text("ជ្រើសរើស Category ដើម្បីលុបវីដេអូ/រូបភាព:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()
@dp.callback_query(F.data.startswith("delcatmd_"))
async def del_cat_media2(call: CallbackQuery):
    execute_db('UPDATE categories SET media_data=NULL WHERE id=?', (int(call.data.split("_")[1]),))
    await call.answer("✅ លុបរួចរាល់!", show_alert=True)
    await call.message.delete()

# --- POST PURCHASE MEDIA ---
@dp.callback_query(F.data == "adm_add_post_media")
async def set_post_media(call: CallbackQuery):
    items = execute_db('SELECT id, name FROM items', fetchall=True)
    kb = [[IBtn(text=i[1], callback_data=f"setpostmd_{i[0]}", style="primary")] for i in items]
    await call.message.edit_text("ជ្រើសរើសទំនិញ ដើម្បីដាក់ Media ក្រោយពេលទិញរួច:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()
@dp.callback_query(F.data.startswith("setpostmd_"))
async def set_post_media2(call: CallbackQuery, state: FSMContext):
    await state.update_data(item_id=int(call.data.split("_")[1]))
    await call.message.edit_text("ផ្ញើ វីដេអូ/រូបភាព/File/Text/សំឡេង មកទីនេះ:", reply_markup=cancel_inline())
    await state.set_state(AdminPostMedia.media)
    await call.answer()
@dp.message(AdminPostMedia.media)
async def set_post_media3(msg: Message, state: FSMContext):
    item_id = (await state.get_data())['item_id']
    if msg.photo: val = f"photo:{msg.photo[-1].file_id}"
    elif msg.video: val = f"video:{msg.video.file_id}"
    elif msg.document: val = f"document:{msg.document.file_id}"
    elif msg.audio: val = f"audio:{msg.audio.file_id}"
    elif msg.voice: val = f"voice:{msg.voice.file_id}"
    else: val = f"text:{msg.html_text}"
    execute_db('UPDATE items SET post_media=? WHERE id=?', (val, item_id))
    await msg.answer("✅ ដាក់ជោគជ័យ!")
    await state.clear()
@dp.callback_query(F.data == "adm_del_post_media")
async def del_post_media(call: CallbackQuery):
    items = execute_db('SELECT id, name FROM items', fetchall=True)
    kb = [[IBtn(text=i[1], callback_data=f"delpostmd_{i[0]}", style="danger")] for i in items]
    await call.message.edit_text("ជ្រើសរើសទំនិញ ដើម្បីលុប Media:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()
@dp.callback_query(F.data.startswith("delpostmd_"))
async def del_post_media2(call: CallbackQuery):
    execute_db('UPDATE items SET post_media=NULL WHERE id=?', (int(call.data.split("_")[1]),))
    await call.answer("✅ លុបរួចរាល់!", show_alert=True)
    await call.message.delete()

# --- MANAGE STOCK ---
@dp.callback_query(F.data == "adm_manage_stock")
async def adm_manage_stock(call: CallbackQuery):
    items = execute_db('SELECT id, name FROM items', fetchall=True)
    if not items: return await call.answer("មិនមានទំនិញទេ!", show_alert=True)
    kb = [[IBtn(text=i[1], callback_data=f"stkopt_{i[0]}", style="primary")] for i in items]
    await call.message.edit_text("👉 សូមរើសបូតុងទំនិញដែលបងចង់គ្រប់គ្រងខាងក្រោម:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("stkopt_"))
async def stk_options(call: CallbackQuery):
    item_id = int(call.data.split("_")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Abb Stock", callback_data=f"addstk_{item_id}", style="success", icon_custom_emoji_id="5397916757333654639")],
        [IBtn(text="Clear Stock", callback_data=f"clrstk_{item_id}", style="danger", icon_custom_emoji_id="5258130763148172425")],
        [IBtn(text="Back", callback_data="adm_manage_stock", style="primary")]
    ])
    await call.message.edit_text("ជ្រើសរើសមុខងារ:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("clrstk_"))
async def clear_stock(call: CallbackQuery):
    item_id = int(call.data.split("_")[1])
    execute_db('DELETE FROM stock WHERE item_id=? AND is_sold=0', (item_id,))
    await call.answer("✅ បានលុបស្តុកចោលទាំងអស់ជោគជ័យ!", show_alert=True)
    await call.message.delete()

@dp.callback_query(F.data.startswith("addstk_"))
async def add_stock_start(call: CallbackQuery, state: FSMContext):
    await state.update_data(item_id=int(call.data.split("_")[1]))
    await call.message.edit_text("📥 សូមផ្ញើ ស្តុកមកទីនេះ (ជា files / វីដេអូ / រូបភាព / លីង / អត្ថបទ):\n*បើអត្ថបទ វាយមួយជួរចុះបន្ទាត់មួយ វាចូល ២ keys*", reply_markup=cancel_inline())
    await state.set_state(AdminAddStock.keys)
    await call.answer()

@dp.message(AdminAddStock.keys)
async def add_stock_save(msg: Message, state: FSMContext):
    item_id = (await state.get_data())['item_id']
    added = 0
    if msg.photo: 
        execute_db('INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)', (item_id, f"photo:{msg.photo[-1].file_id}", 'file'))
        added = 1
    elif msg.video: 
        execute_db('INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)', (item_id, f"video:{msg.video.file_id}", 'file'))
        added = 1
    elif msg.document:
        execute_db('INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)', (item_id, f"document:{msg.document.file_id}", 'file'))
        added = 1
    elif msg.text:
        lines = [L.strip() for L in msg.text.split('\n') if L.strip()]
        for k in lines: execute_db('INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)', (item_id, k, 'text'))
        added = len(lines)
    else: return await msg.answer("❌ មិនគាំទ្រទម្រង់នេះទេ!", reply_markup=cancel_inline())
    
    await msg.answer(f"✅ បានបញ្ចូលចំនួន {added} ចូលស្តុកជោគជ័យ!")
    await state.clear()
    
    # Broadcast New Stock
    item = execute_db('SELECT name, price FROM items WHERE id=?', (item_id,), fetch=True)
    alert = f"""<tg-emoji emoji-id="6138721800403559725">🔔</tg-emoji> <b>ស្តុកថ្មីបានបន្ថែម !</b> 
———————————————————————-
- <tg-emoji emoji-id="6228765605080605101">💵</tg-emoji> តម្លៃ : <b>${item[1]:.2f}</b>
- <tg-emoji emoji-id="5379808153011502648">📦</tg-emoji> ទំនិញ : <b>{item[0]}</b>
- <tg-emoji emoji-id="5397916757333654639">➕</tg-emoji> បន្ថែមចំនួន : <b>{added}</b>
——————————————————————-— 
<tg-emoji emoji-id="6138589833238422233">✅</tg-emoji> រួចសម្រាប់ការទិញនៅ?
<tg-emoji emoji-id="6138677811348513089">👉</tg-emoji> សូមបងចុច <b>BUY NOW</b> ដើម្បីទិញទំនិញ"""
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="BUY NOW", callback_data="buy_now_direct", style="primary", icon_custom_emoji_id="5312361253610475399")]])
    users = execute_db('SELECT id FROM users', fetchall=True)
    for u in users:
        try: await bot.send_message(u[0], alert, reply_markup=kb)
        except: pass

# --- BROADCAST ---
@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("✍️តើបងចង់ធ្ញើសារទៅ User ដែលនៅក្នុងបតបងមិចខ្លះបងអាចធ្ញើបាន\n( ឧទារហណ៍ . ជាលីង / ជាវីដេអូ / ជាfiles / ជារូបភាព / និយាយសំឡេង / ជាអត្ថបទ ):", reply_markup=cancel_inline())
    await state.set_state(AdminBroadcast.msg)
    await call.answer()

@dp.message(AdminBroadcast.msg)
async def execute_broadcast(msg: Message, state: FSMContext):
    users = execute_db('SELECT id FROM users', fetchall=True)
    success, fail = 0, 0
    await msg.answer("កំពុងផ្ញើ...")
    
    prefix = "<tg-emoji emoji-id=\"5798687882369569347\">🔔</tg-emoji> <b>សារពីរ Abmin:</b>\n\n"
    
    for u in users:
        try:
            if msg.text: await bot.send_message(u[0], prefix + msg.html_text)
            elif msg.photo: await bot.send_photo(u[0], msg.photo[-1].file_id, caption=prefix + (msg.html_text or ""))
            elif msg.video: await bot.send_video(u[0], msg.video.file_id, caption=prefix + (msg.html_text or ""))
            elif msg.document: await bot.send_document(u[0], msg.document.file_id, caption=prefix + (msg.html_text or ""))
            elif msg.audio: await bot.send_audio(u[0], msg.audio.file_id, caption=prefix + (msg.html_text or ""))
            elif msg.voice: await bot.send_voice(u[0], msg.voice.file_id, caption=prefix + (msg.html_text or ""))
            success += 1
        except: fail += 1
        await asyncio.sleep(0.05)
        
    res_text = f"""<tg-emoji emoji-id="6100288912620528566">📊</tg-emoji> បានធ្ញើចំនួន <b>{success+fail}</b> នាក់ 
- <tg-emoji emoji-id="6102563003314479651">✅</tg-emoji> ជោគជ័យចំនួន <b>{success}</b> នាក់ 
- <tg-emoji emoji-id="6102914615107133393">❌</tg-emoji> បរាជ័យ <b>{fail}</b> នាក់"""
    await msg.answer(res_text)
    await state.clear()

# --- RESELLER ---
@dp.callback_query(F.data == "adm_reseller")
async def adm_reseller(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Abb Reseller", callback_data="add_reseller", style="success"), IBtn(text="Del Reseller", callback_data="del_reseller", style="danger")],
        [IBtn(text="តម្លៃទូទៅ / តម្លៃ Reseller", callback_data="ignore", style="primary")],
        [IBtn(text="Admin ID", callback_data="ignore", style="primary")],
        [IBtn(text="Back", callback_data="back_admin", style="danger")]
    ])
    await call.message.edit_text("👥 <b>គ្រប់គ្រង Reseller</b>", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "add_reseller")
async def add_reseller_st(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("បញ្ចូល ID របស់ User ដែលចង់ដាក់ជា Reseller:", reply_markup=cancel_inline())
    await state.set_state(AdminReseller.add_id)
    await call.answer()
@dp.message(AdminReseller.add_id)
async def add_reseller_save(msg: Message, state: FSMContext):
    try:
        execute_db('UPDATE users SET is_reseller=1 WHERE id=?', (int(msg.text),))
        await msg.answer("✅ ជោគជ័យ!")
    except: pass
    await state.clear()

@dp.callback_query(F.data == "del_reseller")
async def del_reseller_st(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("បញ្ចូល ID របស់ User ដែលចង់ដកពី Reseller:", reply_markup=cancel_inline())
    await state.set_state(AdminReseller.del_id)
    await call.answer()
@dp.message(AdminReseller.del_id)
async def del_reseller_save(msg: Message, state: FSMContext):
    try:
        execute_db('UPDATE users SET is_reseller=0 WHERE id=?', (int(msg.text),))
        await msg.answer("✅ ជោគជ័យ!")
    except: pass
    await state.clear()

# --- SET CHANNEL ---
@dp.callback_query(F.data == "adm_channel")
async def adm_channel(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🔔 សូមវាយបញ្ចូល Channel/Group ID របស់អ្នក:", reply_markup=cancel_inline())
    await state.set_state(AdminChannel.channel_id)
    await call.answer()
@dp.message(AdminChannel.channel_id)
async def save_channel(msg: Message, state: FSMContext):
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('channel_id', msg.text))
    await msg.answer("✅ កំណត់ជោគជ័យ!")
    await state.clear()

# --- START MEDIA ---
@dp.callback_query(F.data == "adm_start_media")
async def adm_start_media(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("ផ្ញើ វីដេអូ ឬ រូបភាព សម្រាប់ /start (ឬវាយពាក្យ 'del' ដើម្បីលុប):", reply_markup=cancel_inline())
    await state.set_state(AdminStartMedia.media)
    await call.answer()
@dp.message(AdminStartMedia.media)
async def save_start_media(msg: Message, state: FSMContext):
    if msg.text and msg.text.lower() == 'del':
        execute_db('DELETE FROM settings WHERE key=?', ('start_media',))
    elif msg.photo: 
        execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('start_media', f"photo:{msg.photo[-1].file_id}"))
    elif msg.video:
        execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('start_media', f"video:{msg.video.file_id}"))
    await msg.answer("✅ កំណត់ជោគជ័យ!")
    await state.clear()

# --- EDIT CONTACT ADMIN ---
@dp.callback_query(F.data == "adm_edit_contact")
async def adm_edit_contact(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("បញ្ចូល Username ឬ Link ថ្មី (ឧ. @BLACK_Khmer):", reply_ markup=cancel_inline())
    await state.set_state(AdminContact.link)
    await call.answer()
@dp.message(AdminContact.link)
async def save_contact(msg: Message, state: FSMContext):
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('contact_admin', msg.text.strip()))
    await msg.answer("✅ កំណត់ជោគជ័យ!")
    await state.clear()

# ====================================================================================================
# [ MAIN LOOP ]
# ====================================================================================================

async def main():
    logger.info("🚀 BLACK STORE KEY BOT IS RUNNING...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
