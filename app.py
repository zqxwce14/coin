import streamlit as st
import pyupbit
import pandas as pd
from datetime import datetime, timedelta
import calendar
import feedparser
import requests
import numpy as np
import textwrap

st.set_page_config(page_title="통합 코인 시황 대시보드 V11", layout="wide")

# ==========================================
# 0. 세션 상태 초기화
# ==========================================
if 'confirmed_buy_prices' not in st.session_state:
    st.session_state.confirmed_buy_prices = {}

# ==========================================
# 1. 사이드바: 관심 종목 선택 및 매입단가 입력
# ==========================================
st.sidebar.header("🎯 내 관심 종목 설정")

TOP_30_TICKERS = [
    "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA", "KRW-DOGE", "KRW-SHIB", "KRW-AVAX", 
    "KRW-DOT", "KRW-LINK", "KRW-MATIC", "KRW-NEAR", "KRW-BCH", "KRW-ETC", "KRW-STX", "KRW-SUI", 
    "KRW-APT", "KRW-ARB", "KRW-OP", "KRW-SEI", "KRW-MINA", "KRW-BLUR", "KRW-MASK", "KRW-SAND", 
    "KRW-MANA", "KRW-ENJ", "KRW-CHZ", "KRW-AAVE", "KRW-THETA", "KRW-WAVES"
]

ticker_names = [t.replace("KRW-", "") for t in TOP_30_TICKERS]

# [수정된 부분] default 값을 빈 리스트([])로 변경하여 처음엔 아무것도 안 뜨게 만듦
selected_names = st.sidebar.multiselect(
    "관심 코인을 선택하세요", 
    options=ticker_names, 
    default=[] 
)

selected_tickers = [f"KRW-{name}" for name in selected_names]

st.sidebar.markdown("---")
st.sidebar.subheader("💰 매입단가 입력")
st.sidebar.caption("미입력(0) 시 현재가 기준으로 추천합니다.")

temp_buy_prices = {}
for ticker in selected_tickers:
    coin_name = ticker.replace("KRW-", "")
    current_val = st.session_state.confirmed_buy_prices.get(ticker, 0.0)
    temp_buy_prices[ticker] = st.sidebar.number_input(f"{coin_name} 매입가 (원)", min_value=0.0, value=current_val, step=100.0)

if st.sidebar.button("✅ 적용 확인", use_container_width=True):
    st.session_state.confirmed_buy_prices = temp_buy_prices.copy()
    st.sidebar.success("매입단가가 지표에 반영되었습니다!")

# ==========================================
# 2. 데이터 수집 및 복합 기술적 지표 계산
# ==========================================
def format_price(p):
    return f"{p:,.2f}" if p < 100 else f"{p:,.0f}"

@st.cache_data(ttl=10) 
def get_dashboard_data(user_tickers):
    try:
        top_candidates = TOP_30_TICKERS[:10] 
        max_vol_ticker = None
        max_vol = 0
        
        for t in top_candidates:
            df_temp = pyupbit.get_ohlcv(t, interval="day", count=1)
            if df_temp is not None and not df_temp.empty:
                if df_temp['value'].iloc[0] > max_vol:
                    max_vol = df_temp['value'].iloc[0]
                    max_vol_ticker = t
        
        final_tickers = list(set(user_tickers + [max_vol_ticker]))
        details = []
        
        for ticker in final_tickers:
            df = pyupbit.get_ohlcv(ticker, interval="day", count=30)
            if df is not None and not df.empty:
                open_price = df['open'].iloc[-1]
                current_price = df['close'].iloc[-1]
                value_24h = df['value'].iloc[-1]
                
                # MA 계산
                df['ma5'] = df['close'].rolling(window=5).mean()
                df['ma20'] = df['close'].rolling(window=20).mean()
                
                # 볼린저 밴드 계산 (20일선 기준)
                df['std'] = df['close'].rolling(window=20).std()
                df['upper_band'] = df['ma20'] + (2 * df['std'])
                df['lower_band'] = df['ma20'] - (2 * df['std'])
                
                # RSI 계산
                delta = df['close'].diff()
                up = delta.where(delta > 0, 0.0)
                down = -delta.where(delta < 0, 0.0)
                ema_up = up.ewm(alpha=1/14, min_periods=14).mean()
                ema_down = down.ewm(alpha=1/14, min_periods=14).mean()
                rs = ema_up / ema_down
                df['rsi'] = 100 - (100 / (1 + rs))
                
                orderbook = pyupbit.get_orderbook(ticker)
                
                details.append({
                    "ticker": ticker,
                    "open": open_price,
                    "price": current_price,
                    "volume": value_24h,
                    "ask_size": orderbook['total_ask_size'],
                    "bid_size": orderbook['total_bid_size'],
                    "ma5": df['ma5'].iloc[-1],
                    "ma20": df['ma20'].iloc[-1],
                    "upper_band": df['upper_band'].iloc[-1],
                    "lower_band": df['lower_band'].iloc[-1],
                    "rsi": df['rsi'].iloc[-1],
                    "is_top_volume": (ticker == max_vol_ticker)
                })
                
        df_details = pd.DataFrame(details)
        return df_details.sort_values(by="volume", ascending=False)
    except Exception as e:
        return None

@st.cache_data(ttl=600)
def get_filtered_news(query, count=4):
    try:
        url = f"https://news.google.com/rss/search?q={query} when:3d&hl=ko&gl=KR&ceid=KR:ko"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        feed = feedparser.parse(response.content)
        news_list = []
        for entry in feed.entries[:count]:
            time_str = ""
            parsed_time = entry.get('published_parsed')
            if parsed_time:
                dt_kst = datetime.utcfromtimestamp(calendar.timegm(parsed_time)) + timedelta(hours=9)
                time_str = dt_kst.strftime("%m.%d")
            title = entry.title if len(entry.title) < 42 else entry.title[:39] + "..."
            news_list.append({"title": title, "link": entry.link, "time": time_str})
        if not news_list:
            return [{"title": "최근 3일 내 관련 기사가 없습니다.", "link": "#", "time": ""}]
        return news_list
    except:
        return [{"title": "뉴스 수집 오류", "link": "#", "time": ""}]

# ==========================================
# 3. 메인 대시보드 렌더링
# ==========================================

@st.fragment(run_every="10s")
def render_dashboard():
    coin_data = get_dashboard_data(selected_tickers)
    col1, col2, col3, col4 = st.columns(4)
    
    if coin_data is not None:
        # [Column 1] 거래량 현황
        with col1:
            st.subheader("📈 종목별 자금 유입")
            for index, row in coin_data.iterrows():
                coin_name = row['ticker'].replace("KRW-", "")
                if row['is_top_volume']:
                    st.error(f"🔥 **[전체 1위] {coin_name}** • 자금: {row['volume']:,.0f} 원\n\n🔴 매도: {row['ask_size']:,.0f} | 🔵 매수: {row['bid_size']:,.0f}")
                else:
                    st.info(f"**{coin_name}** • 자금: {row['volume']:,.0f} 원\n\n🔴 매도: {row['ask_size']:,.0f} | 🔵 매수: {row['bid_size']:,.0f}")

        # [Column 2] 분석 지표 및 1주일 예측
        with col2:
            st.subheader("🔍 복합 지표 기반 예측")
            for index, row in coin_data.iterrows():
                ticker = row['ticker']
                coin_name = ticker.replace("KRW-", "")
                current_price = row['price']
                open_price = row['open']
                
                change_amt = current_price - open_price
                change_pct = (change_amt / open_price) * 100
                color = "#ef4444" if change_amt > 0 else "#3b82f6" if change_amt < 0 else "#6b7280"
                sign = "▲" if change_amt > 0 else "▼" if change_amt < 0 else "-"
                
                ma5, ma20, rsi = row['ma5'], row['ma20'], row['rsi']
                upper_band, lower_band = row['upper_band'], row['lower_band']
                
                if ma5 > ma20 and rsi < 70:
                    forecast = "1주 내 상승 예상"
                    signal_text = "매수 추천"
                    target_price = upper_band if not np.isnan(upper_band) else current_price * 1.05
                    target_label = f"목표가 {format_price(target_price)}원"
                    signal_bg = "#ef4444"
                else:
                    forecast = "1주 내 하락/조정"
                    signal_text = "매도 추천"
                    target_price = lower_band if not np.isnan(lower_band) else current_price * 0.95
                    target_label = f"방어선 {format_price(target_price)}원"
                    signal_bg = "#3b82f6"
                
                buy_price = st.session_state.confirmed_buy_prices.get(ticker, 0.0)
                my_profit_html = ""
                if buy_price > 0:
                    profit_amt = current_price - buy_price
                    profit_rate = (profit_amt / buy_price) * 100
                    p_color = "#ef4444" if profit_amt > 0 else "#3b82f6" if profit_amt < 0 else "#6b7280"
                    p_sign = "+" if profit_amt > 0 else ""
                    
                    my_profit_html = f"<div style='background-color: #f1f5f9; padding: 6px; border-radius: 6px; margin-bottom: 8px; border-left: 4px solid {p_color};'><span style='font-size: 12px; color: #475569;'>내 매입가({format_price(buy_price)}원) 대비</span><br><span style='font-size: 14px; font-weight: bold; color: {p_color};'>💰 {p_sign}{format_price(profit_amt)}원 ({p_sign}{profit_rate:.2f}%)</span></div>"
                
                card_html = f"<div style='background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 8px; margin-bottom: 12px;'><div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;'><span style='font-weight: bold; font-size: 15px;'>{coin_name}</span><span style='background-color: {signal_bg}; color: white; font-size: 11px; padding: 4px 8px; border-radius: 4px;'>{signal_text} ({target_label})</span></div><div style='font-size: 11px; color: #64748b; margin-bottom: 8px;'>💡 분석: {forecast} (RSI: {rsi:.1f})</div>{my_profit_html}<div><span style='font-size: 16px; font-weight: bold;'>{format_price(current_price)} 원</span><span style='color:{color}; font-size: 13px; margin-left: 5px;'>{sign} {format_price(change_amt)} ({change_pct:+.2f}%)</span></div></div>"
                
                st.markdown(card_html, unsafe_allow_html=True)

    # [Column 3] 호재 및 신규 상장 속보
    with col3:
        st.subheader("📰 상장 및 호재 속보")
        st.caption("최근 3일 이내 주요 시장 호재")
        st.markdown("**🚀 거래소 신규 상장**")
        for news in get_filtered_news("코인 신규 상장 OR 빗썸 상장 OR 업비트 상장", count=3):
            time_badge = f"`{news['time']}` " if news['time'] else ""
            st.warning(f"{time_badge}[{news['title']}]({news['link']})")
        st.markdown("**🔥 상승 예상 주요 호재**")
        for news in get_filtered_news("코인 호재 OR 파트너십 OR 메인넷", count=3):
            time_badge = f"`{news['time']}` " if news['time'] else ""
            st.success(f"{time_badge}[{news['title']}]({news['link']})")

    # [Column 4] 시황 뉴스
    with col4:
        st.subheader("🌍 3일 이내 시황 뉴스")
        st.caption("글로벌 암호화폐 시장 동향")
        for news in get_filtered_news("가상화폐 시황 OR 비트코인 분석", count=6):
            time_badge = f"`{news['time']}` " if news['time'] else ""
            st.error(f"{time_badge}[{news['title']}]({news['link']})")

render_dashboard()
