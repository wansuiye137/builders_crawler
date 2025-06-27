from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import csv
import re
import datetime
import os
from urllib.parse import urljoin
import sys
import time
import traceback
import signal  # 用于处理中断信号
import errno
import random

# 州列表
ALL_STATES = [
    'Arizona', 'California', 'Colorado', 'Connecticut', 'Delaware', 'Florida',
    'Georgia', 'Idaho', 'Maryland', 'Massachusetts', 'Michigan', 'Nevada',
    'New Jersey', 'New York', 'North Carolina', 'Oregon', 'Pennsylvania',
    'South Carolina', 'Tennessee', 'Texas', 'Utah', 'Virginia', 'Washington'
]

# 错误收集
global_errors = []
global_csv_file = None

# 信号处理
def signal_handler(sig, frame):
    print("\n\n用户中断程序...")
    print_global_errors()
    if global_csv_file and not global_csv_file.closed:
        global_csv_file.close()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def print_global_errors():
    """打印全局错误报告"""
    if global_errors:
        print(f"\n{'!' * 80}")
        print(f"错误汇总 ({len(global_errors)} 个错误):")
        print(f"{'!' * 80}")
        for error in global_errors:
            print(f"类型: {error['type']}")
            print(f"URL: {error['url']}")
            print(f"错误: {error['error']}")
            print("-" * 80)
    else:
        print("\n没有发现错误！")


def extract_community_urls(state_url):
    """从州页面提取所有社区URL"""
    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print(f"正在访问州页面: {state_url}")
        try:
            # 导航到目标URL
            page.goto(state_url, timeout=120000)
            page.wait_for_load_state("domcontentloaded", timeout=60000)

            # 确保社区区块加载完成
            print("等待社区卡片加载...")
            page.wait_for_selector('.MetroBlock_metroBlock__lkPmw', timeout=60000)

            # 获取页面内容
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # 查找所有社区卡片容器
            metro_blocks = soup.select('.MetroBlock_metroBlock__lkPmw')

            if not metro_blocks:
                print("⚠️ 未找到社区区块，请检查页面结构或选择器")
                return []

            # 提取所有社区链接
            community_urls = []
            for block in metro_blocks:
                # 在区块内查找所有"View Master Plan"按钮
                view_buttons = block.select('a.SearchProductCard_view__nYL3F')
                for button in view_buttons:
                    href = button.get('href')
                    if href:
                        # 构建完整URL
                        full_url = urljoin(state_url, href)
                        community_urls.append(full_url)

            # 去重
            unique_urls = list(set(community_urls))
            print(f"提取到 {len(unique_urls)} 个社区链接")

            return unique_urls

        except Exception as e:
            print(f"❌ 提取社区URL时出错: {str(e)}")
            traceback.print_exc()
            global_errors.append({
                "type": "州页面",
                "url": state_url,
                "error": f"提取社区URL失败: {str(e)}"
            })
            return []
        finally:
            # 关闭浏览器
            try:
                context.close()
            except:
                pass
            try:
                browser.close()
            except:
                pass


def extract_tollbrothers_data(url, max_retries=3):
    retry_count = 0
    while retry_count < max_retries:
        with sync_playwright() as p:
            # 启动浏览器
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()

            # 设置更长的默认超时
            context.set_default_timeout(120000)

            page = context.new_page()

            try:
                print(f"正在访问房源页面: {url}")

                # 导航到目标URL
                response = page.goto(url, timeout=120000, wait_until="domcontentloaded")

                # 检查响应状态
                if response and response.status >= 400:
                    print(f"⚠️ 页面响应错误: HTTP {response.status} - {url}")
                    retry_count += 1
                    time.sleep(3)
                    continue

                # 检查是否重定向
                if page.url != url:
                    print(f"⚠️ 页面重定向到: {page.url} (原始: {url})")

                try:
                    # 等待地址信息块
                    page.wait_for_selector('aside[class*="CommunityHero_heroDetails"]', timeout=60000)
                    # 等待价格元素
                    page.wait_for_selector('span.price', timeout=30000, state="attached")
                    # 等待户型信息
                    page.wait_for_selector('div[class*="CommunityStatBar_statBox"]', timeout=30000)
                except Exception as e:
                    print(f"⚠️ 等待元素警告: {str(e)} - 继续提取可能不完整的数据")

                # 获取页面内容
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')

                # 提取基础信息
                url_parts = url.split('/')
                state = url_parts[4] if len(url_parts) > 4 else ""
                community = url_parts[5] if len(url_parts) > 5 else ""

                # 提取home_id和status(分类)
                if "Quick-Move-In" in url_parts:
                    # Quick-Move-In类型URL
                    status = "Quick Move In"
                    home_id = url_parts[-1]  # 最后部分是数字ID
                else:
                    # Home Design类型URL
                    status = "Home Design"
                    home_id = url_parts[-1]  # 最后部分是设计名称

                # 当前日期
                date_scraped = datetime.datetime.now().strftime('%Y-%m-%d')

                # 提取地址信息
                address_block = soup.select_one('aside[class*="CommunityHero_heroDetails"]')
                address = ""
                if address_block:
                    # 提取地址文本并清理
                    address_text = address_block.get_text(strip=True)
                    # 移除管道符号后的县名部分
                    if '|' in address_text:
                        address = address_text.split('|')[0].strip()

                # 城市和邮编
                city = ""
                zip_code = ""

                # 查找所有销售团队信息标签
                sales_team_tags = soup.select('p.CommunityContactBar_nameSalesTeam__bKVor')
                for tag in sales_team_tags:
                    text = tag.get_text(strip=True)
                    city_match = re.search(r'^([^,]+),', text)
                    if city_match:
                        city = city_match.group(1).strip()

                    # 提取邮编（5位数字）
                    zip_match = re.search(r'\d{5}', text)
                    if zip_match:
                        zip_code = zip_match.group()

                # 提取价格
                price_element = soup.select_one('span.price')
                price = price_element.get_text(strip=True).replace('$', '').replace(',', '') if price_element else ""

                # 提取房屋类型
                plan_type_element = soup.select_one('ul li span')
                plan_type = plan_type_element.get_text(strip=True) if plan_type_element else ""

                # 提取户型信息
                stats_section = soup.select('div[class*="CommunityStatBar_statBox"]')
                bedrooms = ""
                full_bathrooms = ""
                half_bathrooms = ""
                garage = ""
                sqft = ""
                floors = ""

                for stat in stats_section:
                    title = stat.select_one('p[class*="CommunityStatBar_statTitle"]')
                    if not title:
                        continue

                    value = stat.select_one('p[class*="CommunityStatBar_statNumber"]').get_text(
                        strip=True) if stat.select_one(
                        'p[class*="CommunityStatBar_statNumber"]') else ""

                    if "Bedrooms" in title.get_text():
                        bedrooms = value
                    elif "Bathrooms" in title.get_text():
                        full_bathrooms = value
                    elif "Half Baths" in title.get_text():
                        half_bathrooms = value
                    elif "Garages" in title.get_text():
                        garage = value
                    elif "Square Footage" in title.get_text():
                        sqft = value.replace(',', '')
                    elif "Stories" in title.get_text():
                        floors = value

                # 返回结构化数据
                return {
                    "date_scraped": date_scraped,
                    "builder": "Toll Brothers",
                    "brand": "Toll Brothers",
                    "community": community.replace('-', ' '),
                    "address": address,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                    "plan_type": plan_type,
                    "plan": plan_type,  # 根据需求使用相同值
                    "floors": floors,
                    "bedrooms": bedrooms,
                    "full_bathrooms": full_bathrooms,
                    "half_bathrooms": half_bathrooms,
                    "garage": garage,
                    "sqft": sqft,
                    "price": price,
                    "home_id": home_id,
                    "status": status,
                    "link": url
                }

            except TimeoutError:
                retry_count += 1
                print(f"⏱️ 超时重试 ({retry_count}/{max_retries}): {url}")
                time.sleep(5)  # 重试前等待
            except Exception as e:
                print(f"❌ 提取房源数据时出错: {str(e)}")
                traceback.print_exc()
                global_errors.append({
                    "type": "房源",
                    "url": url,
                    "error": f"提取数据失败: {str(e)}"
                })
                return None
            finally:
                # 安全关闭浏览器
                try:
                    context.close()
                except:
                    pass
                try:
                    browser.close()
                except:
                    pass

    print(f"❌ 达到最大重试次数仍失败: {url}")
    global_errors.append({
        "type": "房源",
        "url": url,
        "error": "达到最大重试次数仍失败"
    })
    return None


def extract_property_urls(community_url):
    """从社区页面提取所有房源URL"""
    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            # 导航到目标URL
            page.goto(community_url, timeout=120000)
            page.wait_for_load_state("domcontentloaded", timeout=60000)

            # 确保房源卡片加载完成
            print("等待房源卡片加载...")
            page.wait_for_selector('.ModelCard_modelCardContainer__lXz5R', timeout=60000)

            # 获取页面内容
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # 查找所有房源卡片容器
            card_containers = soup.select('.ModelCard_modelCardContainer__lXz5R')

            if not card_containers:
                print("⚠️ 未找到房源卡片，请检查页面结构或选择器")
                return []

            print(f"找到 {len(card_containers)} 个房源卡片")

            # 提取所有房源链接
            property_urls = []
            for container in card_containers:
                link_element = container.find('a')
                if link_element and link_element.get('href'):
                    # 构建完整URL
                    full_url = urljoin(community_url, link_element['href'])
                    property_urls.append(full_url)

            # 去重
            unique_urls = list(set(property_urls))
            print(f"提取到 {len(unique_urls)} 个唯一房源链接")

            return unique_urls

        except Exception as e:
            print(f"❌ 提取房源URL时出错: {str(e)}")
            traceback.print_exc()
            global_errors.append({
                "type": "社区",
                "url": community_url,
                "error": f"提取房源URL失败: {str(e)}"
            })
            return []
        finally:
            # 关闭浏览器
            try:
                context.close()
            except:
                pass
            try:
                browser.close()
            except:
                pass


def save_to_csv(data, filename="tollbrothers_homes.csv"):
    """安全保存数据到CSV，处理文件锁定问题"""
    global global_csv_file

    if not data:
        return

    max_retries = 5
    retry_delay = 3  # 秒

    for attempt in range(max_retries):
        try:
            # 检查文件是否存在
            file_exists = os.path.isfile(filename)

            # 打开文件并获取锁
            with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
                global_csv_file = csvfile  # 保存文件引用

                # 写入数据
                fieldnames = [
                    "date_scraped", "builder", "brand", "community", "address", "city",
                    "state", "zip", "plan_type", "plan", "floors", "bedrooms",
                    "full_bathrooms", "half_bathrooms", "garage", "sqft", "price",
                    "home_id", "status", "link"
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                if not file_exists:
                    writer.writeheader()

                writer.writerow(data)


        except PermissionError:
            if attempt < max_retries - 1:
                print(f"文件访问被拒绝，等待 {retry_delay} 秒后重试... (尝试 {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                print(f"❌ 无法写入文件，已达到最大重试次数")
                return
        except Exception as e:
            print(f"❌ 写入CSV文件时出错: {str(e)}")
            traceback.print_exc()
            return


def print_progress(current, total, prefix=""):
    """在状态栏显示进度"""
    progress = int(current / total * 50)
    bar = '[' + '=' * progress + ' ' * (50 - progress) + ']'
    percent = int(current / total * 100)
    sys.stdout.write(f"\r{prefix}{bar} {percent}% ({current}/{total})")
    sys.stdout.flush()


def scrape_community(community_url, csv_filename):
    """爬取整个社区的所有房源信息"""
    print(f"\n开始爬取社区: {community_url}")

    try:
        # 获取所有房源链接
        property_urls = extract_property_urls(community_url)

        if not property_urls:
            print("❌ 未提取到任何房源URL，请检查输入或网站结构")
            global_errors.append({
                "type": "社区",
                "url": community_url,
                "error": "未找到房源卡片"
            })
            return 0  # 返回0表示没有房源

        print(f"找到 {len(property_urls)} 个房源")

        # 爬取每个房源
        success_count = 0
        for i, url in enumerate(property_urls, 1):
            try:
                print_progress(i, len(property_urls), f"房源爬取进度: ")
                property_data = extract_tollbrothers_data(url)
                if property_data:
                    save_to_csv(property_data, csv_filename)
                    success_count += 1
            except Exception as e:
                print(f"\n❌ 处理房源 {url} 时出错: {str(e)}")
                traceback.print_exc()
                global_errors.append({
                    "type": "房源",
                    "url": url,
                    "error": str(e)
                })

        print(f"\n社区爬取完成: 成功提取 {success_count}/{len(property_urls)} 个房源")
        return success_count

    except Exception as e:
        print(f"\n❌ 爬取社区时发生严重错误: {str(e)}")
        traceback.print_exc()
        global_errors.append({
            "type": "社区",
            "url": community_url,
            "error": str(e)
        })
        return 0


def scrape_state(state, csv_filename):
    """爬取整个州的所有房源信息"""
    state_url = f"https://www.tollbrothers.com/luxury-homes/{state}"
    print(f"\n{'=' * 80}")
    print(f"开始爬取州: {state}")
    print(f"州URL: {state_url}")
    print(f"{'=' * 80}")

    try:
        # 提取所有社区URL
        community_urls = extract_community_urls(state_url)

        if not community_urls:
            print("❌ 未提取到任何社区URL，请检查输入或网站结构")
            global_errors.append({
                "type": "州",
                "url": state_url,
                "error": "未找到社区卡片"
            })
            return 0, 0, 0

        print(f"找到 {len(community_urls)} 个社区")

        # 爬取每个社区
        total_communities = len(community_urls)
        total_homes = 0
        total_success = 0
        start_time = time.time()

        for i, community_url in enumerate(community_urls, 1):
            print(f"\n{'=' * 80}")
            print(f"社区进度 ({i}/{total_communities}): {community_url}")
            print(f"{'=' * 80}")

            # 爬取当前社区
            homes_in_community = extract_property_urls(community_url) or []
            total_homes += len(homes_in_community)
            success_count = scrape_community(community_url, csv_filename)
            total_success += success_count

            # 显示当前社区完成状态
            print(f"社区完成: {community_url}")
            print(f"当前社区成功提取: {success_count}/{len(homes_in_community)} 个房源")
            print(f"累计成功提取: {total_success}/{total_homes} 个房源")

            # 随机延迟，避免请求过于频繁
            time.sleep(random.uniform(1, 3))

        elapsed = time.time() - start_time
        print(f"\n{'=' * 80}")
        print(f"州爬取完成: {state}")
        print(f"总社区数: {total_communities}")
        print(f"总房源数: {total_homes}")
        print(f"成功提取房源数: {total_success}")
        print(f"耗时: {elapsed:.2f}秒")
        print(f"{'=' * 80}")

        return total_communities, total_homes, total_success

    except Exception as e:
        print(f"\n❌ 爬取州时发生严重错误: {str(e)}")
        traceback.print_exc()
        global_errors.append({
            "type": "州",
            "url": state_url,
            "error": str(e)
        })
        return 0, 0, 0


def scrape_all_states(csv_filename="tollbrothers_all_homes.csv"):
    """爬取所有州的数据"""
    # 备份已存在的CSV文件
    if os.path.exists(csv_filename):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"tollbrothers_backup_{timestamp}.csv"
        os.rename(csv_filename, backup_name)
        print(f"已备份旧文件为: {backup_name}")

    # 初始化统计信息
    total_states = len(ALL_STATES)
    total_communities = 0
    total_homes = 0
    total_success = 0
    overall_start = time.time()

    # 创建CSV文件并写入表头
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            "date_scraped", "builder", "brand", "community", "address", "city",
            "state", "zip", "plan_type", "plan", "floors", "bedrooms",
            "full_bathrooms", "half_bathrooms", "garage", "sqft", "price",
            "home_id", "status", "link"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

    # 遍历所有州
    for i, state in enumerate(ALL_STATES, 1):
        print(f"\n\n{'#' * 80}")
        print(f"开始处理州 ({i}/{total_states}): {state}")
        print(f"{'#' * 80}")

        # 爬取当前州
        communities, homes, success = scrape_state(state, csv_filename)
        total_communities += communities
        total_homes += homes
        total_success += success

        # 显示当前州完成状态
        print(f"\n州完成: {state}")
        print(f"当前州成功提取: {success}/{homes} 个房源")
        print(f"累计成功提取: {total_success}/{total_homes} 个房源")

        # 州之间暂停，避免请求过于频繁
        time.sleep(random.uniform(3, 7))

    # 计算总耗时
    overall_elapsed = time.time() - overall_start

    # 显示最终报告
    print(f"\n{'=' * 80}")
    print(f"爬取完成!")
    print(f"总州数: {total_states}")
    print(f"总社区数: {total_communities}")
    print(f"总房源数: {total_homes}")
    print(f"成功提取房源数: {total_success}")
    print(f"总耗时: {overall_elapsed:.2f}秒")
    print(f"所有数据已保存到 {csv_filename}")
    print(f"{'=' * 80}")

    # 打印错误报告
    print_global_errors()


def main():
    print(f"{'=' * 80}")
    print(f"开始爬取 Toll Brothers 网站数据")
    print(f"日期: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}")

    try:
        # CSV文件名
        output_csv = "tollbrothers_all_homes.csv"

        # 爬取所有州
        scrape_all_states(output_csv)

        print(f"\n{'=' * 80}")
        print(f"爬取任务完成!")
        print(f"最终数据文件: {output_csv}")
        print(f"{'=' * 80}")

    except Exception as e:
        print(f"\n❌ 主程序发生未预期错误: {str(e)}")
        traceback.print_exc()
    finally:
        # 确保打印所有错误
        print_global_errors()


if __name__ == "__main__":
    main()