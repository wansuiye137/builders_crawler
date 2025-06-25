import os
import csv
import re
import time
import random
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# 州与市场对应关系
STATE_MARKETS = {
    "AL": ["BRM", "PEN", "HUN", "TUS"],
    "AZ": ["PHO", "TUC"],
    "CA": ["CCA", "INL", "LSA", "ORA", "DER", "SAC", "SDO", "SFR", "SFM"],
    "CO": ["COS", "DEN"],
    "DE": ["NCC", "SUX"],
    "FL": ["FTL", "PEN", "JAX", "MIA", "FTM", "OCA", "ORL", "PLM", "SAR", "SPA", "TAM", "TRE"],
    "IL": ["CHI"],
    "MD": ["CMD", "EAS", "MDC", "SMD"],
    "MN": ["MIN", "RCT"],
    "NC": ["CHA", "RAL", "WLM", "WSN"],
    "NJ": ["CNJ"],
    "NV": ["LVE", "REN"],
    "NY": ["NYS"],
    "PA": ["ADM", "PHI"],
    "SC": ["CHR", "CHA", "CLM", "GRN", "HHB", "MYB"],
    "TX": ["AUS", "CPC", "DAL", "HOU", "SAN", "TEP", "THC"],
    "VA": ["RVA", "VDC", "WIL"],
    "GA": ["ATL", "MID", "SAV"],
    "WA": ["INW", "SEA", "VAN"],
    "OR": ["COR", "POT", "WMV"],
    "TN": ["CHT", "NAS"],
    "IN": ["INP", "NWI"],
    "UT": ["SLC", "STG"],
    "WV": ["BER", "JFC"],
    "ID": ["BOI", "INW"],
    "WI": ["MAD"],
    "OK": ["OKL", "STW", "TUL"],
    "AR": ["FTS", "JON", "LIT", "NWA"],
    "KS": ["KCK"],
    "MO": ["KCM"]
}


def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--headless")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=3")

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15"
    ]
    options.add_argument(f"user-agent={random.choice(user_agents)}")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(120)
    return driver


#市场页面获取所有房源链接
def get_links_for_market(driver, state_code, market_code):
    base_url = "https://www.lennar.com"
    #网址结构
    url = f"{base_url}/find-a-home?state={state_code}&market={market_code}"

    print(f"正在访问市场页面: {url}")

    try:
        driver.get(url)
    except Exception as e:
        print(f"  页面加载超时: {str(e)}")
        return []

    # 处理Cookie弹窗
    try:
        accept_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
        accept_button.click()
        print("  已接受Cookie政策")
        time.sleep(1)
    except Exception as e:
        print(f"  未找到Cookie弹窗: {str(e)}")

    # 点击"Load more homes"直到没有更多内容
    click_count = 0
    max_clicks = 20

    while click_count < max_clicks:
        try:
            button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Load more homes']")))

            # 滚动到按钮位置
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
            time.sleep(1.5)

            # 点击
            driver.execute_script("arguments[0].click();", button)
            click_count += 1
            print(f"  点击加载更多按钮 ({click_count}次)")

            # 随机等待时间
            time.sleep(random.uniform(2.0, 4.0))

        except Exception as e:
            print(f"  没有更多内容或加载超时: {str(e)}")
            break

    print(f"  完成加载，共点击 {click_count} 次")

    # 获取完整页面源码
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # 提取所有链接
    links = []
    link_elements = soup.select('a.HomesiteCard_link__CyDpK[href]')

    for link in link_elements:
        href = link.get('href')
        if href and href.startswith("/new-homes"):
            full_url = base_url + href
            links.append(full_url)

    # 去重
    unique_links = list(set(links))
    print(f"  找到 {len(unique_links)} 个唯一房源链接")
    return unique_links


# 从房源页面提取详细信息
def extract_property_data(url):
    headers = {
        'User-Agent': random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15"
        ])
    }

    try:
        # 添加随机延迟
        time.sleep(random.uniform(0.5, 2.0))

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 初始化字典
        data = {
            'date_scraped': datetime.now().strftime('%Y-%m-%d'),
            'builder': 'Lennar',
            'brand': 'Lennar',
            'community': '',
            'address': '',
            'city': '',
            'state': '',
            'zip': '',
            'plan_type': '',
            'plan': '',
            'floors': '',
            'bedrooms': '',
            'full_bathrooms': '',
            'half_bathrooms': '',
            'garage': '',
            'sqft': '',
            'price': '',
            'home_id': '',
            'status': '',
            'link': url
        }

        # 1. 提取州信息并大写
        url_parts = url.split('/')
        if len(url_parts) > 4:
            state_str = url_parts[4]
            data['state'] = state_str.capitalize()

        # 2. 提取社区信息
        community_element = soup.select_one('a[data-testid="sidebar-community-url"] span')
        if community_element:
            data['community'] = community_element.get_text(strip=True)

        # 3. 提取地址信息
        address_element = soup.select_one('.HomesiteDetailsInfoV2_supplementalAddressWrapper__k0gEc p:nth-of-type(2)')
        if address_element:
            address_text = address_element.get_text(strip=True)
            address_parts = [part.strip() for part in address_text.split(',')]
            if len(address_parts) >= 1:
                data['address'] = address_parts[0]
            if len(address_parts) >= 2:
                data['city'] = address_parts[1]
            # 提取可能的邮编（5位数字）
            zip_match = re.search(r'(\d{5})', address_text)
            if zip_match:
                data['zip'] = zip_match.group(1)

        # 4. 提取房屋特征
        features_element = soup.select_one('.HomesiteDetailsInfoV2_supplementalAddressWrapper__k0gEc p:nth-of-type(1)')
        if features_element:
            features_text = features_element.get_text(strip=True)

            # 提取卧室数量
            bedrooms_match = re.search(r'(\d+)\s*bd', features_text)
            if bedrooms_match:
                data['bedrooms'] = bedrooms_match.group(1)

            # 提取浴室信息
            full_bath_match = re.search(r'(\d+)\s*ba', features_text)
            if full_bath_match:
                data['full_bathrooms'] = full_bath_match.group(1)
            else:
                data['full_bathrooms'] = ''

            # 提取半浴室信息
            half_bath_match = re.search(r'(\d+)\s*half\s*ba', features_text)
            if half_bath_match:
                data['half_bathrooms'] = half_bath_match.group(1)
            else:
                data['half_bathrooms'] = ''

            # 提取车库信息
            garage_match = re.search(r'(\d+)\s*Car Garage', features_text)
            if garage_match:
                data['garage'] = garage_match.group(1)

            # 提取面积
            sqft_match = re.search(r'([\d,]+)\s*ft²', features_text)
            if sqft_match:
                data['sqft'] = sqft_match.group(1).replace(',', '')

        # 5. 提取价格
        price_element = soup.select_one('#sidebar-price')
        if price_element:
            price_text = price_element.get_text(strip=True).replace('$', '').replace(',', '')
            # 只保留数字
            price_match = re.search(r'(\d+)', price_text)
            if price_match:
                data['price'] = price_match.group(1)

        # 6. 提取房屋ID
        homesite_element = soup.find('p', string='Homesite')
        if homesite_element:
            home_id_element = homesite_element.find_next_sibling('p')
            if home_id_element:
                data['home_id'] = home_id_element.get_text(strip=True)

        # 7. 提取状态
        status_element = soup.select_one('#homesite-status')
        if status_element:
            data['status'] = status_element.get_text(strip=True)

        # 8. 提取户型计划
        plan_element = soup.select_one('.TextButton_textbutton__bkUsl span.textLinkLargeNew')
        if plan_element:
            plan_text = plan_element.get_text(strip=True)
            data['plan'] = plan_text

            # 提取plan_type
            if ' ' in plan_text:
                data['plan_type'] = plan_text.split()[0]
            else:
                data['plan_type'] = plan_text

        # 9. 提取楼层信息
        if data['plan'] and 'Story' in data['plan']:
            floors_match = re.search(r'(\d+)\s*Story', data['plan'])
            if floors_match:
                data['floors'] = floors_match.group(1)

        return data

    except Exception as e:
        print(f"  爬取房源页面 {url} 时出错: {str(e)}")
        return None


# 主函数
def main():
    # 设置CSV文件
    csv_filename = "lennar_all_homes.csv"
    fieldnames = [
        'date_scraped', 'builder', 'brand', 'community', 'address', 'city',
        'state', 'zip', 'plan_type', 'plan', 'floors', 'bedrooms',
        'full_bathrooms', 'half_bathrooms', 'garage', 'sqft', 'price',
        'home_id', 'status', 'link'
    ]

    file_exists = os.path.exists(csv_filename)

    # 打开CSV
    with open(csv_filename, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        # 遍历所有州和市场
        total_homes = 0
        for state_code, markets in STATE_MARKETS.items():
            print(f"\n{'=' * 50}")
            print(f"开始处理州: {state_code}")
            print(f"{'=' * 50}")

            for market in markets:
                print(f"\n{'=' * 50}")
                print(f"开始处理市场: {state_code}/{market}")
                print(f"{'=' * 50}")

                # 为每个市场创建新的WebDriver实例
                driver = None
                retry_count = 0
                max_retries = 3
                links = []

                while retry_count < max_retries and not links:
                    try:
                        # 创建新的WebDriver实例
                        driver = setup_driver()
                        links = get_links_for_market(driver, state_code, market)
                    except Exception as e:
                        print(f"  获取链接失败: {str(e)}，重试 {retry_count + 1}/{max_retries}")
                        retry_count += 1
                        # 关闭失败的driver
                        if driver:
                            try:
                                driver.quit()
                            except:
                                pass
                        time.sleep(10)
                    finally:
                        # 确保driver被关闭
                        if driver:
                            try:
                                driver.quit()
                            except:
                                pass

                if not links:
                    print(f"  无法获取市场 {state_code}/{market} 的房源链接，跳过")
                    continue

                # 处理每个房源
                for i, link in enumerate(links, 1):
                    print(f"  [{i}/{len(links)}] 爬取房源: {link}")

                    time.sleep(random.uniform(0.5, 2.0))

                    property_data = extract_property_data(link)

                    if property_data:
                        writer.writerow(property_data)
                        csvfile.flush()  # 立即写入磁盘
                        total_homes += 1
                    else:
                        print(f"  房源爬取失败: {link}")

                # 市场处理完成
                print(f"\n市场 {state_code}/{market} 处理完成，共爬取 {len(links)} 个房源")

        # 所有市场处理完成
        print(f"\n{'=' * 50}")
        print(f"所有市场处理完成！共爬取 {total_homes} 个房源")
        print(f"数据已保存到: {csv_filename}")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    main()