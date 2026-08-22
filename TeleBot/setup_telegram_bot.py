"""
Telegram Bot Commands & UI Automator
====================================
Run this script with your Telegram Bot Token to automatically configure:
1. Bot command menu (/start, /history, /trending, /compare, /interactions, /delete_data)
2. Short description & bot info banner
"""

import urllib.request
import json
import sys

BOT_TOKEN = input("أدخل توكن بوت التلجرام الخاص بك (Bot Token): ").strip()
if not BOT_TOKEN:
    print("❌ لم يتم إدخال التوكن. تم الإلغاء.")
    sys.exit(1)

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 1. Set Bot My Commands
commands_payload = {
    "commands": [
        {"command": "start", "description": "🏠 القائمة الرئيسية والترحيب"},
        {"command": "history", "description": "📋 سجل الاستعلامات السابقة"},
        {"command": "trending", "description": "🏆 الأدوية الأكثر بحثاً اليوم"},
        {"command": "compare", "description": "⚖️ مقارنة بين دوائين (Amoxicillin vs Augmentin)"},
        {"command": "interactions", "description": "🔄 فحص التداخلات الدوائية لقائمة أدوية"},
        {"command": "delete_data", "description": "🗑️ حذف كافة بياناتي الطبية المشفّرة"}
    ]
}

def call_telegram(method, data):
    req = urllib.request.Request(
        f"{BASE_URL}/{method}",
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            return res
    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بتلجرام ({method}): {e}")
        return None

print("🔄 جاري ضبط قائمة أوامر البوت على التلجرام...")
res1 = call_telegram("setMyCommands", commands_payload)
if res1 and res1.get("ok"):
    print("✅ تم ضبط الأوامر بنجاح!")
else:
    print("⚠️ فشل ضبط الأوامر.")

# 2. Set Bot Description
desc_payload = {
    "description": "🏥 MedSafety Bot — مساعدك الذكي الموثوق لفحص وتأكيد سلامة الأدوية، قراءة الروشتات، ومقارنة الأدوية مع الحفاظ على خصوصيتك بتشغيل AES-256-GCM."
}
call_telegram("setMyDescription", desc_payload)

print("\n🎉 تم إعداد قائمة وتفاصيل البوت على التلجرام بنجاح!")
