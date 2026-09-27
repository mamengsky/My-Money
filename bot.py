import os
import datetime
import logging
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from supabase import create_client, Client

# Konfigurasi Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Konfigurasi Supabase
SUPABASE_URL = "https://nfquoswrwtgegsprpuae.supabase.co"
SUPABASE_KEY = "sb_publishable_7zCLrX-DciJNflkgPUj6jQ_xb9G_mtf"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# State untuk ConversationHandler
NOMINAL, ACCOUNT, KETERANGAN = range(3)

# Opsi Kategori / Keterangan dari Gambar & Pemasukan
EXPENSE_OPTIONS = [
    "Biaya Listrik",
    "Biaya Internet",
    "Bensin",
    "Service Motor",
    "Makan dan Minum",
    "Rokok",
    "Pods",
    "Jajan",
    "Kesehatan",
    "Jatah Ayang"
]

INCOME_OPTIONS = [
    "Gaji / Income Utama",
    "Bonus / Sampingan",
    "Lainnya"
]

def get_main_menu_keyboard():
    """Membuat Menu Tombol Utama yang selalu muncul di bawah obrolan."""
    keyboard = [
        [KeyboardButton("🟢 Masuk"), KeyboardButton("🔴 Keluar")],
        [KeyboardButton("📊 Saldo")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menyapa pengguna dan menampilkan menu utama berupa tombol."""
    welcome_message = (
        "Halo! Selamat datang di Bot MY WALLET 💰\n\n"
        "Semua data yang kamu catat di sini akan langsung tersinkronisasi dengan website.\n\n"
        "Silakan pilih menu di bawah ini untuk memulai:"
    )
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_main_menu_keyboard(),
        parse_mode='Markdown'
    )

async def handle_unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Merespons jika pengguna mengirim pesan apapun tanpa menggunakan command."""
    text = update.message.text
    
    if "Saldo" in text:
        await saldo(update, context)
    else:
        await update.message.reply_text(
            "Silakan pilih tindakan dari tombol di bawah ini ⬇️",
            reply_markup=get_main_menu_keyboard()
        )

async def mulai_transaksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 1: Memulai alur dengan menentukan tipe (masuk/keluar)."""
    text = update.message.text
    
    if "Masuk" in text or "masuk" in text:
        command = "masuk"
    else:
        command = "keluar"
        
    context.user_data['type'] = command
    
    tipe_text = "pemasukan 🟢" if command == "masuk" else "pengeluaran 🔴"
    await update.message.reply_text(
        f"Silakan ketikkan nominal **{tipe_text}** (contoh: `50000`):",
        parse_mode='Markdown'
    )
    return NOMINAL

async def terima_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 2: Menerima nominal dan menampilkan pilihan Akun (Bank / Cash)."""
    text = update.message.text.strip().replace(".", "").replace(",", "")
    
    try:
        amount = float(text)
        if amount <= 0:
            await update.message.reply_text("Nominal harus lebih dari 0. Silakan masukkan angka lagi:")
            return NOMINAL
            
        context.user_data['amount'] = amount
        
        # Tombol Pilihan Akun
        keyboard = [
            [
                InlineKeyboardButton("🏦 Bank", callback_data="acc_bank"),
                InlineKeyboardButton("💵 Cash", callback_data="acc_cash")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        formatted_amount = f"Rp {amount:,.0f}".replace(",", ".")
        await update.message.reply_text(
            f"Nominal dicatat: **{formatted_amount}**\n\n"
            f"Pilih **sumber / tujuan akun** transaksi:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ACCOUNT

    except ValueError:
        await update.message.reply_text("Nominal harus berupa angka saja! Silakan ketik ulang nominalnya:")
        return NOMINAL

async def terima_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 3: Menerima akun (Bank/Cash) lalu menampilkan pilihan Keterangan."""
    query = update.callback_query
    await query.answer()
    
    account_selected = "bank" if query.data == "acc_bank" else "cash"
    context.user_data['account'] = account_selected
    
    tipe = context.user_data.get('type')
    
    # Buat tombol pilihan keterangan
    options = INCOME_OPTIONS if tipe == "masuk" else EXPENSE_OPTIONS
    keyboard = []
    
    for item in options:
        keyboard.append([InlineKeyboardButton(item, callback_data=item)])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    account_label = "🏦 Bank" if account_selected == "bank" else "💵 Cash"
    await query.edit_message_text(
        f"Akun dipilih: **{account_label}**\n\n"
        f"Pilih **keterangan/kategori** {tipe} di bawah ini:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return KETERANGAN

async def terima_keterangan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 4: Menerima keterangan dan menyimpan seluruh data ke Supabase."""
    query = update.callback_query
    await query.answer()
    
    note = query.data
    tipe = context.user_data.get('type')
    amount = context.user_data.get('amount')
    account = context.user_data.get('account')
    
    db_type = 'income' if tipe == 'masuk' else 'expense'
    current_date = datetime.date.today().isoformat()

    data_to_insert = {
        "id": f"bot_{uuid.uuid4().hex[:10]}",
        "type": db_type,
        "amount": amount,
        "category": note if db_type == 'expense' else "Pemasukan",
        "account": account,
        "note": note,
        "date": current_date
    }

    try:
        response = supabase.table("transactions").insert(data_to_insert).execute()

        if response.data:
            emoji = "🟢" if db_type == 'income' else "🔴"
            formatted_amount = f"Rp {amount:,.0f}".replace(",", ".")
            account_label = "🏦 Bank" if account == "bank" else "💵 Cash"
            
            await query.edit_message_text(
                f"✅ **Berhasil dicatat!** {emoji}\n\n"
                f"**Jenis:** {db_type.upper()}\n"
                f"**Jumlah:** {formatted_amount}\n"
                f"**Akun:** {account_label}\n"
                f"**Keterangan:** {note}\n"
                f"**Tanggal:** {current_date}",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Gagal menyimpan ke database. Silakan coba lagi.")
    except Exception as e:
        logger.error(f"Error Supabase: {e}")
        await query.edit_message_text(f"Terjadi kesalahan sistem: {str(e)}")

    return ConversationHandler.END

async def batal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Membatalkan proses pencatatan kapan saja."""
    context.user_data.clear()
    await update.message.reply_text(
        "Prosedur pencatatan dibatalkan.",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghitung dan menampilkan saldo total, rincian per akun, serta saldo bersih (savings)."""
    try:
        response = supabase.table("transactions").select("*").execute()
        data = response.data

        if not data:
            await update.message.reply_text(
                "Belum ada transaksi tercatat di database.",
                reply_markup=get_main_menu_keyboard()
            )
            return

        total_income = sum(item['amount'] for item in data if item.get('type') == 'income')
        total_expense = sum(item['amount'] for item in data if item.get('type') == 'expense')
        
        # Perhitungan Saldo per Akun
        bank_income = sum(item['amount'] for item in data if item.get('type') == 'income' and item.get('account') == 'bank')
        bank_expense = sum(item['amount'] for item in data if item.get('type') == 'expense' and item.get('account') == 'bank')
        bank_balance = bank_income - bank_expense

        cash_income = sum(item['amount'] for item in data if item.get('type') == 'income' and item.get('account') == 'cash')
        cash_expense = sum(item['amount'] for item in data if item.get('type') == 'expense' and item.get('account') == 'cash')
        cash_balance = cash_income - cash_expense

        savings = total_income - total_expense

        msg = (
            f"📊 **Ringkasan Keuangan MY WALLET**\n\n"
            f"🟢 **Total Pemasukan:** Rp {total_income:,.0f}\n".replace(",", ".") +
            f"🔴 **Total Pengeluaran:** Rp {total_expense:,.0f}\n".replace(",", ".") +
            f"──────────────\n"
            f"🏦 **Saldo Bank:** Rp {bank_balance:,.0f}\n".replace(",", ".") +
            f"💵 **Saldo Cash:** Rp {cash_balance:,.0f}\n".replace(",", ".") +
            f"──────────────\n"
            f"💰 **Total Savings (Saldo Bersih):** Rp {savings:,.0f}".replace(",", ".")
        )
        await update.message.reply_text(
            msg,
            reply_markup=get_main_menu_keyboard(),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error mengambil saldo: {e}")
        await update.message.reply_text(
            "Gagal mengambil data saldo dari database.",
            reply_markup=get_main_menu_keyboard()
        )

def main():
    TOKEN = "8841482158:AAGwDZp4UhX7qQltllmHJMtyBXTH_KTZPeo"

    application = ApplicationBuilder().token(TOKEN).build()

    # Conversation Handler untuk transaksi bertahap
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("masuk", mulai_transaksi),
            CommandHandler("keluar", mulai_transaksi),
            MessageHandler(filters.Regex("^(🟢 Masuk|🔴 Keluar)$"), mulai_transaksi)
        ],
        states={
            NOMINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, terima_nominal)],
            ACCOUNT: [CallbackQueryHandler(terima_account, pattern="^acc_")],
            KETERANGAN: [CallbackQueryHandler(terima_keterangan)]
        },
        fallbacks=[
            CommandHandler("batal", batal),
            MessageHandler(filters.Regex("^/batal$"), batal)
        ]
    )

    # Register Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("saldo", saldo))
    application.add_handler(conv_handler)
    
    # Handler pesan umum
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_text))

    print("Bot sedang berjalan... Tekan Ctrl+C untuk berhenti.")
    application.run_polling()

if __name__ == '__main__':
    main()
