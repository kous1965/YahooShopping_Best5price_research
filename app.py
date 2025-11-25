import streamlit as st
import time
import re
import math
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType # ★ここを追加
from selenium.common.exceptions import TimeoutException

# --- 定数設定 ---
SPREADSHEET_NAME = 'YahooShopping_Price_Scraping'
JSON_FILE = 'credentials.json'

# --- ページ設定 ---
st.set_page_config(page_title="Yahoo!ショッピング 最安値取得アプリ", layout="wide")

st.title("🛒 Yahoo!ショッピング 最安値スクレイピング & 転記アプリ")
st.markdown("JANコードのリストを入力し、「処理開始」ボタンを押してください。")

# --- サイドバー：設定 ---
st.sidebar.header("設定")
# クラウド上ではヘッドレス必須のためチェックボックス削除
clear_sheet = st.sidebar.checkbox("実行前にシートをクリアする", value=True)

# --- メインエリア：入力 ---
jan_input = st.text_area("JANコードリスト（1行に1つ入力）", height=200, placeholder="4571697232075\n4904710437681")

# --- ロジック関数 ---
def init_driver():
    options = webdriver.ChromeOptions()
    
    # --- クラウド環境（Streamlit Cloud）用オプション ---
    options.add_argument('--headless') 
    options.add_argument('--no-sandbox') 
    options.add_argument('--disable-dev-shm-usage') 
    options.add_argument('--disable-gpu') 
    options.add_argument('--window-size=1920,1080') 
    
    # 自動操作の検知回避
    options.add_argument('--disable-blink-features=AutomationControlled') 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    
    # Chromiumの場所を指定
    options.binary_location = "/usr/bin/chromium"

    # ★修正ポイント: chrome_type=ChromeType.CHROMIUM を指定してChromium用ドライバを取得させる
    return webdriver.Chrome(
        service=Service(
            ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
        ),
        options=options
    )

def run_scraping(jan_list):
    log_area = st.empty()
    progress_bar = st.progress(0)
    
    try:
        # スプレッドシート接続
        log_area.info(f"Googleスプレッドシート '{SPREADSHEET_NAME}' に接続中...")
        
        # Secretsから鍵情報を取得
        key_dict = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SPREADSHEET_NAME).sheet1
        
        if clear_sheet:
            sheet.clear()
            header = ["JAN", "商品名", "順位", "店舗名", "価格(送料込)", "送料表記", "ポイント%", "ポイント額", "優良配送", "BONUS", "レビュー件数", "注文情報", "商品URL"]
            sheet.append_row(header)
        
        log_area.success("スプレッドシート接続完了。ブラウザを起動します...")
        
        driver = init_driver()
        wait = WebDriverWait(driver, 30)
        
        total_jans = len(jan_list)
        
        for i, jan in enumerate(jan_list):
            jan = jan.strip()
            if not jan: continue
            
            progress = (i) / total_jans
            progress_bar.progress(progress)
            log_area.info(f"[{i+1}/{total_jans}] 処理中 JAN: {jan}")
            
            try:
                # 1. 検索
                driver.get(f"https://shopping.yahoo.co.jp/search?first=1&tab_ex=commerce&fr=shp-prop&p={jan}")
                time.sleep(3)

                # 2. 製品ページ遷移
                try:
                    product_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/products/') and not(contains(@href, 'search'))]")))
                    driver.get(product_link.get_attribute("href"))
                    time.sleep(5)
                except:
                    st.warning(f"JAN: {jan} の製品ページが見つかりませんでした。スキップします。")
                    continue

                # 3. リスト表示へ切り替え
                try:
                    list_view_btn = driver.find_elements(By.XPATH, "//li[contains(@class, 'ChangeView__item--list')]//a | //a[contains(text(), 'リスト')]")
                    if list_view_btn:
                        driver.execute_script("arguments[0].click();", list_view_btn[0])
                        time.sleep(3)
                except:
                    pass

                # 4. 「送料込み」へ切り替え（リトライロジック）
                switched = False
                for attempt in range(3):
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text
                        if "表示価格：送料込みの価格" in body_text or "条件指定：送料込み" in body_text:
                            switched = True
                            break

                        driver.execute_script("""
                            let buttons = document.querySelectorAll('button, div[role="button"], span');
                            for(let b of buttons){
                                if(b.innerText.includes('表示価格') || b.innerText.includes('実質価格') || b.innerText.includes('本体価格')) { b.click(); }
                            }
                        """)
                        time.sleep(1)
                        driver.execute_script("""
                            let options = document.querySelectorAll('li, a, button, label');
                            for (let o of options) {
                                if (o.innerText.includes("送料込みの価格")) { o.click(); }
                            }
                        """)
                        
                        # 確認待機
                        check_start = time.time()
                        while time.time() - check_start < 10:
                            curr_text = driver.find_element(By.TAG_NAME, "body").text
                            if "送料込みの価格" in curr_text and "表示価格：実質価格" not in curr_text:
                                switched = True
                                break
                            items = driver.find_elements(By.XPATH, "//li[contains(@class, 'elItem')] | //div[contains(@class, 'LoopList__item')]")
                            if items:
                                if "送料無料" in items[0].text or "送料0円" in items[0].text:
                                    switched = True
                                    break
                            time.sleep(1)
                        
                        if switched:
                            time.sleep(3)
                            break
                        else:
                            driver.refresh()
                            time.sleep(5)
                    except:
                        driver.refresh()
                        time.sleep(5)
                
                # 5. データ取得
                items = driver.find_elements(By.XPATH, "//li[contains(@class, 'elItem')]")
                if not items: items = driver.find_elements(By.XPATH, "//div[contains(@class, 'LoopList__item')]")
                if not items: items = driver.find_elements(By.XPATH, "//div[contains(@class, 'SearchResultItem')]")
                if not items: items = driver.find_elements(By.XPATH, "//li[descendant::span[contains(text(), '円')] and descendant::a]")
                
                valid_count = 0
                for item in items:
                    if valid_count >= 5: break
                    
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                    except:
                        pass

                    raw_text = item.text
                    search_text = re.sub(r'\s+', ' ', raw_text)
                    clean_text_shipping = re.sub(r'\s+', '', raw_text)
                    html_inner = item.get_attribute('innerHTML')

                    # 送料チェック
                    if "送料無料" in clean_text_shipping or "送料0円" in clean_text_shipping:
                        postage = "送料無料"
                    else:
                        pm = re.search(r'送料([0-9,]+)円', clean_text_shipping)
                        postage = f"送料{pm.group(1)}円" if pm else "送料別"
                    
                    if postage == "送料別": continue

                    # 価格チェック
                    price = "取得失敗"
                    try:
                        pe = item.find_element(By.XPATH, ".//span[contains(@class, 'elPriceValue')]")
                        price = pe.text + "円"
                    except:
                        pm = re.search(r'([0-9,]+)\s*円', search_text)
                        if pm: price = pm.group(1) + "円"
                    
                    if price == "取得失敗": continue

                    # 商品名取得
                    product_name = ""
                    try:
                        name_elem = item.find_element(By.XPATH, ".//div[contains(@class, 'elName')]//a | .//div[contains(@class, 'SearchResultItem__title')]//a | .//p[contains(@class, 'elName')]//a")
                        product_name = name_elem.text.strip()
                    except:
                        pass
                    if not product_name:
                        try:
                            links = item.find_elements(By.TAG_NAME, "a")
                            links_sorted = sorted(links, key=lambda x: len(x.text), reverse=True)
                            for link in links_sorted:
                                txt = link.text.strip()
                                if "円" in txt or "件" in txt or "最安値" in txt: continue
                                product_name = txt
                                break
                        except: pass

                    # 店名チェック
                    shop_name = ""
                    try:
                        se = item.find_element(By.XPATH, ".//*[contains(@class, 'Store') or contains(@class, 'store')]//a")
                        shop_name = se.text.strip()
                        if not shop_name:
                            img = se.find_element(By.TAG_NAME, "img")
                            shop_name = img.get_attribute("alt")
                    except:
                        pass
                    
                    # URL/IDチェック
                    item_url = ""
                    try:
                        item_url = item.find_element(By.TAG_NAME, "a").get_attribute("href")
                    except: pass
                    
                    if not shop_name and item_url and 'store.shopping.yahoo.co.jp' in item_url:
                        try: shop_name = item_url.split('/')[3] + " (ID)"
                        except: shop_name = "店舗名不明"

                    # その他情報
                    is_good = "あり" if ("優良配送" in raw_text) or ("icon_delivery_excellent" in html_inner) else "なし"
                    if is_good == "なし":
                         try:
                             for img in item.find_elements(By.TAG_NAME, "img"):
                                 if "優良配送" in img.get_attribute("alt"):
                                     is_good = "あり"; break
                         except: pass

                    is_bonus = "あり" if "BONUS" in raw_text or "bonus" in html_inner else "なし"
                    
                    pt_match = re.search(r'(\d+)%', clean_text_shipping)
                    pt_pct_str = pt_match.group(1) if pt_match else "0"
                    pt_pct_display = pt_pct_str + "%" if pt_pct_str != "0" else ""
                    
                    try:
                        price_num = int(re.sub(r'[^\d]', '', price))
                        pct_num = int(pt_pct_str)
                        if price_num > 0 and pct_num > 0:
                            val = math.floor(price_num * pct_num / 100)
                            pt_val = f"{val:,}" 
                        else:
                            pt_val = ""
                    except:
                        pt_val = ""

                    rev_cnt = ""
                    rev_match = re.search(r'[（\(]([\d,]+)件[）\)]', raw_text)
                    if rev_match:
                        rev_cnt = rev_match.group(1)
                    else:
                        backup_match = re.search(r'([\d,]+)件', raw_text)
                        if backup_match:
                             num_check = backup_match.group(1).replace(",", "")
                             if num_check.isdigit():
                                 rev_cnt = backup_match.group(1)

                    order_info = "なし"
                    if item_url:
                        try:
                            driver.execute_script(f"window.open('{item_url}', '_blank');")
                            driver.switch_to.window(driver.window_handles[-1])
                            time.sleep(2.0)
                            btext = driver.find_element(By.TAG_NAME, "body").text
                            for phrase in ["以内に注文", "人がカート", "人が検討"]:
                                for line in btext.split('\n'):
                                    if phrase in line:
                                        order_info = line.strip()
                                        break
                                if order_info != "なし": break
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                        except:
                            if len(driver.window_handles) > 1:
                                driver.close()
                                driver.switch_to.window(driver.window_handles[0])

                    row = [jan, product_name, valid_count+1, shop_name, price, postage, pt_pct_display, pt_val, is_good, is_bonus, rev_cnt, order_info, item_url]
                    sheet.append_row(row)
                    valid_count += 1
            
            except Exception as e:
                st.error(f"JAN: {jan} の処理中にエラーが発生しました: {e}")
        
        progress_bar.progress(100)
        log_area.success("すべての処理が完了しました！スプレッドシートを確認してください。")
        st.balloons()

    except Exception as e:
        st.error(f"システムエラー: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()

# --- ボタン ---
if st.button("スクレイピング開始", type="primary"):
    if not jan_input:
        st.warning("JANコードを入力してください。")
    else:
        jan_list = jan_input.split('\n')
        jan_list = [j for j in jan_list if j.strip()]
        run_scraping(jan_list)
