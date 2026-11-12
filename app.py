import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Stock & Gold Pro Analyzer", layout="wide")
st.title("📈 ระบบวิเคราะห์กราฟหุ้นและทองคำ (Pro Version)")

# --- แถบเมนูด้านซ้าย (Sidebar) ---
st.sidebar.header("ตั้งค่าการวิเคราะห์")

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

# เลือก Timeframe ครบทั้งสั้นและยาว
interval = st.sidebar.selectbox(
    "Timeframe",
    ["1m", "5m", "15m", "30m", "1h", "1d", "1wk"],
    index=2 # ค่าเริ่มต้นที่ 15m
)

# กำหนดช่วงเวลาย้อนหลังให้เหมาะกับข้อจำกัดของแต่ละ TF
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

period = st.sidebar.selectbox("ช่วงเวลาย้อนหลัง (ปรับตาม TF)", period_options, index=default_idx)

# ตั้งค่า Indicator
st.sidebar.subheader("ตั้งค่าเส้นค่าเฉลี่ย & RSI")
ema_fast_len = st.sidebar.number_input("EMA ระยะสั้น", min_value=5, max_value=50, value=9)
ema_slow_len = st.sidebar.number_input("EMA ระยะยาว", min_value=10, max_value=200, value=21)
rsi_len = st.sidebar.number_input("RSI Period", min_value=7, max_value=30, value=14)

# --- ฟังก์ชันดึงข้อมูลและคำนวณ ---
@st.cache_data(ttl=60) # อัปเดตข้อมูลทุก 1 นาที
def get_data(symbol, p, i):
    df = yf.download(symbol, period=p, interval=i, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

@st.cache_data(ttl=300)
def get_news(symbol):
    try:
        t = yf.Ticker(symbol)
        return t.news
    except:
        return []

try:
    data = get_data(ticker, period, interval)

    if data.empty:
        st.error(f"ไม่พบข้อมูลสำหรับ '{ticker}' กรุณาตรวจสอบชื่อย่ออีกครั้ง")
    else:
        # คำนวณ EMA
        data['EMA_Fast'] = data['Close'].ewm(span=ema_fast_len, adjust=False).mean()
        data['EMA_Slow'] = data['Close'].ewm(span=ema_slow_len, adjust=False).mean()

        # คำนวณ RSI
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_len).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_len).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))

        # คำนวณ ATR (สำหรับหาจุด Stop Loss และ Take Profit)
        high_low = data['High'] - data['Low']
        high_close = np.abs(data['High'] - data['Close'].shift())
        low_close = np.abs(data['Low'] - data['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        data['ATR'] = true_range.rolling(14).mean()

        # หาจุดตัด EMA (Buy / Sell Signals)
        data['Signal'] = 0
        data.loc[data['EMA_Fast'] > data['EMA_Slow'], 'Signal'] = 1
        data['Position'] = data['Signal'].diff()

        buy_signals = data[data['Position'] == 1]
        sell_signals = data[data['Position'] == -1]

        # ค่าล่าสุด
        latest_close = float(data['Close'].iloc[-1])
        prev_close = float(data['Close'].iloc[-2])
        price_change = latest_close - prev_close
        pct_change = (price_change / prev_close) * 100
        latest_rsi = float(data['RSI'].iloc[-1])
        latest_ema_fast = float(data['EMA_Fast'].iloc[-1])
        latest_ema_slow = float(data['EMA_Slow'].iloc[-1])
        latest_atr = float(data['ATR'].iloc[-1]) if not np.isnan(data['ATR'].iloc[-1]) else latest_close * 0.01

        # --- ส่วนสรุปผลด้านบน ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("ราคาล่าสุด", f"{latest_close:,.2f}", f"{price_change:+.2f} ({pct_change:+.2f}%)")
        col2.metric(f"RSI ({rsi_len})", f"{latest_rsi:.2f}")
        
        if latest_ema_fast > latest_ema_slow:
            trend = "ขาขึ้น (Uptrend) 🟢"
            action = "รอจังหวะ BUY / ถือต่อ"
            tp_price = latest_close + (latest_atr * 2.0)
            sl_price = latest_close - (latest_atr * 1.0)
        else:
            trend = "ขาลง (Downtrend) 🔴"
            action = "รอจังหวะ SELL / ชะลอซื้อ"
            tp_price = latest_close - (latest_atr * 2.0)
            sl_price = latest_close + (latest_atr * 1.0)

        col3.metric("แนวโน้ม (EMA)", trend)

        if latest_rsi >= 70:
            rsi_status = "Overbought (ระวังย่อ) ⚠️"
        elif latest_rsi <= 30:
            rsi_status = "Oversold (ลุ้นเด้ง) 🛒"
        else:
            rsi_status = "ปกติ (Neutral) ⚪"
        col4.metric("สถานะ RSI", rsi_status)

        # --- กล่องคำแนะนำจุดเข้า-จุดออกเบื้องต้น ---
        st.subheader("🎯 แผนการเทรดและจุดเข้า-ออกเบื้องต้น (อ้างอิง EMA & ATR)")
        p_col1, p_col2, p_col3 = st.columns(3)
        p_col1.info(f"**คำแนะนำ:** {action}\n\n**จุดเข้า (Entry):** ประมาณ `{latest_close:,.2f}`")
        p_col2.success(f"**เป้าหมายทำกำไร (TP):** `{tp_price:,.2f}`\n\n(ระยะคาดหวัง 2 เท่าของความผันผวน)")
        p_col3.error(f"**จุดตัดขาดทุน (SL):** `{sl_price:,.2f}`\n\n(ระยะตัดขาดทุน 1 เท่าของความผันผวน)")

        # --- ส่วนวาดกราฟ Plotly ---
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.05, row_heights=[0.7, 0.3],
            subplot_titles=(f"กราฟราคา {ticker} (TF: {interval})", "ดัชนี RSI")
        )

        # กราฟแท่งเทียน
        fig.add_trace(go.Candlestick(
            x=data.index,
            open=data['Open'], high=data['High'],
            low=data['Low'], close=data['Close'],
            name="ราคา"
        ), row=1, col=1)

        # เส้น EMA
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_Fast'], line=dict(color='orange', width=1.5), name=f'EMA {ema_fast_len}'), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_Slow'], line=dict(color='cyan', width=1.5), name=f'EMA {ema_slow_len}'), row=1, col=1)

        # สัญลักษณ์จุดซื้อ (สามเหลี่ยมสีเขียวชี้ขึ้น)
        fig.add_trace(go.Scatter(
            x=buy_signals.index, y=buy_signals['Low'] * 0.999,
            mode='markers', marker=dict(symbol='triangle-up', size=12, color='lime'),
            name='จุดสัญญาณ BUY'
        ), row=1, col=1)

        # สัญลักษณ์จุดขาย (สามเหลี่ยมสีแดงชี้ลง)
        fig.add_trace(go.Scatter(
            x=sell_signals.index, y=sell_signals['High'] * 1.001,
            mode='markers', marker=dict(symbol='triangle-down', size=12, color='red'),
            name='จุดสัญญาณ SELL'
        ), row=1, col=1)

        # กราฟ RSI
        fig.add_trace(go.Scatter(x=data.index, y=data['RSI'], line=dict(color='purple', width=1.5), name='RSI'), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

        fig.update_layout(height=700, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        # --- ส่วนแสดงข่าวสารล่าสุด ---
        st.subheader(f"📰 ข่าวสารล่าสุดที่เกี่ยวข้องกับ {ticker}")
        news_list = get_news(ticker)
        if news_list:
            for item in news_list[:5]:
                # รองรับโครงสร้างข้อมูลข่าวของ yfinance เวอร์ชันใหม่และเก่า
                content = item.get('content', item)
                title = content.get('title', 'ไม่มีหัวข้อข่าว')
                publisher = content.get('provider', {}).get('displayName', content.get('publisher', 'แหล่งข่าวการเงิน'))
                link = content.get('canonicalUrl', {}).get('url', content.get('link', '#'))
                st.markdown(f"- **[{title}]({link})** *(โดย {publisher})*")
        else:
            st.write("ไม่พบข่าวสารล่าสุดสำหรับสินทรัพย์นี้ในขณะนี้ (มักพบข่าวเยอะในหุ้นอเมริกา เช่น AAPL, NVDA, TSLA)")

        # แสดงตารางข้อมูลย้อนหลัง
        with st.expander("ดูตารางข้อมูลราคาย้อนหลัง"):
            st.dataframe(data.tail(20).sort_index(ascending=False))

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
