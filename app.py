import streamlit as st
import pyupbit
import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta
import calendar
import feedparser
import requests
import numpy as np
import json
import os
import urllib.parse
import io # [NEW] 최신 Pandas HTML 파싱 호환성을 위한 라이브러리

st.set_page_config(page_title="통합 금융 시황 대시보드 V16", layout="wide")

# ==========================================
# 0. 로컬 파일 저장소 세팅 (기억 상자 확장)
# ==========================================
SAVE_FILE = "my_financial_portfolio.json"

def load_portfolio():
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "coins": [], "coin_prices": {},
        "stocks": [], "stock_prices": {}
    }

def save_portfolio(coins, coin_prices, stocks, stock_prices):
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "coins": coins, "coin_prices": coin_prices,
            "stocks": stocks, "stock_prices": stock_prices
        }, f, indent=4)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio()

# ==========================================
# 1. 상단 메인 메뉴 선택 (주식 vs 코인)
# ==========================================
view_mode = st.radio(
    "📊 보고 싶은 자산 시장을 선택하세요",
    ["🪙 가상화폐 대시보드", "🇰🇷 국내주식 대시보드"],
    horizontal=True
)

# ==========================================
# 2. 실시간 데이터 수집 함수 (1시간 마다 업데이트 ttl=3600)
# ==========================================

# 코인 24시간 거래량 상위 100개 자동 수집
@st.cache_data(ttl=3600)
def get_top_100_coins():
    try:
        markets = pyupbit.get_tickers(fiat="KRW")
        url = "https://api.upbit.com/v1/ticker?markets=" + ",".join(markets)
        headers = {"accept": "application/json"}
        response = requests.get(url, headers=headers)
        data = response.json()
        
        sorted_data = sorted(data, key=lambda x: x['acc_trade_price_24h'], reverse=True)
        top_100_tickers = [item['market'] for item in sorted_data[:100]]
        top_100_names = [m.replace("KRW-", "") for m in top_100_tickers]
        
        return top_100_names, top_100_tickers
    except:
        fallback_names = ["BTC", "ETH", "XRP", "SOL", "DOGE"]
        return fallback_names, [f"KRW-{c}" for c in fallback_names]

# [BUG FIX] 주식 당일 거래량 상위 50개 완벽 수집 로직 수정
@st.cache_data(ttl=3600)
def get_top_50_stocks():
    try:
        url = "https://finance.naver.com/sise/sise_quant.naver"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers)
        res.encoding = 'euc-kr' 
        
        # 최신 pandas 에러 방지를 위해 io.StringIO 사용
        tables = pd.read_html(io.StringIO(res.text))
        
        # '종목명'이 포함된 테이블 찾기
        df_vol = None
        for tbl in tables:
            if '종목명' in tbl.columns:
                df_vol = tbl
                break
                
        if df_vol is None:
            raise Exception("종목명 테이블 찾기 실패")
            
        df_vol = df_vol.dropna(subset=['종목명'])
        top_50_names = df_vol['종목명'].head(50).tolist()
        
        df_krx = fdr.StockListing('KRX')
        stock_options = []
        for name in top_50_names:
            matched = df_krx[df_krx['Name'] == name]
            if not matched.empty:
                # FinanceDataReader 버전별 컬럼명(Code 또는 Symbol) 완벽 호환
                if 'Code' in matched.columns:
                    code = matched['Code'].values[0]
                elif 'Symbol' in matched.columns:
                    code = matched['Symbol'].values[0]
                else:
                    continue
                stock_options.append(f"{name} ({code})")
        
        if len(stock_options) > 10:
            return stock_options, None
        else:
            raise Exception("종목 매칭 수량 부족")
    except Exception as e:
        fallback = ["삼성전자 (005930)", "SK하이닉스 (000660)", "현대차 (005380)", "LG에너지솔루션 (373220)", "NAVER (035420)"]
        return fallback, None

# 시장 데이터 변수 할당
coin_names, coin_tickers = get_top_100_coins()
stock_options, df_top50_data = get_top_50_stocks()

# ==========================================
# 3. 사이드바: 조건 설정
# ==========================================
st.sidebar.header("🎯 내 관심 종목 설정")

saved_coins = st.session_state.portfolio.get("coins", [])
saved_coin_prices = st.session_state.portfolio.get("coin_prices", {})
saved_stocks = st.session_state.portfolio.get("stocks", [])
saved_stock_prices = st.session_state.portfolio.get("stock_prices", {})

temp_coin_prices = {}
temp_stock_prices = {}

if view_mode == "🪙 가상화폐 대시보드":
    valid_saved_coins = [c for c in saved_coins if c in coin_names]
    selected_coins = st.sidebar.multiselect("거래대금 상위 100대 코인 선택", options=coin_names, default=valid_saved_coins)
    selected_tickers = [f"KRW-{name}" for name in selected_coins]

    st.sidebar.markdown("---")
    st.sidebar.subheader("💰 코인 매입단가 입력")
    for ticker in selected_tickers:
        coin_name = ticker.replace("KRW-", "")
        current_val = saved_coin_prices.get(ticker, 0.0)
        temp_coin_prices[ticker] = st.sidebar.number_input(f"{coin_name} 매입가 (원)", min_value=0.0, value=float(current_val), step=100.0)

else: 
    valid_saved_stocks = [s for s in saved_stocks if s in stock_options]
    selected_stocks = st.sidebar.multiselect("당일 거래량 상위 50대 주식 선택", options=stock_options, default=valid_saved_stocks)

    st.sidebar.markdown("---")
    st.sidebar.subheader("💰 주식 매입단가 입력")
    for stock in selected_stocks:
        current_val = saved_stock_prices.get(stock, 0.0)
        temp_stock_prices[stock] = st.sidebar.number_input(f"{stock.split(' ')[0]} 매입가 (원)", min_value=0.0, value=float(current_val), step=500.0)

if st.sidebar.button("💾 적용 및 내 PC에 저장", use_container_width=True):
    if view_mode == "🪙 가상화폐 대시보드":
        st.session_state.portfolio["coins"] = selected_coins
        st.session_state.portfolio["coin_prices"] = temp_coin_prices
    else:
        st.session_state.portfolio["stocks"] = selected_stocks
        st.session_state.portfolio["stock_prices"] = temp_stock_prices
        
    save_portfolio(
        st.session_state.portfolio.get("coins", []),
        st.session_state.portfolio.get("coin_prices", {}),
        st.session_state.portfolio.get("stocks", []),
        st.session_state.portfolio.get("stock_prices", {})
    )
    st.sidebar.success("설정이 성공적으로 저장되었습니다! 🚀")

# ==========================================
# 4. 공통 데이터 처리 로직 및 지표 계산
# ==========================================
def format_price(p):
    return f"{p:,.2f}" if p < 100 else f"{p:,.0f}"

def calculate_technical_indicators(df):
    df['ma5'] = df['Close'].rolling(window=5).mean()
    df['ma20'] = df['Close'].rolling(window=20).mean()
    df['std'] = df['Close'].rolling(window=20).std()
    df['upper_band'] = df['ma20'] + (2 * df['std'])
    df['lower_band'] = df['ma20'] - (2 * df['std'])
    
    delta = df['Close'].diff()
    up = delta.where(delta > 0, 0.0)
    down = -delta.where(delta < 0, 0.0)
    ema_up = up.ewm(alpha=1/14, min_periods=14).mean()
    ema_down = down.ewm(alpha=1/14, min_periods=14).mean()
    rs = ema_up / ema_down
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

@st.cache_data(ttl=10)
def get_stock_dashboard_data(user_stocks):
    if not user_stocks:
        return pd.DataFrame()
    
    details = []
    for stock_str in user_stocks:
        try:
            code = stock_str.split('(')[1].replace(')', '').strip()
            name = stock_str.split('(')[0].strip()
            
            df = fdr.DataReader(code, (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d'))
            if df is not None and not df.empty:
                df = calculate_technical_indicators(df)
                open_price = df['Open'].iloc[-1]
                current_price = df['Close'].iloc[-1]
                volume_24h = df['Volume'].iloc[-1] * current_price 
                
                details.append({
                    "ticker": stock_str, "name": name, "open": open_price, "price": current_price, "volume": volume_24h,
                    "ma5": df['ma5'].iloc[-1], "ma20": df['ma20'].iloc[-1],
                    "upper_band": df['upper_band'].iloc[-1], "lower_band": df['lower_band'].iloc[-1],
                    "rsi": df['rsi'].iloc[-1], "is_top_volume": False
                })
        except:
            continue
            
    df_details = pd.DataFrame(details)
    if not df_details.empty:
        df_details = df_details.sort_values(by="volume", ascending=False)
        df_details.iloc[0, df_details.columns.get_loc('is_top_volume')] = True 
    return df_details

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
# 5. 메인 대시보드 화면 구현 (렌더링)
# ==========================================
@st.fragment(run_every="10s")
def render_combined_dashboard():
    col1, col2, col3, col4 = st.columns(4)
    
    if view_mode == "🪙 가상화폐 대시보드":
        try:
            max_vol_ticker = coin_tickers[0] if coin_tickers else None
            user_coins = [f"KRW-{c}" for c in st.session_state.portfolio.get("coins", [])]
            final_tickers = list(set(user_coins + [max_vol_ticker])) if max_vol_ticker else user_coins
            
            details = []
            for ticker in final_tickers:
                df = pyupbit.get_ohlcv(ticker, interval="day", count=30)
                if df is not None and not df.empty:
                    df.rename(columns={'open':'Open', 'close':'Close'}, inplace=True)
                    df = calculate_technical_indicators(df)
                    orderbook = pyupbit.get_orderbook(ticker)
                    details.append({
                        "ticker": ticker, "name": ticker.replace("KRW-", ""),
                        "open": df['Open'].iloc[-1], "price": df['Close'].iloc[-1], "volume": df['value'].iloc[-1],
                        "ask_size": orderbook['total_ask_size'], "bid_size": orderbook['total_bid_size'],
                        "ma5": df['ma5'].iloc[-1], "ma20": df['ma20'].iloc[-1],
                        "upper_band": df['upper_band'].iloc[-1], "lower_band": df['lower_band'].iloc[-1],
                        "rsi": df['rsi'].iloc[-1], "is_top_volume": (ticker == max_vol_ticker)
                    })
            asset_data = pd.DataFrame(details).sort_values(by="volume", ascending=False)
        except:
            asset_data = pd.DataFrame()
            
    else: # "🇰🇷 국내주식 대시보드"
        user_stocks = st.session_state.portfolio.get("stocks", [])
        asset_data = get_stock_dashboard_data(user_stocks)

    # ----------------------------------------
    # 화면 그리드 배치 출력 시작
    # ----------------------------------------
    if not asset_data.empty:
        # [Column 1] 거래대금 유입 현황 (네이버 검색 하이퍼링크 추가)
        with col1:
            st.subheader("📈 종목별 자금 유입")
            for _, row in asset_data.iterrows():
                
                search_keyword = f"{row['name']} 주식" if view_mode == "🇰🇷 국내주식 대시보드" else f"{row['name']} 코인"
                encoded_query = urllib.parse.quote(search_keyword)
                naver_search_url = f"https://search.naver.com/search.naver?query={encoded_query}"
                
                display_name = f"[{row['name']}]({naver_search_url})"
                
                if view_mode == "🪙 가상화폐 대시보드":
                    sub_info = f"🔴 매도: {row.get('ask_size',0):,.0f} | 🔵 매수: {row.get('bid_size',0):,.0f}"
                else:
                    sub_info = "🏢 국내 주요 거래소 정규 시장 거래 기준"
                    
                if row['is_top_volume']:
                    st.error(f"🔥 **[전체 1위] {display_name}** 🔍 • 자금: {row['volume']:,.0f} 원\n\n{sub_info}")
                else:
                    st.info(f"**{display_name}** 🔍 • 자금: {row['volume']:,.0f} 원\n\n{sub_info}")

        # [Column 2] 분석 지표 및 수익률 계산 카드
        with col2:
            st.subheader("🔍 복합 지표 기반 예측")
            for _, row in asset_data.iterrows():
                change_amt = row['price'] - row['open']
                change_pct = (change_amt / row['open']) * 100
                color = "#ef4444" if change_amt > 0 else "#3b82f6" if change_amt < 0 else "#6b7280"
                sign = "▲" if change_amt > 0 else "▼" if change_amt < 0 else "-"
                
                ma5, ma20, rsi = row['ma5'], row['ma20'], row['rsi']
                upper_band, lower_band = row['upper_band'], row['lower_band']
                
                if ma5 > ma20 and rsi < 70:
                    forecast, signal_text, signal_bg = "1주 내 상승 예상", "매수 추천", "#ef4444"
                    target_price = upper_band if not np.isnan(upper_band) else row['price'] * 1.05
                    target_label = f"목표가 {format_price(target_price)}원"
                else:
                    forecast, signal_text, signal_bg = "1주 내 하락/조정", "매도 추천", "#3b82f6"
                    target_price = lower_band if not np.isnan(lower_band) else row['price'] * 0.95
                    target_label = f"방어선 {format_price(target_price)}원"
                
                price_dict_key = "coin_prices" if view_mode == "🪙 가상화폐 대시보드" else "stock_prices"
                buy_price = st.session_state.portfolio.get(price_dict_key, {}).get(row['ticker'], 0.0)
                
                my_profit_html = ""
                if buy_price > 0:
                    profit_amt = row['price'] - buy_price
                    profit_rate = (profit_amt / buy_price) * 100
                    p_color = "#ef4444" if profit_amt > 0 else "#3b82f6" if profit_amt < 0 else "#6b7280"
                    p_sign = "+" if profit_amt > 0 else ""
                    my_profit_html = f"<div style='background-color: #f1f5f9; padding: 6px; border-radius: 6px; margin-bottom: 8px; border-left: 4px solid {p_color};'><span style='font-size: 12px; color: #475569;'>내 매입가({format_price(buy_price)}원) 대비</span><br><span style='font-size: 14px; font-weight: bold; color: {p_color};'>{p_sign}{format_price(profit_amt)}원 ({p_sign}{profit_rate:.2f}%)</span></div>"
                
                card_html = f"<div style='background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 8px; margin-bottom: 12px;'><div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;'><span style='font-weight: bold; font-size: 15px;'>{row['name']}</span><span style='background-color: {signal_bg}; color: white; font-size: 11px; padding: 4px 8px; border-radius: 4px;'>{signal_text} ({target_label})</span></div><div style='font-size: 11px; color: #64748b; margin-bottom: 8px;'>💡 분석: {forecast} (RSI: {rsi:.1f})</div>{my_profit_html}<div><span style='font-size: 16px; font-weight: bold;'>{format_price(row['price'])} 원</span><span style='color:{color}; font-size: 13px; margin-left: 5px;'>{sign} {format_price(change_amt)} ({change_pct:+.2f}%)</span></div></div>"
                st.markdown(card_html, unsafe_allow_html=True)
    else:
        with col1: st.info("사이드바에서 종목을 선택해 주세요.")

    # [Column 3 & 4] 뉴스 뉴스 영역 
    with col3:
        if view_mode == "🪙 가상화폐 대시보드":
            st.subheader("📰 상장 및 호재 속보")
            q1, q2 = "코인 신규 상장 OR 빗썸 상장 OR 업비트 상장", "코인 호재 OR 파트너십 OR 메인넷"
        else:
            st.subheader("📰 공시 및 주가 호재 속보")
            q1, q2 = "주식 무상증자 OR 최대주주 변경 OR 공급계약 체결", "주식 호재 OR 어닝서프라이즈 OR 특허 취득"
            
        st.caption("최근 3일 이내 주요 시장 이벤트")
        st.markdown("**🚀 주요 인프라 및 공급 공시**")
        for news in get_filtered_news(q1, count=3):
            time_badge = f"`{news['time']}` " if news['time'] else ""
            st.warning(f"{time_badge}[{news['title']}]({news['link']})")
            
        st.markdown("**🔥 시장 상승 견인 주요 호재**")
        for news in get_filtered_news(q2, count=3):
            time_badge = f"`{news['time']}` " if news['time'] else ""
            st.success(f"{time_badge}[{news['title']}]({news['link']})")

    with col4:
        st.subheader("🌍 3일 이내 종합 시황")
        q3 = "가상화폐 시황 OR 비트코인 분석" if view_mode == "🪙 가상화폐 대시보드" else "국내 증시 시황 OR 코스피 코스닥 전망"
        st.caption("글로벌 거시경제 및 금융 시장 동향")
        for news in get_filtered_news(q3, count=6):
            time_badge = f"`{news['time']}` " if news['time'] else ""
            st.error(f"{time_badge}[{news['title']}]({news['link']})")

render_combined_dashboard()
