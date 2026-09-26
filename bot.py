import os
import datetime
import logging
import uuid  # <--- Tambahkan import ini
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from supabase import create_client, Client

# Konfigurasi Logging untuk melihat status bot di terminal
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Konfigurasi Supabase (Gunakan credentials proyek website kamu)
SUPABASE_URL = "https://nfquoswrwtgegsprpuae.supabase.co"
SUPABASE_KEY = "sb_publishable_7zCLrX-DciJNflkgPUj6jQ_xb9G_mtf"

# Inisialisasi klien Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menyapa pengguna dan memberikan panduan perintah bot."""
    welcome_message = (
        "Halo! Selamat datang di Bot MY WALLET 💰\n\n"
        "Semua data yang kamu catat di sini akan langsung tersinkronisasi dengan website.\n\n"
        "**Perintah yang tersedia:**\n"
        "• `/masuk <jumlah> <keterangan>` - Mencatat pemasukan\n"
        "  Contoh: `/masuk 5000000 Gaji Bulanan`\n\n"
        "• `/keluar <jumlah> <keterangan>` - Mencatat pengeluaran\n"
        "  Contoh: `/keluar 25000 Makan Siang`\n\n"
        "• `/saldo` - Mengecek total pemasukan, pengeluaran, dan saldo saat ini\n"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def tambah_transaksi(update: Update, context: ContextTypes.DEFAULT_TYPE, tipe: str):
    """Fungsi helper universal untuk mencatat pemasukan atau pengeluaran."""
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            f"Format salah! Gunakan: `/{tipe} <jumlah> <keterangan>`\n"
            f"Contoh: `/{tipe} 50000 Beli Kopi`",
            parse_mode='Markdown'
        )
        return

    try:
        # Ambil jumlah uang (argumen pertama)
        amount = float(args[0])
        # Gabungkan sisa argumen menjadi keterangan/catatan
        note = " ".join(args[1:])
        
        # Tentukan tipe transaksi untuk database ('income' atau 'expense')
        db_type = 'income' if tipe == 'masuk' else 'expense'
        current_date = datetime.date.today().isoformat()

        # Data yang akan dimasukkan ke Supabase
               # Data yang akan dimasukkan ke Supabase (Tambahkan 'id' unik di sini)
        data_to_insert = {
            "id": f"bot_{uuid.uuid4().hex[:10]}",  # <--- ID Unik untuk mencegah error null constraint
            "type": db_type,
            "amount": amount,
            "category": "Lainnya" if db_type == 'expense' else "Pemasukan",
            "account": "cash",
            "note": note,
            "date": current_date
        }


        # Kirim data ke tabel 'transactions' di Supabase
        response = supabase.table("transactions").insert(data_to_insert).execute()

        if response.data:
            emoji = "🟢" if db_type == 'income' else "🔴"
            formatted_amount = f"Rp {amount:,.0f}".replace(",", ".")
            await update.message.reply_text(
                f"Berhasil dicatat! {emoji}\n\n"
                f"**Kategori:** {db_type.upper()}\n"
                f"**Jumlah:** {formatted_amount}\n"
                f"**Keterangan:** {note}\n"
                f"**Tanggal:** {current_date}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("Gagal menyimpan ke database. Coba lagi nanti.")

    except ValueError:
        await update.message.reply_text("Jumlah uang harus berupa angka! Contoh: `50000`", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error Supabase: {e}")
        await update.message.reply_text(f"Terjadi kesalahan sistem: {str(e)}")

async def masuk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /masuk"""
    await tambah_transaksi(update, context, 'masuk')

async def keluar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /keluar"""
    await tambah_transaksi(update, context, 'keluar')

async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghitung dan menampilkan total pemasukan, pengeluaran, dan saldo bersih."""
    try:
        # Ambil semua data dari tabel transactions
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
    # Token API Telegram yang telah Anda berikan
    TOKEN = "8841482158:AAGwDZp4UhX7qQltllmHJMtyBXTH_KTZPeo"

    # Inisialisasi Application Bot Telegram
    application = ApplicationBuilder().token(TOKEN).build()

    # Daftarkan command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("masuk", masuk))
    application.add_handler(CommandHandler("keluar", keluar))
    application.add_handler(CommandHandler("saldo", saldo))

    print("Bot sedang berjalan... Tekan Ctrl+C untuk berhenti.")
    # Jalankan bot dengan sistem polling
    application.run_polling()

if __name__ == '__main__':
    main()
