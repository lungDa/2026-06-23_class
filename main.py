import os
import json
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import yt_dlp
import pandas as pd
import gspread

app = FastAPI(title="雲端智慧電台")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 💡 定義歌曲的資料結構，解決 422 驗證錯誤
class SongItem(BaseModel):
    title: str
    url: str

# =======================================================
# 🔒 真正的、唯一的 gspread 初始化區塊
# =======================================================
def get_sheet_data():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("系統找不到 GOOGLE_CREDENTIALS 環境變數，請檢查 Render 後台設定。")
    
    creds_dict = json.loads(creds_json)
    gc = gspread.service_account_from_dict(creds_dict)
    sh = gc.open("music") 
    worksheet = sh.worksheet("playlists")
    return worksheet

# --- API 1: 取得歌單 ---
@app.get("/api/playlist")
def get_playlist():
    try:
        worksheet = get_sheet_data()
        records = worksheet.get_all_records()
        if not records:
            return []
        
        df = pd.DataFrame(records)
        df.columns = [str(c).lower().strip() for c in df.columns]
        
        if 'username' not in df.columns:
            return []
            
        return df[df['username'] == 'admin'].to_dict('records')
    except Exception as e:
        return {"error": f"資料庫連線失敗: {str(e)}"}

# --- API 2: 同步歌單 ---
@app.post("/api/playlist/sync")
def sync_playlist(playlist: List[SongItem]):  # 💡 這裡改用 List[SongItem] 接收
    try:
        worksheet = get_sheet_data()
        try:
            records = worksheet.get_all_records()
            if records:
                df_all = pd.DataFrame(records)
                df_all.columns = [str(c).lower().strip() for c in df_all.columns]
                df_others = df_all[df_all['username'] != 'admin']
            else:
                df_others = pd.DataFrame(columns=['username', 'title', 'url'])
        except:
            df_others = pd.DataFrame(columns=['username', 'title', 'url'])
            
        # 💡 將 Pydantic 模型陣列轉換為 Dict 列表，供 Pandas 讀取
        playlist_dicts = [item.dict() for item in playlist]
        new_data = pd.DataFrame(playlist_dicts)
        
        if not new_data.empty:
            new_data.columns = [str(c).lower().strip() for c in new_data.columns]
            new_data['username'] = 'admin'
            new_data = new_data[['username', 'title', 'url']]
            df_final = pd.concat([df_others, new_data], ignore_index=True)
        else:
            df_final = df_others[['username', 'title', 'url']] if 'username' in df_others.columns else pd.DataFrame(columns=['username', 'title', 'url'])
            
        worksheet.clear()
        worksheet.update([['username', 'title', 'url']] + df_final[['username', 'title', 'url']].values.tolist())
        return {"status": "success"}
    except Exception as e:
        return {"error": f"同步失敗: {str(e)}"}

# --- API 3: 搜尋歌曲 ---
@app.get("/api/search")
def search_songs(q: str = Query(...)):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True, 'playlistend': 20}) as ydl:
            res = ydl.extract_info(f"ytsearch20:{q}", download=False)
            entries = res.get('entries', [])
            
            cleaned_results = []
            for item in entries:
                url = item.get('url') if item.get('url') else f"https://www.youtube.com/watch?v={item.get('id')}"
                cleaned_results.append({
                    "title": item.get("title", "未知歌曲"),
                    "url": url
                })
            return cleaned_results
    except Exception as e:
        return {"error": f"搜尋失敗: {str(e)}"}

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()
