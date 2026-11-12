import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Stock & Gold Analyzer", layout="wide")
st.title("📈 ระบบวิเคราะห์กราฟหุ้นและทองคำ")

# --- แถบเมนูด้านซ้าย (Sidebar) ---
st.sidebar.header("ตั้งค่าการวิเคราะห์")

# เลือกสินทรัพย์ยอดนิยม หรือพิมพ์ชื่อย่อเอง
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

# เลือกช่วงเวลาและ Timeframe
period = st.sidebar.selectbox("ช่วงเวลาย้อนหลัง", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)
interval = st.sidebar.selectbox("Timeframe", ["1h", "1d", "1wk"], index=1)

# ตั้งค่า Indicator
st.sidebar.subheader("ตั้งค่าเส้นค่าเฉลี่ย & RSI")
ema_fast_len = st.sidebar.number_input("EMA ระยะสั้น", min_value=5, max_value=50, value=20)
ema_slow_len = st.sidebar.number_input("EMA ระยะยาว", min_value=20, max_value=200, value=50)
rsi_len = st.sidebar.number_input("RSI Period", min_value=7, max_value=30, value=14)

# --- ฟังก์ชันดึงข้อมูลและคำนวณ ---
@st.cache_data(ttl=300) # แคชข้อมูลไว้ 5 นาทีเพื่อไม่ให้โหลดซ้ำบ่อยเกินไป
def get_data(symbol, p, i):
    df = yf.download(symbol, period=p, interval=i, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

try:
    data = get_data(ticker, period, interval)

    if data.empty:
        st.error(f"ไม่พบข้อมูลสำหรับ '{ticker}' กรุณาตรวจสอบชื่อย่ออีกครั้ง (หุ้นไทยต้องมี .BK ต่อท้าย)")
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

        # ดึงค่าล่าสุดมาแสดงผล
        latest_close = float(data['Close'].iloc[-1])
        prev_close = float(data['Close'].iloc[-2])
        price_change = latest_close - prev_close
        pct_change = (price_change / prev_close) * 100
        latest_rsi = float(data['RSI'].iloc[-1])
        latest_ema_fast = float(data['EMA_Fast'].iloc[-1])
        latest_ema_slow = float(data['EMA_Slow'].iloc[-1])

        # --- ส่วนสรุปผลด้านบน ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("ราคาล่าสุด", f"{latest_close:,.2f}", f"{price_change:+.2f} ({pct_change:+.2f}%)")
        col2.metric(f"RSI ({rsi_len})", f"{latest_rsi:.2f}")
        
        # วิเคราะห์แนวโน้มเบื้องต้น
        if latest_ema_fast > latest_ema_slow:
            trend = "ขาขึ้น (Uptrend) 🟢"
        else:
            trend = "ขาลง (Downtrend) 🔴"
        col3.metric("แนวโน้ม (EMA)", trend)

        # วิเคราะห์โซน RSI
        if latest_rsi >= 70:
            rsi_status = "ซื้อมากเกินไป (Overbought) ⚠️"
        elif latest_rsi <= 30:
            rsi_status = "ขายมากเกินไป (Oversold) 🛒"
        else:
            rsi_status = "ปกติ (Neutral) ⚪"
        col4.metric("สถานะ RSI", rsi_status)

        # --- ส่วนวาดกราฟ Plotly ---
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.05, row_heights=[0.7, 0.3],
            subplot_titles=(f"กราฟราคา {ticker}", "ดัชนี RSI")
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

        # กราฟ RSI
        fig.add_trace(go.Scatter(x=data.index, y=data['RSI'], line=dict(color='purple', width=1.5), name='RSI'), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

        fig.update_layout(height=700, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        # แสดงตารางข้อมูลย้อนหลัง
        with st.expander("ดูตารางข้อมูลราคาย้อนหลัง"):
            st.dataframe(data.tail(20).sort_index(ascending=False))

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
