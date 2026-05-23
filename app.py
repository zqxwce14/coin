import streamlit as st
import pyupbit
import pandas as pd
from datetime import datetime, timedelta
import calendar
import feedparser
import requests

# 페이지 기본 설정
st.set_page_config(page_title="통합 코인 시황 대시보드 V3", layout="wide")

st.title("📊 통합 가상화폐 시황 대시보드 (Seamless V3)")
st.write("💡 가격과 물량은 **10초 단위로 숫자만 스무스하게** 갱신되며, 뉴스는 **10분 주기**로 최신화됩니다.")
st.markdown("---")

# 1. 종합 데이터 수집 함수 (10초 캐싱)
@st.cache_data(ttl=10) 
def get_complete_coin_data():
    try:
        details = []
        sample_tickers = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA", "KRW-DOGE", "KRW-SHIB", "KRW-AVAX", "KRW-DOT"]
        
        for ticker in sample_tickers:
            df = pyupbit.get_ohlcv(ticker, interval="day", count=1)
            if df is not None and not df.empty:
                open_price = df['open'].iloc[0]
                current_price = df['close'].iloc[0]
                value_24h = df['value'].iloc[0]
                
                orderbook = pyupbit.get_orderbook(ticker)
                total_ask_size = orderbook['total_ask_size'] 
                total_bid_size = orderbook['total_bid_size'] 
                
                details.append({
                    "ticker": ticker,
                    "open": open_price,
                    "price": current_price,
                    "volume": value_24h,
                    "ask_size": total_ask_size,
                    "bid_size": total_bid_size
                })
                
        df_details = pd.DataFrame(details)
        top6 = df_details.sort_values(by="volume", ascending=False).head(6)
        return top6
    except Exception as e:
        return None

# 2. 구글 뉴스 크롤링 함수 (600초=10분 캐싱)
@st.cache_data(ttl=600)
def get_google_news(keyword, count=3):
    try:
        url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=5)
        feed = feedparser.parse(response.content)
        
        news_list = []
        for entry in feed.entries[:count]:
            # 기사 작성 시간(UTC)을 한국 시간(KST)으로 변환 후 포맷팅
            time_str = ""
            parsed_time = entry.get('published_parsed')
            if parsed_time:
                timestamp = calendar.timegm(parsed_time)
                dt_utc = datetime.utcfromtimestamp(timestamp)
                dt_kst = dt_utc + timedelta(hours=9)
                time_str = dt_kst.strftime("%m.%d %H:%M") # 월.일 시간:분 표기
                
            title = entry.title if len(entry.title) < 40 else entry.title[:37] + "..."
            news_list.append({"title": title, "link": entry.link, "time": time_str})
            
        if not news_list:
            return [{"title": "검색된 관련 뉴스가 없습니다.", "link": "#", "time": ""}]
        return news_list
    except:
        return [{"title": "뉴스를 불러오는 중 일시적 오류 발생", "link": "#", "time": ""}]


# 💡 3. 핵심 부분: 전체 화면 갱신을 막고, 이 구역 안에서만 데이터를 업데이트 (10초 주기)
@st.fragment(run_every="10s")
def render_dashboard():
    # 데이터 로딩
    coin_data = get_complete_coin_data()
    
    # 4개의 기둥 생성 (프래그먼트 내부에서 렌더링되어 깜빡이지 않음)
    col1, col2, col3, col4 = st.columns(4)
    
    # [Column 1] 거래량 (스트림릿 네이티브 Metric 애니메이션 적용)
    with col1:
        st.subheader("📈 일일 거래량 TOP 6")
        if coin_data is not None:
            for index, row in coin_data.iterrows():
                coin_name = row['ticker'].replace("KRW-", "")
                st.info(f"""
                **{coin_name}** • 거래대금: {row['volume']:,.0f} 원  
                🔴 매도 잔량: {row['ask_size']:,.2f}  
                🔵 매수 잔량: {row['bid_size']:,.2f}
                """)

    # [Column 2] 변동 지표
    with col2:
        st.subheader("🔍 변동 지표 (09:00 기준)")
        if coin_data is not None:
            for index, row in coin_data.iterrows():
                coin_name = row['ticker'].replace("KRW-", "")
                current_price = row['price']
                open_price = row['open']
                change_amt = current_price - open_price
                change_pct = (change_amt / open_price) * 100
                
                if change_amt > 0:
                    color = "#ef4444"
                    sign = "▲"
                elif change_amt < 0:
                    color = "#3b82f6"
                    sign = "▼"
                else:
                    color = "#6b7280"
                    sign = "-"
                    
                st.success(f"**{coin_name} 현재가**: {current_price:,.0f} 원")
                st.markdown(f"""
                <div style='margin-top:-10px; margin-bottom:15px; padding-left:5px;'>
                    <span style='color:{color}; font-weight:bold; font-size:15px;'>
                        {sign} {change_amt:+,.0f}원 ({change_pct:+.2f}%)
                    </span>
                    <span style='color:#9ca3af; font-size:12px; margin-left:5px;'>
                        (시가: {open_price:,.0f}원)
                    </span>
                </div>
                """, unsafe_allow_html=True)

    # [Column 3] 개별 뉴스 (10분 캐싱된 데이터를 가져와 화면 렌더링)
    with col3:
        st.subheader("📰 TOP 6 관련 속보")
        if coin_data is not None:
            target_coins = coin_data.head(3)['ticker'].tolist()
            for ticker in target_coins:
                coin_name = ticker.replace("KRW-", "")
                st.markdown(f"**🔥 {coin_name} 최신 속보**")
                
                coin_news = get_google_news(f"{coin_name} 코인", count=2)
                for news in coin_news:
                    time_badge = f"`{news['time']}` " if news['time'] else ""
                    st.warning(f"{time_badge}[{news['title']}]({news['link']})")

    # [Column 4] 전체 시황 뉴스
    with col4:
        st.subheader("🌍 코인 시황 뉴스")
        st.markdown("**글로벌 암호화폐 주요 동향**")
        
        market_news = get_google_news("가상화폐 시황 OR 비트코인 시황", count=5)
        for news in market_news:
            time_badge = f"`{news['time']}` " if news['time'] else ""
            st.error(f"{time_badge}[{news['title']}]({news['link']})")

# 프래그먼트 실행 (앱이 시작되면 이 함수가 10초마다 자기 자신만 업데이트합니다)
render_dashboard()