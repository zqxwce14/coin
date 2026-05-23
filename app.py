import streamlit as st
import pyupbit
import pandas as pd
from datetime import datetime, timedelta
import calendar
import feedparser
import requests

# 페이지 기본 설정
st.set_page_config(page_title="통합 코인 시황 대시보드 V5", layout="wide")

# ---------------------------------------------------------
# [NEW] 사이드바: 내 포트폴리오 매입단가 설정란
# ---------------------------------------------------------
st.sidebar.header("💰 내 평단가 설정")
st.sidebar.write("매입단가를 입력하면 해당 가격 기준으로 AI 추천이 실시간 변경됩니다.")

# 분석 대상 코인 목록
sample_tickers = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA", "KRW-DOGE", "KRW-SHIB", "KRW-AVAX", "KRW-DOT"]

buy_prices = {}
for ticker in sample_tickers:
    coin_name = ticker.replace("KRW-", "")
    # 사이드바에 입력창 생성 (값이 없으면 0.0)
    buy_prices[ticker] = st.sidebar.number_input(f"{coin_name} 매입가 (원)", min_value=0.0, value=0.0, step=100.0)

st.sidebar.markdown("---")
st.sidebar.info("💡 **매매 추천 로직**\n\n• **+5% 이상:** 강력 매도 (익절)\n• **+0% ~ 5%:** 보유 추천\n• **-5% ~ 0%:** 추가 매수 (물타기)\n• **-5% 이하:** 강력 매도 (손절)")

# 메인 화면 타이틀
st.title("📊 통합 가상화폐 시황 대시보드")
st.markdown("---")

# 가격 포맷팅 헬퍼 함수 (소수점 처리)
def format_price(p):
    return f"{p:,.2f}" if p < 100 else f"{p:,.0f}"

# 1. 종합 데이터 수집 함수
@st.cache_data(ttl=10) 
def get_complete_coin_data():
    try:
        details = []
        for ticker in sample_tickers:
            df = pyupbit.get_ohlcv(ticker, interval="day", count=15)
            if df is not None and not df.empty:
                open_price = df['open'].iloc[-1]
                current_price = df['close'].iloc[-1]
                value_24h = df['value'].iloc[-1]
                ma15 = df['close'].mean() # 기본 분석용 15일 이동평균선
                
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
                    "ma15": ma15
                })
                
        df_details = pd.DataFrame(details)
        top6 = df_details.sort_values(by="volume", ascending=False).head(6)
        return top6
    except Exception as e:
        return None

# 2. 구글 뉴스 크롤링 함수
@st.cache_data(ttl=600)
def get_google_news(keyword, count=3):
    try:
        url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        feed = feedparser.parse(response.content)
        
        news_list = []
        for entry in feed.entries[:count]:
            time_str = ""
            parsed_time = entry.get('published_parsed')
            if parsed_time:
                dt_kst = datetime.utcfromtimestamp(calendar.timegm(parsed_time)) + timedelta(hours=9)
                time_str = dt_kst.strftime("%m.%d %H:%M")
            title = entry.title if len(entry.title) < 40 else entry.title[:37] + "..."
            news_list.append({"title": title, "link": entry.link, "time": time_str})
            
        if not news_list:
            return [{"title": "검색된 관련 뉴스가 없습니다.", "link": "#", "time": ""}]
        return news_list
    except:
        return [{"title": "뉴스를 불러오는 중 일시적 오류 발생", "link": "#", "time": ""}]


# 3. 화면 렌더링 프래그먼트 (10초 갱신)
@st.fragment(run_every="10s")
def render_dashboard():
    coin_data = get_complete_coin_data()
    col1, col2, col3, col4 = st.columns(4)
    
    # [Column 1] 거래량
    with col1:
        st.subheader("📈 일일 거래량 TOP 6")
        if coin_data is not None:
            for index, row in coin_data.iterrows():
                coin_name = row['ticker'].replace("KRW-", "")
                st.info(f"**{coin_name}** • 거래대금: {row['volume']:,.0f} 원\n\n🔴 매도 잔량: {row['ask_size']:,.2f}\n\n🔵 매수 잔량: {row['bid_size']:,.2f}")

    # [Column 2] 변동 지표 및 내 평단가 기반 추천
    with col2:
        st.subheader("🔍 변동 지표 (09:00 기준)")
        if coin_data is not None:
            for index, row in coin_data.iterrows():
                ticker = row['ticker']
                coin_name = ticker.replace("KRW-", "")
                current_price = row['price']
                open_price = row['open']
                
                # 변동률 계산
                change_amt = current_price - open_price
                change_pct = (change_amt / open_price) * 100
                color = "#ef4444" if change_amt > 0 else "#3b82f6" if change_amt < 0 else "#6b7280"
                sign = "▲" if change_amt > 0 else "▼" if change_amt < 0 else "-"
                
                # ---------------------------------------------------------
                # [핵심] 사이드바에서 입력한 매입가 가져오기
                # ---------------------------------------------------------
                buy_price = buy_prices.get(ticker, 0.0)
                
                if buy_price > 0.0:
                    # 1. 사용자가 매입가를 입력했을 때 (내 포트폴리오 기준)
                    profit_rate = ((current_price - buy_price) / buy_price) * 100
                    
                    if profit_rate >= 5.0:
                        signal_text = "강력 매도"
                        target_info = f"수익달성 +{profit_rate:.1f}%"
                        signal_bg = "#ef4444" # 빨강
                    elif profit_rate > 0.0:
                        signal_text = "보유 추천"
                        target_info = f"목표가 {format_price(buy_price * 1.05)}원"
                        signal_bg = "#f97316" # 주황
                    elif profit_rate <= -5.0:
                        signal_text = "강력 매도"
                        target_info = f"손절도달 {profit_rate:.1f}%"
                        signal_bg = "#3b82f6" # 파랑
                    else:
                        signal_text = "추가 매수"
                        target_info = f"손절가 {format_price(buy_price * 0.95)}원"
                        signal_bg = "#10b981" # 초록
                else:
                    # 2. 매입가를 입력하지 않았을 때 (기존 15일 이평선 기준)
                    ma15 = row['ma15']
                    if current_price > ma15:
                        signal_text = "매수 추천"
                        target_info = f"익절가 {format_price(current_price * 1.05)}원"
                        signal_bg = "#ef4444"
                    else:
                        signal_text = "매도 추천"
                        target_info = f"손절가 {format_price(current_price * 0.95)}원"
                        signal_bg = "#3b82f6"
                
                # UI 출력부 (배지 및 변동률)
                st.markdown(f"""
                <div style='background-color: #e6f4ea; border: 1px solid #ceead6; padding: 12px; border-radius: 8px; margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center;'>
                    <span style='color: #0d652d; font-weight: bold; font-size: 15px;'>{coin_name} 현재가: {format_price(current_price)} 원</span>
                    <span style='background-color: {signal_bg}; color: white; font-size: 12px; font-weight: bold; padding: 4px 8px; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);'>
                        {signal_text} ({target_info})
                    </span>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown(f"""
                <div style='margin-top:-5px; margin-bottom:15px; padding-left:5px;'>
                    <span style='color:{color}; font-weight:bold; font-size:15px;'>
                        {sign} {format_price(change_amt)}원 ({change_pct:+.2f}%)
                    </span>
                    <span style='color:#9ca3af; font-size:12px; margin-left:5px;'>(시가: {format_price(open_price)}원)</span>
                </div>
                """, unsafe_allow_html=True)

    # [Column 3, 4] 뉴스 연동부 (기존과 동일)
    with col3:
        st.subheader("📰 TOP 6 관련 속보")
        if coin_data is not None:
            for ticker in coin_data.head(3)['ticker'].tolist():
                coin_name = ticker.replace("KRW-", "")
                st.markdown(f"**🔥 {coin_name} 최신 속보**")
                for news in get_google_news(f"{coin_name} 코인", count=2):
                    time_badge = f"`{news['time']}` " if news['time'] else ""
                    st.warning(f"{time_badge}[{news['title']}]({news['link']})")

    with col4:
        st.subheader("🌍 코인 시황 뉴스")
        st.markdown("**글로벌 암호화폐 주요 동향**")
        for news in get_google_news("가상화폐 시황 OR 비트코인 시황", count=5):
            time_badge = f"`{news['time']}` " if news['time'] else ""
            st.error(f"{time_badge}[{news['title']}]({news['link']})")

render_dashboard()
