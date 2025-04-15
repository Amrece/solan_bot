#!/bin/bash
cd /path/to/bot/folder
source venv/bin/activate  # إذا كنت تستخدم بيئة افتراضية
python solana_bot.py >> bot.log 2>&1 &
