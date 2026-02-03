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

# --- 2. 改良版 SAR 核心演算法 ---
def calculate_modified_sar(df, af_start=0.02, af_limit=0.2):
    # 確保資料為 numpy 格式以提升運算效率
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
            if low[i] <= current_sar:
                if close[i] > current_sar:
                    # --- 改良點：觸碰但未破收盤，維持趨勢但 Reset AF ---
                    new_af = af_start
                else:
                    # 正式跌破，反轉
                    new_trend = -1
                    current_sar = prev_ep
                    new_af = af_start
                    new_ep = low[i]
        else:  # 下降趨勢
            if high[i] >= current_sar:
                if close[i] < current_sar:
                    # --- 改良點：觸碰但未破收盤，維持趨勢但 Reset AF ---
                    new_af = af_start
                else:
                    # 正式突破，反轉
                    new_trend = 1
                    current_sar = prev_ep
                    new_af = af_start
                    new_ep = high[i]

        # 更新極值與 AF 加速
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

# --- 3. UI 介面與樣式 ---
st.markdown("""
    <style>
    .main-title { font-size: 22px !important; font-weight: bold; margin-bottom: 5px; }
    </style>
    <div class="main-title">🚀 改良版 SAR 趨勢追蹤系統</div>
    """, unsafe_allow_html=True)

# 側邊欄輸入
st.sidebar.header("參數設定")
stock_id = st.sidebar.text_input("股票代號", value="2330")
start_date = st.sidebar.date_input("起始日期", value=datetime.now() - timedelta(days=365))
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
        # 股票代號處理 (保留原本邏輯)
        base_id = stock_id.strip().upper().replace(".TW", "").replace(".TWO", "")
        df = yf.download(base_id, start=start_date, end=end_date, progress=False)
        final_id = base_id
        if df.empty:
            df = yf.download(f"{base_id}.TW", start=start_date, end=end_date, progress=False)
            final_id = f"{base_id}.TW"
        if df.empty:
            df = yf.download(f"{base_id}.TWO", start=start_date, end=end_date, progress=False)
            final_id = f"{base_id}.TWO"

        if df.empty:
            st.error(f"❌ 找不到股票代號 '{base_id}'")
            st.session_state.submitted = False
        else:
            # 執行改良版 SAR 計算
            sar_values, trend_values = calculate_modified_sar(df, af_start, af_limit)
            df['SAR'] = sar_values
            df['Trend'] = trend_values
            
            # --- 繪圖區 ---
            fig = go.Figure()

            # 1. 股價 K 線 (收盤價)
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Close'].values.flatten(),
                name='收盤價', line=dict(color='#333333', width=1.5)
            ))

            # 2. SAR 點位 (根據趨勢變色)
            up_trend = df[df['Trend'] == 1]
            down_trend = df[df['Trend'] == -1]

            fig.add_trace(go.Scatter(
                x=up_trend.index, y=up_trend['SAR'],
                name='上升趨勢', mode='markers',
                marker=dict(color='#FF4B4B', size=4)
            ))

            fig.add_trace(go.Scatter(
                x=down_trend.index, y=down_trend['SAR'],
                name='下降趨勢', mode='markers',
                marker=dict(color='#008000', size=4)
            ))

            fig.update_layout(
                xaxis_title=None, yaxis_title='價格',
                hovermode="x unified", template="plotly_white", height=500,
                margin=dict(l=5, r=5, t=50, b=5),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
            )

            st.plotly_chart(fig, use_container_width=True)

            # --- 數據摘要 ---
            st.subheader("📊 趨勢狀態")
            c1, c2, c3 = st.columns(3)
            current_trend = "📈 多頭" if trend_values[-1] == 1 else "📉 空頭"
            c1.metric("目前趨勢", current_trend)
            c2.metric("SAR 點位", f"{sar_values[-1]:.2f}")
            dist = ((df['Close'].values.flatten()[-1] / sar_values[-1]) - 1) * 100
            c3.metric("距支撐/壓力", f"{dist:.2f}%")

else:
    st.info("💡 請設定參數後按「開始分析」。")
