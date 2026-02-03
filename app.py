import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 狀態初始化與配置 ---
if "submitted" not in st.session_state:
    st.session_state.submitted = False

st.set_page_config(
    page_title="改良版 SAR 分析工具", 
    layout="wide",
    initial_sidebar_state="collapsed" if st.session_state.submitted else "expanded"
)

# --- 2. 改良版 SAR 核心演算法 (邏輯不變，確保有抓取 High/Low) ---
def calculate_modified_sar(df, af_start=0.02, af_limit=0.2):
    # 這裡明確抓取 High, Low, Close 進行運算
    high = df['High'].values.flatten()
    low = df['Low'].values.flatten()
    close = df['Close'].values.flatten()
    size = len(df)
    
    sar = np.zeros(size)
    trend = np.ones(size)  # 1: 上升, -1: 下降
    af = np.full(size, af_start)
    ep = np.zeros(size)

    # 初始值設定
    trend[0] = 1 if close[min(1, size-1)] > close[0] else -1
    sar[0] = low[0] if trend[0] == 1 else high[0]
    ep[0] = high[0] if trend[0] == 1 else low[0]

    for i in range(1, size):
        prev_sar = sar[i-1]
        prev_trend = trend[i-1]
        prev_af = af[i-1]
        prev_ep = ep[i-1]

        # 基礎 SAR 計算
        current_sar = prev_sar + prev_af * (prev_ep - prev_sar)
        
        new_trend = prev_trend
        new_af = prev_af
        new_ep = prev_ep

        if prev_trend == 1:  # 上升趨勢
            if low[i] <= current_sar: # 判斷最低價是否觸碰
                if close[i] > current_sar:
                    # 改良點：觸碰但收盤有守住 -> Reset AF
                    new_af = af_start
                else:
                    # 實體跌破 -> 反轉
                    new_trend = -1
                    current_sar = prev_ep
                    new_af = af_start
                    new_ep = low[i]
        else:  # 下降趨勢
            if high[i] >= current_sar: # 判斷最高價是否觸碰
                if close[i] < current_sar:
                    # 改良點：觸碰但收盤沒過 -> Reset AF
                    new_af = af_start
                else:
                    # 實體突破 -> 反轉
                    new_trend = 1
                    current_sar = prev_ep
                    new_af = af_start
                    new_ep = high[i]

        # 更新極值 (EP) 與 AF
        if new_trend == 1:
            if high[i] > new_ep:
                new_ep = high[i]
                new_af = min(af_limit, new_af + af_start)
        else:
            if low[i] < new_ep:
                new_ep = low[i]
                new_af = min(af_limit, new_af + af_start)

        sar[i] = current_sar
        trend[i] = new_trend
        af[i] = new_af
        ep[i] = new_ep

    return sar, trend

# --- 3. UI 介面 ---
st.markdown("""
    <style>
    .main-title { font-size: 22px !important; font-weight: bold; margin-bottom: 5px; }
    </style>
    <div class="main-title">🚀 改良版 SAR 趨勢追蹤系統 (K線版)</div>
    """, unsafe_allow_html=True)

st.sidebar.header("參數設定")
stock_id = st.sidebar.text_input("股票代號", value="2330")
start_date = st.sidebar.date_input("起始日期", value=datetime.now() - timedelta(days=200)) # 預設縮短天數以便看清K線
end_date = st.sidebar.date_input("結束日期", value=datetime.now())

st.sidebar.markdown("---")
af_start = st.sidebar.slider("AF 起始值", 0.01, 0.1, 0.02, step=0.01)
af_limit = st.sidebar.slider("AF 極限值", 0.1, 0.5, 0.2, step=0.05)

if st.sidebar.button("開始分析", use_container_width=True):
    st.session_state.submitted = True
    st.rerun()

# --- 4. 核心執行區 ---
if st.session_state.submitted:
    with st.spinner('計算趨勢中...'):
        base_id = stock_id.strip().upper().replace(".TW", "").replace(".TWO", "")
        df = yf.download(base_id, start=start_date, end=end_date, progress=False)
        
        # 簡易容錯重試
        if df.empty:
            df = yf.download(f"{base_id}.TW", start=start_date, end=end_date, progress=False)
        if df.empty:
            df = yf.download(f"{base_id}.TWO", start=start_date, end=end_date, progress=False)

        if df.empty:
            st.error(f"❌ 找不到股票代號 '{base_id}'")
            st.session_state.submitted = False
        else:
            # 確保欄位單純化 (去除 MultiIndex)
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
            
            # 執行計算
            sar_values, trend_values = calculate_modified_sar(df, af_start, af_limit)
            df['SAR'] = sar_values
            df['Trend'] = trend_values
            
            # --- 重點修改：繪製 K 線圖 ---
            fig = go.Figure()

            # 1. 繪製 Candlestick (開高低收)
            # 台股習慣：漲是紅 (increasing), 跌是綠 (decreasing)
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='K線',
                increasing_line_color='#FF4B4B',  # 紅色
                decreasing_line_color='#008000'   # 綠色
            ))

            # 2. SAR 點位
            up_trend = df[df['Trend'] == 1]
            down_trend = df[df['Trend'] == -1]

            fig.add_trace(go.Scatter(
                x=up_trend.index, y=up_trend['SAR'],
                name='多頭支撐', mode='markers',
                marker=dict(color='#FF4B4B', size=4, symbol='circle') # 紅點
            ))

            fig.add_trace(go.Scatter(
                x=down_trend.index, y=down_trend['SAR'],
                name='空頭壓力', mode='markers',
                marker=dict(color='#008000', size=4, symbol='circle') # 綠點
            ))

            # 優化圖表顯示
            fig.update_layout(
                xaxis_title=None, yaxis_title='價格',
                xaxis_rangeslider_visible=False, # 隱藏下方原本的縮放條，讓畫面更乾淨
                hovermode="x unified", 
                template="plotly_white", 
                height=600,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
            )

            st.plotly_chart(fig, use_container_width=True)

            # --- 數據摘要 ---
            st.subheader("📊 最新狀態")
            curr_close = df['Close'].iloc[-1]
            curr_sar = sar_values[-1]
            
            c1, c2, c3 = st.columns(3)
            current_trend = "📈 看漲 (多頭)" if trend_values[-1] == 1 else "📉 看跌 (空頭)"
            c1.metric("目前趨勢", current_trend)
            
            c2.metric("收盤價", f"{curr_close:.2f}")
            
            # 計算距離
            dist_val = curr_close - curr_sar
            dist_pct = (dist_val / curr_close) * 100
            label = "支撐" if trend_values[-1] == 1 else "壓力"
            c3.metric(f"SAR {label}位置", f"{curr_sar:.2f}", f"{dist_pct:.2f}% (距離)")

else:
    st.info("💡 請設定參數後按「開始分析」。")
