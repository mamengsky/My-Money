import os
import datetime
import logging
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
NOMINAL, KETERANGAN = range(2)

# Opsi Kategori / Keterangan dari Gambar & Tambahan Gaji/Income
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menyapa pengguna dan memberikan panduan perintah bot."""
    welcome_message = (
        "Halo! Selamat datang di Bot MY WALLET 💰\n\n"
        "Semua data yang kamu catat di sini akan langsung tersinkronisasi dengan website.\n\n"
        "**Perintah yang tersedia:**\n"
        "• `/masuk` - Mencatat pemasukan secara bertahap\n"
        "• `/keluar` - Mencatat pengeluaran secara bertahap\n"
        "• `/saldo` - Mengecek total pemasukan, pengeluaran, dan saldo saat ini\n"
        "• `/batal` - Membatalkan proses pencatatan\n"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def mulai_transaksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 1: Memulai alur dengan menentukan tipe (masuk/keluar)."""
    command = update.message.text.split()[0].replace("/", "")
    context.user_data['type'] = command  # simpan 'masuk' atau 'keluar'
    
    tipe_text = "pemasukan 🟢" if command == "masuk" else "pengeluaran 🔴"
    await update.message.reply_text(
        f"Silakan ketikkan nominal **{tipe_text}** (contoh: `50000`):",
        parse_mode='Markdown'
    )
    return NOMINAL

async def terima_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 2: Menerima input nominal angka, lalu menampilkan tombol opsi keterangan."""
    text = update.message.text.strip().replace(".", "").replace(",", "")
    
    try:
        amount = float(text)
        if amount <= 0:
            await update.message.reply_text("Nominal harus lebih dari 0. Silakan masukkan angka lagi:")
            return NOMINAL
            
        context.user_data['amount'] = amount
        tipe = context.user_data['type']
        
        # Buat daftar tombol (Inline Keyboard)
        options = INCOME_OPTIONS if tipe == "masuk" else EXPENSE_OPTIONS
        keyboard = []
        
        for item in options:
            keyboard.append([InlineKeyboardButton(item, callback_data=item)])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        formatted_amount = f"Rp {amount:,.0f}".replace(",", ".")
        await update.message.reply_text(
            f"Nominal dicatat: **{formatted_amount}**\n\n"
            f"Pilih **keterangan/kategori** {tipe} di bawah ini:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return KETERANGAN

    except ValueError:
        await update.message.reply_text("Nominal harus berupa angka saja! Silakan ketik ulang nominalnya:")
        return NOMINAL

async def terima_keterangan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 3: Menerima pilihar tombol keterangan, lalu menyimpan data ke Supabase."""
    query = update.callback_query
    await query.answer()
    
    note = query.data
    tipe = context.user_data.get('type')
    amount = context.user_data.get('amount')
    
    db_type = 'income' if tipe == 'masuk' else 'expense'
    current_date = datetime.date.today().isoformat()

    # Data yang disiapkan untuk Supabase
    data_to_insert = {
        "id": f"bot_{uuid.uuid4().hex[:10]}",
        "type": db_type,
        "amount": amount,
        "category": note if db_type == 'expense' else "Pemasukan",
        "account": "cash",
        "note": note,
        "date": current_date
    }

    try:
        response = supabase.table("transactions").insert(data_to_insert).execute()

        if response.data:
            emoji = "🟢" if db_type == 'income' else "🔴"
            formatted_amount = f"Rp {amount:,.0f}".replace(",", ".")
            
            await query.edit_message_text(
                f"✅ **Berhasil dicatat!** {emoji}\n\n"
                f"**Jenis:** {db_type.upper()}\n"
                f"**Jumlah:** {formatted_amount}\n"
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
    await update.message.reply_text("Prositur pencatatan dibatalkan.")
    return ConversationHandler.END

async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghitung dan menampilkan total pemasukan, pengeluaran, dan saldo bersih."""
    try:
        response = supabase.table("transactions").select("*").execute()
        data = response.data

        if not data:
            await update.message.reply_text("Belum ada transaksi tercatat di database.")
            return

        total_income = sum(item['amount'] for item in data if item.get('type') == 'income')
        total_expense = sum(item['amount'] for item in data if item.get('type') == 'expense')
        net_balance = total_income - total_expense

        msg = (
            f"📊 **Ringkasan Keuangan MY WALLET**\n\n"
            f"🟢 **Total Pemasukan:** Rp {total_income:,.0f}\n".replace(",", ".") +
            f"🔴 **Total Pengeluaran:** Rp {total_expense:,.0f}\n".replace(",", ".") +
            f"──────────────────\n"
            f"💰 **Saldo Bersih:** Rp {net_balance:,.0f}".replace(",", ".")
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error mengambil saldo: {e}")
        await update.message.reply_text("Gagal mengambil data saldo dari database.")

def main():
    TOKEN = "8841482158:AAGwDZp4UhX7qQltllmHJMtyBXTH_KTZPeo"

    application = ApplicationBuilder().token(TOKEN).build()

    # Conversation Handler untuk alur bertahap /masuk dan /keluar
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("masuk", mulai_transaksi),
            CommandHandler("keluar", mulai_transaksi)
        ],
        states={
            NOMINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, terima_nominal)],
            KETERANGAN: [CallbackQueryHandler(terima_keterangan)]
        },
        fallbacks=[CommandHandler("batal", batal)]
    )

    # Register Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("saldo", saldo))
    application.add_handler(conv_handler)

    print("Bot sedang berjalan... Tekan Ctrl+C untuk berhenti.")
    application.run_polling()

if __name__ == '__main__':
    main()
