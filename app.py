import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone, timedelta

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Stock & Gold Pro Analyzer", layout="wide")
st.title("📈 ระบบวิเคราะห์กราฟหุ้นและทองคำ + วิเคราะห์เทรดชนข่าว (เวลาไทย)")

# --- แถบเมนูด้านซ้าย (Sidebar) ---
st.sidebar.header("ตั้งค่าการวิเคราะห์")

if st.sidebar.button("🔄 รีเฟรชข้อมูลล่าสุด", use_container_width=True):
    st.cache_data.clear()

preset = st.sidebar.selectbox(
    "เลือกสินทรัพย์แนะนำ",
    ["พิมพ์ชื่อย่อเอง", "ทองคำ (GC=F)", "หุ้น Apple (AAPL)", "หุ้น NVIDIA (NVDA)", "หุ้น PTT (PTT.BK)", "หุ้น AOT (AOT.BK)"]
)

preset_map = {
    "ทองคำ (GC=F)": "GC=F",
    "หุ้น Apple (AAPL)": "AAPL",
    "หุ้น NVIDIA (NVDA)": "NVDA",
    "หุ้น PTT (PTT.BK)": "PTT.BK",
    "หุ้น AOT (AOT.BK)": "AOT.BK"
}

if preset == "พิมพ์ชื่อย่อเอง":
    ticker = st.sidebar.text_input("ใส่ชื่อย่อหุ้น (เช่น TSLA, KBANK.BK)", value="GC=F").upper()
else:
    ticker = preset_map[preset]

# เลือก Timeframe
interval = st.sidebar.selectbox(
    "Timeframe",
    ["1m", "5m", "15m", "30m", "1h", "1d", "1wk"],
    index=2
)

if interval == "1m":
    period_options = ["1d", "5d"]
    default_idx = 1
elif interval in ["5m", "15m", "30m"]:
    period_options = ["1d", "5d", "1mo"]
    default_idx = 1
elif interval == "1h":
    period_options = ["5d", "1mo", "3mo", "6mo"]
    default_idx = 2
else:
    period_options = ["1mo", "3mo", "6mo", "1y", "2y"]
    default_idx = 2

period = st.sidebar.selectbox("ช่วงเวลาย้อนหลัง", period_options, index=default_idx)

# ตั้งค่า Indicator และตัวกรอง EMA 200
st.sidebar.subheader("ตั้งค่าอินดิเคเตอร์ & ตัวกรอง")
use_ema200 = st.sidebar.checkbox("🛡️ เปิดตัวกรองเทรนด์ใหญ่ (EMA 200)", value=True, help="คัดเฉพาะสัญญาณ BUY เหนือเส้น EMA 200 และ SELL ใต้เส้น EMA 200 เพื่อลดสัญญาณหลอกใน TF สั้น")
ema_fast_len = st.sidebar.number_input("EMA ระยะสั้น", min_value=5, max_value=50, value=9)
ema_slow_len = st.sidebar.number_input("EMA ระยะยาว", min_value=10, max_value=150, value=21)
rsi_len = st.sidebar.number_input("RSI Period", min_value=7, max_value=30, value=14)
rr_ratio = st.sidebar.number_input("อัตราส่วนกำไรต่อขาดทุน (RR 1:?)", min_value=1.0, max_value=5.0, value=1.5, step=0.5)

# ตั้งค่ากรองสกุลเงินข่าว Forex Factory
st.sidebar.subheader("ตั้งค่าปฏิทินข่าวกล่องแดง")
currency_filter = st.sidebar.multiselect(
    "เลือกสกุลเงินที่ต้องการดูข่าว",
    ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "CNY"],
    default=["USD", "EUR", "GBP", "JPY"]
)

# --- ฟังก์ชันวิเคราะห์ผลกระทบข่าวสำหรับทองคำและตลาด ---
def analyze_news_impact(title, currency):
    t = title.lower()
    if currency != "USD":
        return (
            f"กระทบคู่เงิน {currency} โดยตรง (อาจทำให้ดอลลาร์ผันผวนทางอ้อม)",
            "ดูตัวเลขจริงเทียบคาดการณ์: ดีกว่าคาด = สกุลเงินแข็งค่า",
            "500 - 1,200 จุด ($5 - $12)"
        )
    
    # วิเคราะห์ข่าวกล่องแดงของ USD ที่มีผลกับทองคำแรงที่สุด
    if any(k in t for k in ["non-farm", "nonfarm", "nfp", "employment change"]):
        return (
            "🔥 ข่าวจ้างงานนอกภาคเกษตร (แรงสุดของเดือน)",
            "ตัวเลขสูงกว่าคาด = ทองคำร่วง (SELL) | ต่ำกว่าคาด = ทองคำพุ่ง (BUY)",
            "2,000 - 4,000 จุด ($20 - $40)"
        )
    elif any(k in t for k in ["cpi", "inflation", "pce"]):
        return (
            "🔥 ข่าวเงินเฟ้อสหรัฐฯ (ชี้ชะตาดอกเบี้ย Fed)",
            "ตัวเลขสูงกว่าคาด = ทองคำร่วง (SELL) | ต่ำกว่าคาด = ทองคำพุ่ง (BUY)",
            "1,800 - 3,500 จุด ($18 - $35)"
        )
    elif any(k in t for k in ["fomc", "federal funds", "interest rate", "powell"]):
        return (
            "🔥 ประกาศดอกเบี้ย / แถลงการณ์ประธาน Fed",
            "คง/ขึ้นดอกเบี้ยหรือพูดแข็งกร้าว = ทองคำร่วง (SELL) | ลดดอกเบี้ย = ทองคำพุ่ง (BUY)",
            "2,500 - 5,000 จุด ($25 - $50)"
        )
    elif any(k in t for k in ["unemployment", "jobless claims"]):
        return (
            "⚡ ข่าวอัตราว่างงาน / ผู้ขอรับสวัสดิการว่างงาน",
            "คนว่างงานเพิ่มขึ้น (สูงกว่าคาด) = ทองคำพุ่ง (BUY) | ลดลง = ทองคำร่วง (SELL)",
            "1,000 - 2,000 จุด ($10 - $20)"
        )
    elif any(k in t for k in ["gdp", "retail sales", "pmi", "ism"]):
        return (
            "⚡ ข่าวตัวเลขเศรษฐกิจ / ยอดค้าปลีก / ภาคการผลิต",
            "ตัวเลขดีกว่าคาด = ทองคำร่วง (SELL) | แย่กว่าคาด = ทองคำพุ่ง (BUY)",
            "1,000 - 2,200 จุด ($10 - $22)"
        )
    else:
        return (
            "⚡ ข่าวเศรษฐกิจสำคัญของสหรัฐฯ (USD High Impact)",
            "ตัวเลขจริงออกมาสูงกว่าคาด (เขียว) = กดดันทองคำลง (SELL)",
            "800 - 1,800 จุด ($8 - $18)"
        )

# --- ฟังก์ชันดึงข่าวกล่องแดงจาก Forex Factory ---
@st.cache_data(ttl=3600) # แคชไว้ 1 ชั่วโมงเพื่อไม่ให้โดนบล็อก
def get_ff_red_news():
    urls = [
        "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                events = res.json()
                red_events = []
                tz_th = timezone(timedelta(hours=7))
                now_th = datetime.now(tz_th)
                today_str = now_th.strftime("%Y-%m-%d")

                for ev in events:
                    if ev.get("impact") == "High":
                        raw_date = ev.get("date", "")
                        title = ev.get("title", "-")
                        currency = ev.get("country", "-")
                        try:
                            dt = datetime.fromisoformat(raw_date).astimezone(tz_th)
                            date_str = dt.strftime("%Y-%m-%d")
                            time_str = dt.strftime("%H:%M น.")
                            day_label = "🔥 วันนี้" if date_str == today_str else dt.strftime("%d/%m/%Y")
                        except:
                            date_str = raw_date[:10]
                            time_str = "-"
                            day_label = date_str

                        impact_desc, direction_guide, est_points = analyze_news_impact(title, currency)

                        red_events.append({
                            "สถานะวัน": day_label,
                            "เวลา (ไทย)": time_str,
                            "สกุลเงิน": currency,
                            "หัวข้อข่าวกล่องแดง": title,
                            "คาดการณ์": ev.get("forecast") or "-",
                            "ครั้งก่อน": ev.get("previous") or "-",
                            "คาดการณ์ทิศทางทองคำ": direction_guide,
                            "ระยะวิ่งเฉลี่ย (ทองคำ)": est_points,
                            "ความสำคัญ": impact_desc
                        })
                if red_events:
                    return pd.DataFrame(red_events)
        except Exception:
            continue
    return pd.DataFrame()

# --- ส่วนแสดงวิเคราะห์เทรดชนข่าว (ด้านบนสุด) ---
st.subheader("🚨 แผนเทรดชนข่าว & ปฏิทินข่าวกล่องแดง (เวลาไทย GMT+7)")
ff_df = get_ff_red_news()

if not ff_df.empty:
    if currency_filter:
        ff_df = ff_df[ff_df["สกุลเงิน"].isin(currency_filter)]
    
    today_news = ff_df[ff_df["สถานะวัน"] == "🔥 วันนี้"]
    if not today_news.empty:
        st.error(f"⚠️ **วันนี้มีข่าวกล่องแดง {len(today_news)} รายการ!** ดูทิศทางและระยะวิ่งคาดการณ์ด้านล่างก่อนเข้าออเดอร์:")
        st.dataframe(
            today_news[["เวลา (ไทย)", "สกุลเงิน", "หัวข้อข่าวกล่องแดง", "คาดการณ์", "ครั้งก่อน", "คาดการณ์ทิศทางทองคำ", "ระยะวิ่งเฉลี่ย (ทองคำ)"]],
            use_container_width=True, hide_index=True
        )
    else:
        st.success("✅ **วันนี้ไม่มีข่าวกล่องแดง** ในสกุลเงินที่เลือก สามารถดูตารางข่าวแรงทั้งสัปดาห์เพื่อเตรียมตัวล่วงหน้าได้ด้านล่างครับ")

    with st.expander("📅 ดูตารางวิเคราะห์ข่าวกล่องแดงทั้งหมดในสัปดาห์นี้ (พร้อมทิศทางและระยะวิ่ง)", expanded=today_news.empty):
        st.dataframe(
            ff_df[["สถานะวัน", "เวลา (ไทย)", "สกุลเงิน", "หัวข้อข่าวกล่องแดง", "คาดการณ์", "ครั้งก่อน", "คาดการณ์ทิศทางทองคำ", "ระยะวิ่งเฉลี่ย (ทองคำ)"]],
            use_container_width=True, hide_index=True
        )
else:
    st.info("ไม่สามารถดึงฟีดข่าวอัตโนมัติจาก Forex Factory ได้ชั่วคราว สามารถเปิดดูได้ที่ [Forex Factory Calendar](https://forexfactory.com)")

st.divider()

# --- ฟังก์ชันดึงข้อมูลราคาและแปลงเป็นเวลาไทย ---
@st.cache_data(ttl=60)
def get_data(symbol, p, i):
    df = yf.download(symbol, period=p, interval=i, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if not df.empty:
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert('Asia/Bangkok')
        else:
            df.index = df.index.tz_convert('Asia/Bangkok')
    return df

@st.cache_data(ttl=300)
def get_news(symbol):
    try:
        search_sym = "GLD" if symbol in ["GC=F", "XAUUSD=X"] else symbol
        t = yf.Ticker(search_sym)
        return t.news
    except:
        return []

# --- ฟังก์ชันจำลองประวัติการเทรดย้อนหลัง (Backtest) ---
def run_backtest(df, rr):
    trades = []
    in_trade = False
    trade_type = ""
    entry_price = 0.0
    tp_price = 0.0
    sl_price = 0.0
    entry_time = ""

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        if pd.isna(prev_row['ATR']) or prev_row['ATR'] == 0:
            continue

        if in_trade:
            if trade_type == "BUY":
                if row['Low'] <= sl_price:
                    trades.append({"เวลาเข้า (ไทย)": entry_time, "ฝั่ง": "BUY 🟢", "ราคาเข้า": round(entry_price, 2), "TP": round(tp_price, 2), "SL": round(sl_price, 2), "ผลลัพธ์": "LOSS ❌"})
                    in_trade = False
                elif row['High'] >= tp_price:
                    trades.append({"เวลาเข้า (ไทย)": entry_time, "ฝั่ง": "BUY 🟢", "ราคาเข้า": round(entry_price, 2), "TP": round(tp_price, 2), "SL": round(sl_price, 2), "ผลลัพธ์": "WIN 🏆"})
                    in_trade = False
            elif trade_type == "SELL":
                if row['High'] >= sl_price:
                    trades.append({"เวลาเข้า (ไทย)": entry_time, "ฝั่ง": "SELL 🔴", "ราคาเข้า": round(entry_price, 2), "TP": round(tp_price, 2), "SL": round(sl_price, 2), "ผลลัพธ์": "LOSS ❌"})
                    in_trade = False
                elif row['Low'] <= tp_price:
                    trades.append({"เวลาเข้า (ไทย)": entry_time, "ฝั่ง": "SELL 🔴", "ราคาเข้า": round(entry_price, 2), "TP": round(tp_price, 2), "SL": round(sl_price, 2), "ผลลัพธ์": "WIN 🏆"})
                    in_trade = False

        if not in_trade:
            if prev_row['Filtered_Pos'] == 1:
                in_trade = True
                trade_type = "BUY"
                entry_price = float(row['Open'])
                atr = float(prev_row['ATR'])
                sl_price = entry_price - atr
                tp_price = entry_price + (atr * rr)
                entry_time = df.index[i].strftime("%d/%m/%Y %H:%M")
            elif prev_row['Filtered_Pos'] == -1:
                in_trade = True
                trade_type = "SELL"
                entry_price = float(row['Open'])
                atr = float(prev_row['ATR'])
                sl_price = entry_price + atr
                tp_price = entry_price - (atr * rr)
                entry_time = df.index[i].strftime("%d/%m/%Y %H:%M")

    if in_trade:
        trades.append({"เวลาเข้า (ไทย)": entry_time, "ฝั่ง": f"{trade_type} (ถืออยู่)", "ราคาเข้า": round(entry_price, 2), "TP": round(tp_price, 2), "SL": round(sl_price, 2), "ผลลัพธ์": "กำลังวิ่ง ⏳"})

    return pd.DataFrame(trades)

try:
    data = get_data(ticker, period, interval)

    if data.empty:
        st.error(f"ไม่พบข้อมูลสำหรับ '{ticker}' กรุณาตรวจสอบชื่อย่ออีกครั้ง")
    else:
        # คำนวณ EMA สั้น, ยาว และ EMA 200
        data['EMA_Fast'] = data['Close'].ewm(span=ema_fast_len, adjust=False).mean()
        data['EMA_Slow'] = data['Close'].ewm(span=ema_slow_len, adjust=False).mean()
        data['EMA_200'] = data['Close'].ewm(span=200, adjust=False).mean()

        # คำนวณ RSI
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_len).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_len).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))

        # คำนวณ ATR
        high_low = data['High'] - data['Low']
        high_close = np.abs(data['High'] - data['Close'].shift())
        low_close = np.abs(data['Low'] - data['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        data['ATR'] = np.max(ranges, axis=1).rolling(14).mean()

        # หาจุดตัด EMA พื้นฐาน
        data['Signal'] = 0
        data.loc[data['EMA_Fast'] > data['EMA_Slow'], 'Signal'] = 1
        data['Raw_Pos'] = data['Signal'].diff()

        # กรองสัญญาณด้วย EMA 200 (หากเปิดใช้งาน)
        data['Filtered_Pos'] = 0
        if use_ema200:
            data.loc[(data['Raw_Pos'] == 1) & (data['Close'] > data['EMA_200']), 'Filtered_Pos'] = 1
            data.loc[(data['Raw_Pos'] == -1) & (data['Close'] < data['EMA_200']), 'Filtered_Pos'] = -1
        else:
            data['Filtered_Pos'] = data['Raw_Pos']

        buy_signals = data[data['Filtered_Pos'] == 1]
        sell_signals = data[data['Filtered_Pos'] == -1]

        # แจ้งเตือนบนหน้าจอหากเพิ่งเกิดสัญญาณผ่านตัวกรองใน 2 แท่งล่าสุด
        recent_pos = data['Filtered_Pos'].iloc[-2:].values
        if 1 in recent_pos:
            st.toast("🚨 แจ้งเตือน: เพิ่งเกิดสัญญาณเข้าซื้อ (BUY) ตามเทรนด์!", icon="🟢")
            st.success("🔔 **แจ้งเตือนสัญญาณใหม่:** เพิ่งเกิดจุดตัดขาขึ้น (BUY) ที่ผ่านตัวกรองเรียบร้อย!")
        elif -1 in recent_pos:
            st.toast("🚨 แจ้งเตือน: เพิ่งเกิดสัญญาณขาย (SELL) ตามเทรนด์!", icon="🔴")
            st.error("🔔 **แจ้งเตือนสัญญาณใหม่:** เพิ่งเกิดจุดตัดขาลง (SELL) ที่ผ่านตัวกรองเรียบร้อย!")

        latest_close = float(data['Close'].iloc[-1])
        prev_close = float(data['Close'].iloc[-2])
        price_change = latest_close - prev_close
        pct_change = (price_change / prev_close) * 100
        latest_rsi = float(data['RSI'].iloc[-1])
        latest_ema_fast = float(data['EMA_Fast'].iloc[-1])
        latest_ema_slow = float(data['EMA_Slow'].iloc[-1])
        latest_ema_200 = float(data['EMA_200'].iloc[-1])
        latest_atr = float(data['ATR'].iloc[-1]) if not np.isnan(data['ATR'].iloc[-1]) else latest_close * 0.01

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("ราคาล่าสุด", f"{latest_close:,.2f}", f"{price_change:+.2f} ({pct_change:+.2f}%)")
        col2.metric(f"RSI ({rsi_len})", f"{latest_rsi:.2f}")
        
        if latest_close > latest_ema_200 and latest_ema_fast > latest_ema_slow:
            trend = "ขาขึ้นแข็งแกร่ง 🟢"
            action = "เน้นฝั่ง BUY ตามเทรนด์"
            tp_price = latest_close + (latest_atr * rr_ratio)
            sl_price = latest_close - latest_atr
        elif latest_close < latest_ema_200 and latest_ema_fast < latest_ema_slow:
            trend = "ขาลงแข็งแกร่ง 🔴"
            action = "เน้นฝั่ง SELL ตามเทรนด์"
            tp_price = latest_close - (latest_atr * rr_ratio)
            sl_price = latest_close + latest_atr
        else:
            trend = "พักตัว / สวนเทรนด์ใหญ่ 🟡"
            action = "ชะลอการเข้า / รอเลือกทาง"
            tp_price = latest_close + (latest_atr * rr_ratio) if latest_ema_fast > latest_ema_slow else latest_close - (latest_atr * rr_ratio)
            sl_price = latest_close - latest_atr if latest_ema_fast > latest_ema_slow else latest_close + latest_atr

        col3.metric("แนวโน้ม (เทียบ EMA 200)", trend)
        rsi_status = "Overbought ⚠️" if latest_rsi >= 70 else ("Oversold 🛒" if latest_rsi <= 30 else "ปกติ ⚪")
        col4.metric("สถานะ RSI", rsi_status)

        st.subheader(f"🎯 แผนการเทรดปัจจุบัน (ตั้งค่า RR 1:{rr_ratio})")
        p_col1, p_col2, p_col3 = st.columns(3)
        p_col1.info(f"**แนวทาง:** {action}\n\n**จุดเข้าอ้างอิง:** `{latest_close:,.2f}`")
        p_col2.success(f"**เป้าหมายกำไร (TP):** `{tp_price:,.2f}`")
        p_col3.error(f"**จุดตัดขาดทุน (SL):** `{sl_price:,.2f}`")

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.05, row_heights=[0.7, 0.3],
            subplot_titles=(f"กราฟราคา {ticker} (TF: {interval} - เวลาไทย)", "ดัชนี RSI")
        )

        fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="ราคา"), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_Fast'], line=dict(color='orange', width=1.5), name=f'EMA {ema_fast_len}'), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_Slow'], line=dict(color='cyan', width=1.5), name=f'EMA {ema_slow_len}'), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_200'], line=dict(color='white', width=2, dash='dot'), name='EMA 200 (เส้นแบ่งเทรนด์)'), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['Low'] * 0.999, mode='markers', marker=dict(symbol='triangle-up', size=12, color='lime'), name='จุดสัญญาณ BUY'), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['High'] * 1.001, mode='markers', marker=dict(symbol='triangle-down', size=12, color='red'), name='จุดสัญญาณ SELL'), row=1, col=1)

        fig.add_trace(go.Scatter(x=data.index, y=data['RSI'], line=dict(color='purple', width=1.5), name='RSI'), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

        fig.update_layout(height=650, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📊 ประวัติสัญญาณย้อนหลัง & ผลการทดสอบตั้ง TP/SL (Backtest เวลาไทย)")
        bt_df = run_backtest(data, rr_ratio)
        if not bt_df.empty:
            closed_trades = bt_df[bt_df['ผลลัพธ์'].isin(["WIN 🏆", "LOSS ❌"])]
            wins = len(closed_trades[closed_trades['ผลลัพธ์'] == "WIN 🏆"])
            total_closed = len(closed_trades)
            win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

            b_col1, b_col2, b_col3 = st.columns(3)
            b_col1.metric("จำนวนออเดอร์ที่ปิดแล้ว", f"{total_closed} ไม้")
            b_col2.metric("จำนวนไม้ที่ชนะ (TP)", f"{wins} ไม้")
            b_col3.metric("อัตราชนะ (Win Rate)", f"{win_rate:.1f}%")

            st.dataframe(bt_df.iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.write("ยังไม่พบประวัติการเกิดสัญญาณที่ผ่านเกณฑ์ในช่วงเวลาที่เลือก ลองขยายช่วงเวลาย้อนหลังหรือปิดตัวกรอง EMA 200 ชั่วคราวครับ")

        st.subheader(f"📰 ข่าวสารล่าสุด & วิเคราะห์แนวโน้มจากข่าว ({ticker})")
        news_list = get_news(ticker)
        if news_list:
            pos_words = ['surge', 'jump', 'rise', 'gain', 'bull', 'high', 'record', 'rally', 'boost', 'growth', 'up', 'soar']
            neg_words = ['drop', 'fall', 'plunge', 'bear', 'low', 'slump', 'crash', 'down', 'fear', 'loss', 'decline', 'cut']
            
            score = 0
            news_items_display = []

            for item in news_list[:6]:
                content = item.get('content', item)
                title = content.get('title', 'ไม่มีหัวข้อข่าว')
                publisher = content.get('provider', {}).get('displayName', content.get('publisher', 'แหล่งข่าว'))
                link = content.get('canonicalUrl', {}).get('url', content.get('link', '#'))
                pub_date = content.get('pubDate', '')[:16].replace('T', ' ')

                title_lower = title.lower()
                if any(w in title_lower for w in pos_words):
                    score += 1
                    tag = "🟢 ข่าวบวก"
                elif any(w in title_lower for w in neg_words):
                    score -= 1
                    tag = "🔴 ข่าวลบ"
                else:
                    tag = "⚪ ข่าวทั่วไป"

                news_items_display.append(f"- {tag} `[{pub_date}]` **[{title}]({link})** *(โดย {publisher})*")

            if score > 0:
                st.success(f"**บทวิเคราะห์จากข่าว (คะแนน +{score}):** พาดหัวข่าวส่วนใหญ่เป็นเชิงบวก มีโอกาสหนุนให้กราฟ **ปรับตัวขึ้น (Bullish)**")
            elif score < 0:
                st.error(f"**บทวิเคราะห์จากข่าว (คะแนน {score}):** พาดหัวข่าวส่วนใหญ่เป็นเชิงลบ มีโอกาสกดดันให้กราฟ **ปรับตัวลง (Bearish)**")
            else:
                st.info("**บทวิเคราะห์จากข่าว (คะแนน 0):** ข่าวสารโดยรวมยังเป็นกลาง กราฟมีโอกาสวิ่งออกข้าง (Sideway) หรือรอปัจจัยใหม่")

            for line in news_items_display:
                st.markdown(line)
        else:
            st.write("ไม่พบข่าวสารล่าสุดสำหรับสินทรัพย์นี้ในขณะนี้")

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
