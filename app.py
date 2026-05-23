import streamlit as st
import pyupbit
import pandas as pd
from datetime import datetime, timedelta
import calendar
import feedparser
import requests
import numpy as np

st.set_page_config(page_title="통합 코인 시황 대시보드 V7", layout="wide")

# ==========================================
# 1. 사이드바: 관심 종목 무제한 선택 및 매입단가 설정
# ==========================================
st.sidebar.header("🎯 내 관심 종목 설정")

TOP_30_TICKERS = [
    "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA", "KRW-DOGE", "KRW-SHIB", "KRW-AVAX", 
    "KRW-DOT", "KRW-LINK", "KRW-MATIC", "KRW-NEAR", "KRW-BCH", "KRW-ETC", "KRW-STX", "KRW-SUI", 
    "KRW-APT", "KRW-ARB", "KRW-OP", "KRW-SEI", "KRW-MINA", "KRW-BLUR", "KRW-MASK", "KRW-SAND", 
    "KRW-MANA", "KRW-ENJ", "KRW-CHZ", "KRW-AAVE", "KRW-THETA", "KRW-WAVES"
]

ticker_names = [t.replace("KRW-", "") for t in TOP_30_TICKERS]
# 선택 수량 제한(max_selections) 해제
selected_names = st.sidebar.multiselect(
    "관심 코인을 선택하세요", 
    options=ticker_names, 
    default=["XRP", "SOL", "ADA", "DOGE"] 
)

selected_tickers = [f"KRW-{name}" for name in selected_names]

st.sidebar.markdown("---")
st.sidebar.subheader("💰 매입단가 입력")
st.sidebar.caption("미입력(0) 시 현재가 기준으로 추천합니다.")

buy_prices = {}
for ticker in selected_tickers:
    coin_name = ticker.replace("KRW-", "")
    buy_prices[ticker] = st.sidebar.number_input(f"{coin_name} 매입가 (원)", min_value=0.0, value=0.0, step=100.0)

# ==========================================
# 2. 데이터 수집 및 복합 기술적 지표 계산 로직
# ==========================================
def format_price(p):
    return f"{p:,.2f}" if p < 100 else f"{p:,.0f}"

@st.cache_data(ttl=10) 
def get_dashboard_data(user_tickers):
    try:
        top_candidates = TOP_30_TICKERS[:10] 
        max_vol_ticker = None
        max_vol = 0
        
        # 거래대금 1위 찾기
        for t in top_candidates:
            df_temp = pyupbit.get_ohlcv(t, interval="day", count=1)
            if df_temp is not None and not df_temp.empty:
                if df_temp['value'].iloc[0] > max_vol:
                    max_vol = df_temp['value'].iloc[0]
                    max_vol_ticker = t
        
        final_tickers = list(set(user_tickers + [max_vol_ticker]))
        details = []
        
        for ticker in final_tickers:
            # MA20과 RSI 계산을 위해 30일치 데이터 수집
            df = pyupbit.get_ohlcv(ticker, interval="day", count=30)
            if df is not None and not df.empty:
                open_price = df['open'].iloc[-1]
                current_price = df['close'].iloc[-1]
                value_24h = df['value'].iloc[-1]
                
                # 복합 지표 계산 (MA5, MA20)
                df['ma5'] = df['close'].rolling(window=5).mean()
                df['ma20'] = df['close'].rolling(window=20).mean()
                
                # 복합 지표 계산 (RSI 14일)
                delta = df['close'].diff()
                up = delta.where(delta > 0, 0.0)
                down = -delta.where(delta < 0, 0.0)
                ema_up = up.ewm(alpha=1/14, min_periods=14).mean()
                ema_down = down.ewm(alpha=1/14, min_periods=14).mean()
                rs = ema_up / ema_down
                df['rsi'] = 100 - (100 / (1 + rs))
                
                ma5 = df['ma5'].iloc[-1]
                ma20 = df['ma20'].iloc[-1]
                rsi = df['rsi'].iloc[-1]
                
                orderbook = pyupbit.get_orderbook(ticker)
                total_ask_size = orderbook['total_ask_size'] 
                total_bid_size = orderbook['total_bid_size'] 
                
                details.append({
                    "ticker": ticker,
                    "open": open_price,
                    "price": current_price,
                    "volume": value_24h,
                    "ask_size": total_ask_size,
                    "bid_size": total_bid_size,
                    "ma5": ma5,
                    "ma20": ma20,
                    "rsi": rsi,
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
# 3. 메인 대시보드 렌더링 (타이틀 삭제)
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

        # [Column 2] 분석 지표 및 1주일 예측 매매 추천
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
                
                # 지표 불러오기
                ma5 = row['ma5']
                ma20 = row['ma20']
                rsi = row['rsi']
                buy_price = buy_prices.get(ticker, 0.0)
                
                # 기준가 설정 (매입가가 있으면 매입가, 없으면 현재가)
                base_price = buy_price if buy_price > 0 else current_price
                
                # 1주일 방향성 예측 로직 (MA정배열 + RSI 과열여부)
                if ma5 > ma20 and rsi < 70:
                    forecast = "1주 내 상승 예상"
                    signal_text = "매수 추천"
                    target_price = base_price * 1.10 # 익절가 +10% 
                    target_label = f"익절가 {format_price(target_price)}원"
                    signal_bg = "#ef4444" # 빨강
                else:
                    forecast = "1주 내 하락/조정"
                    signal_text = "매도 추천"
                    target_price = base_price * 0.95 # 손절가 -5%
                    target_label = f"손절가 {format_price(target_price)}원"
                    signal_bg = "#3b82f6" # 파랑
                
                # 카드 UI
                st.markdown(f"""
                <div style='background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 8px; margin-bottom: 8px;'>
                    <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;'>
                        <span style='font-weight: bold; font-size: 15px;'>{coin_name}</span>
                        <span style='background-color: {signal_bg}; color: white; font-size: 11px; padding: 4px 8px; border-radius: 4px;'>
                            {signal_text} ({target_label})
                        </span>
                    </div>
                    <div style='font-size: 11px; color: #64748b; margin-bottom: 5px;'>💡 분석: {forecast} (RSI: {rsi:.1f})</div>
                    <span style='font-size: 16px; font-weight: bold;'>{format_price(current_price)} 원</span>
                    <span style='color:{color}; font-size: 13px; margin-left: 5px;'>{sign} {format_price(change_amt)} ({change_pct:+.2f}%)</span>
                </div>
                """, unsafe_allow_html=True)

    # [Column 3] 호재 및 신규 상장 속보 (최근 3일)
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

    # [Column 4] 시황 뉴스 (최근 3일)
    with col4:
        st.subheader("🌍 3일 이내 시황 뉴스")
        st.caption("글로벌 암호화폐 시장 동향")
        
        for news in get_filtered_news("가상화폐 시황 OR 비트코인 분석", count=6):
            time_badge = f"`{news['time']}` " if news['time'] else ""
            st.error(f"{time_badge}[{news['title']}]({news['link']})")

render_dashboard()
