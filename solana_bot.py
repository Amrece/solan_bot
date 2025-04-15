import os
import requests
import sqlite3
import json
import time
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

# تحميل الإعدادات
load_dotenv()

# الثوابت
BURN_ADDRESSES = {
    '1nc1nerator11111111111111111111111111111111',
    'burn111111111111111111111111111111111111111',
    '11111111111111111111111111111111'
}

class SolanaTokenBot:
    def __init__(self):
        self.db = sqlite3.connect('token_scanner.db')
        self.setup_database()
        
    def setup_database(self):
        """تهيئة قاعدة البيانات"""
        c = self.db.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS tokens (
            address TEXT PRIMARY KEY,
            symbol TEXT,
            first_seen TIMESTAMP,
            last_checked TIMESTAMP,
            status TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT,
            timestamp TIMESTAMP,
            price REAL,
            volume REAL,
            liquidity REAL,
            holders INTEGER,
            market_cap REAL,
            FOREIGN KEY(token_address) REFERENCES tokens(address)
        )''')
        self.db.commit()

    def fetch_qualified_tokens(self):
        """جلب التوكينز المؤهلة"""
        try:
            params = {
                'sort': 'marketCap',
                'order': 'desc',
                'blockchain': 'solana'
            }
            response = requests.get(os.getenv('DEXSCREENER_API') + '/tokens', params=params)
            data = response.json()
            qualified = []
            
            for token in data.get('tokens', []):
                if self.check_token_eligibility(token):
                    qualified.append(self.prepare_token_data(token))
            
            return qualified
        except Exception as e:
            print(f"Error fetching tokens: {e}")
            return []

    def check_token_eligibility(self, token):
        """فحص أهلية التوكين"""
        mcap = float(token.get('marketCap', 0))
        if not (float(os.getenv('MIN_MCAP')) <= mcap <= float(os.getenv('MAX_MCAP'))):
            return False
            
        created_at = datetime.fromtimestamp(token.get('pairCreatedAt', 0)/1000)
        if (datetime.now() - created_at) > timedelta(days=3):
            return False
            
        holders = self.get_token_holders(token['address'])
        if holders < 100000:
            return False
            
        if not self.is_decentralized(token['address']):
            return False
            
        return True

    def get_token_holders(self, token_address):
        """عدد حاملي التوكين"""
        try:
            url = f"{os.getenv('SOLSCAN_API')}/token/holders?token={token_address}"
            response = requests.get(url)
            return response.json().get('data', {}).get('total', 0)
        except:
            return 0

    def is_decentralized(self, token_address):
        """فحص اللامركزية"""
        try:
            url = f"{os.getenv('SOLSCAN_API')}/token/holders?token={token_address}&limit=10"
            response = requests.get(url)
            holders = response.json().get('data', {}).get('result', [])
            total_supply = float(response.json().get('data', {}).get('totalSupply', 1))
            
            filtered = [h for h in holders if h['address'] not in BURN_ADDRESSES]
            top10_share = sum(float(h['amount']) for h in filtered[:10]) / total_supply
            return top10_share <= 0.25
        except:
            return False

    def prepare_token_data(self, token):
        """إعداد بيانات التوكين"""
        return {
            'address': token['address'],
            'symbol': token['symbol'],
            'price': float(token['price']),
            'liquidity': float(token['liquidity']),
            'volume': float(token.get('volume24h', 0)),
            'market_cap': float(token.get('marketCap', 0)),
            'holders': self.get_token_holders(token['address']),
            'created_at': datetime.fromtimestamp(token.get('pairCreatedAt', 0)/1000)
        }

    def send_to_trading_bot(self, token_data):
        """إرسال للتداول الآلي"""
        try:
            payload = {
                'token_address': token_data['address'],
                'symbol': token_data['symbol'],
                'price': token_data['price'],
                'liquidity': token_data['liquidity'],
                'market_cap': token_data['market_cap'],
                'timestamp': datetime.now().isoformat()
            }
            
            response = requests.post(
                os.getenv('TRADING_BOT_WEBHOOK'),
                json=payload,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending to trading bot: {e}")
            return False

    def run(self):
        """تشغيل البوت"""
        print("Starting Solana Token Scanner")
        while True:
            try:
                tokens = self.fetch_qualified_tokens()
                for token in tokens:
                    if self.send_to_trading_bot(token):
                        self.save_token(token)
                time.sleep(300)  # انتظر 5 دقائق
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)

    def save_token(self, token):
        """حفظ التوكين في قاعدة البيانات"""
        c = self.db.cursor()
        c.execute('''
            INSERT OR REPLACE INTO tokens 
            VALUES (?, ?, ?, ?, ?)
        ''', (
            token['address'],
            token['symbol'],
            datetime.now(),
            datetime.now(),
            'processed'
        ))
        self.db.commit()

if __name__ == "__main__":
    bot = SolanaTokenBot()
    bot.run()
