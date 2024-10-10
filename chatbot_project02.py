from flask import Flask, request, jsonify
from linebot import LineBotApi
from linebot.models import FlexSendMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
import requests
from bs4 import BeautifulSoup
import json
from selenium import webdriver
import time
import chromedriver_autoinstaller
from neo4j import GraphDatabase  # เพิ่มการเชื่อมต่อกับ Neo4j
from datetime import datetime
from sentence_transformers import SentenceTransformer
import chromedriver_autoinstaller
import faiss
import numpy as np

app = Flask(__name__)

# Initialize LineBotApi with your channel access token
line_bot_api = LineBotApi('+9efv6+iMkcvyQcaxPnb5EcvazdJlWBUAzIQaNCPJrZzBIPKGlRcET6nlnxUVJkjD7B9/XYvvrDkV/3vX5onOStkuj+ICKByGLIGcsHlyMHAby06fpvVVQhpDVIiYjR85eW4jQ5Qw56z//HQwvdpVwdB04t89/1O/w1cDnyilFU=')

# ตั้งค่า Neo4j
URI = "neo4j://localhost:7687"
AUTH = ("neo4j", "poramest")  # เปลี่ยนเป็นรหัสผ่านจริงของคุณ


# ฟังก์ชันบันทึกข้อความผู้ใช้และคำตอบจากบอทลงใน Neo4j
def store_chat_history_in_neo4j(user_id, user_message, bot_response):
    query = '''
    MERGE (u:User {user_id: $user_id})
    CREATE (m:Message {text: $user_message, timestamp: $timestamp})
    CREATE (r:Response {text: $bot_response, timestamp: $timestamp})
    MERGE (u)-[:SENT]->(m)-[:REPLIED]->(r)
    '''
    parameters = {
        'user_id': user_id,
        'user_message': user_message,
        'bot_response': bot_response,
        'timestamp': datetime.now().isoformat()  # บันทึกเวลาที่ผู้ใช้โต้ตอบ
    }

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session() as session:
            session.run(query, parameters)

encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def create_faiss_index(phrases):
    vectors = encoder.encode(phrases)
    vector_dimension = vectors.shape[1]
    index = faiss.IndexFlatL2(vector_dimension)
    faiss.normalize_L2(vectors)
    index.add(vectors)
    return index, vectors

intent_phrases = [
    "สวัสดี",
    "สอบถาม",
    "สอบถามเพิ่มเติม",
    "ขอบคุณ",
    "จบการสนทนา",
    "สมาร์ทวอทช์",
    "amazfit", 
    "garmin", 
    "huawei", 
    "samsung", 
    "xiaomi",
    "เลือกสี",
    "เลือกช่วงราคา",
    "black"
    "cream white"
    "lava black",
    "lavender purple",
    "midnight black",
    "mint green",
    "ocean blue",
    "น้อยกว่า 3000"
    "3001-6000",
    "6001-9000",
    "9001-12000",
    "มากกว่า 12001",
    "สอบถามข้อมูล",
    "สอบถามแบรนด์",
    "ยี่ห้อ",
    "สมาร์ทวอทช์",
    "smartwatch",
    "สนใจสินค้า",
]
index, vectors = create_faiss_index(intent_phrases)

def faiss_search(sentence):
    search_vector = encoder.encode(sentence)
    _vector = np.array([search_vector])
    faiss.normalize_L2(_vector)
    distances, ann = index.search(_vector, k=1)

    distance_threshold = 0.5
    if distances[0][0] > distance_threshold:
        return 'unknown'
    else:
        return intent_phrases[ann[0][0]]
def scrape_product_page(url):
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # Run in headless mode (no browser UI)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    chromedriver_autoinstaller.install()

    driver = webdriver.Chrome(options=options)
    products = []

    print(f"Fetching URL: {url}")  # เพิ่มการพิมพ์ URL ที่กำลังดึงข้อมูล

    driver.get(url)
    time.sleep(5)  # Allow time for the page to fully load
    
    # Create BeautifulSoup object to parse HTML
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    base_url = "https://www.bnn.in.th"
    
    # Find all product elements
    product_tags = soup.find_all('a', class_='product-link verify product-item')
    print(f"Number of products found: {len(product_tags)}")  # ตรวจสอบว่าพบกี่ product

    for tag in product_tags:
        name_tag = tag.find("div", class_="product-name")
        price_tag = tag.find("div", class_="product-price")
        image_tag = tag.find("img", class_="image")
        image_url = image_tag['src'] if image_tag else None  # ตรวจสอบว่าพบ image หรือไม่
        tag_url = base_url + tag['href']

        if name_tag and price_tag:
            products.append({
                'title': name_tag.get_text(strip=True),  # Extract product title
                'price': price_tag.get_text(strip=True),   # Extract product price
                'image_url': image_url,  # URL ของรูปภาพ
                'url': tag_url  # Include the product URL
            })
            print(f"Product found: {name_tag.get_text(strip=True)}, Price: {price_tag.get_text(strip=True)}, Image: {image_url}")

    driver.quit()
    return products


# Function to send Flex Message with product details
def send_flex_message(reply_token, products):
    if not products:
        print("No products found, sending no product message.")
        text_message = TextSendMessage(text="ไม่พบสินค้า")
        line_bot_api.reply_message(reply_token, text_message)
        return

    bubbles = []
    for prod in products[:12]:
        print(f"Product to be displayed: {prod['title']} with price {prod['price']} and image URL {prod['image_url']}")
        bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": prod['image_url'],
                "size": "full",
                "aspectRatio": "1:1",
                "aspectMode": "cover",
                "action": {
                    "type": "uri",
                    "uri": prod['url']
                }
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": prod['title'], "weight": "bold", "size": "md", "wrap": True},
                    {"type": "text", "text": f"Price: {prod['price']}", "size": "sm", "color": "#999999"}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "link",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "ดูสินค้า",
                            "uri": prod['url']
                        },
                        "color": "#000000"  # สีของข้อความในปุ่ม (เลือกสีที่ตัดกับพื้นหลัง)
                    }
                ],
                "backgroundColor": "#99FFCC"  # สีพื้นหลังของปุ่ม
            }
        }
        bubbles.append(bubble)

    contents = {"type": "carousel", "contents": bubbles}
    flex_message = FlexSendMessage(alt_text="รายการสินค้า", contents=contents)

    quick_reply_message = TextSendMessage(
        text="ขอบคุณที่ใช้บริการ ต้องการสอบถามเพิ่มเติมไหม",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="สวัสดี", text="สวัสดี")),
            QuickReplyButton(action=MessageAction(label="สอบถามเพิ่มเติม", text="สอบถามเพิ่มเติม")),
            QuickReplyButton(action=MessageAction(label="ขอบคุณ", text="ขอบคุณ")),
            QuickReplyButton(action=MessageAction(label="จบการสนทนา", text="จบการสนทนา"))
        ])
    )

    try:
        line_bot_api.reply_message(
            reply_token,
            messages=[flex_message, quick_reply_message]
        )
    except Exception as e:
        print(f"Error sending Flex Message: {e}")


# Variable to keep track of selected brand globally
selected_brand = None  # Declare it as a global variable

@app.route("/", methods=['POST'])
def linebot():
    global selected_brand  # Declare global to modify its value
    body = request.get_data(as_text=True)
    try:
        json_data = json.loads(body)
        reply_token = json_data['events'][0]['replyToken']
        msg = json_data['events'][0]['message']['text'].lower()
        user_id = json_data['events'][0]['source']['userId']  # ดึง user_id จากข้อมูล
        user_message = json_data['events'][0]['message']['text']  # ข้อความจากผู้ใช้

        msg = faiss_search(msg)

        if msg in ["สวัสดี","ดีจ้า","สวัสดีครับ","สวัสดีค่า","สวัสดีค่ะ","สวัสดีจ้า","หวัดดี","หวัดดีจ้า","หวัดดีครับ","Hi","Hello","hi","hello"]:
            bot_response = "สวัสดีครับ ฉันชื่อ S-Watch Bot ยินดีให้บริการ สนใจสินค้าสามารถสอบถามได้ครับ"
            line_bot_api.reply_message(reply_token, TextSendMessage(
                text=bot_response,
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="สอบถาม", text="สอบถาม")),
                    QuickReplyButton(action=MessageAction(label="สมาร์ทวอทช์", text="สมาร์ทวอทช์")),
                ])
            ))
            # บันทึกประวัติการสนทนาใน Neo4j
            store_chat_history_in_neo4j(user_id, user_message, bot_response)
            return 'OK'

        # Check for greeting
        if msg in ["สอบถาม","สอบถามเพิ่มเติม","สอบถามข้อมูล","สอบถามแบรนด์","สมาร์ทวอทช์","Smartwatch","smartwatch","สนใจสินค้า","สนใจ","สินค้า"]:
            bot_response = "มีแบนด์ Smartwatch แนะนำ"
            line_bot_api.reply_message(reply_token, TextSendMessage(
                text=bot_response,
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="amazfit", text="amazfit")),
                    QuickReplyButton(action=MessageAction(label="garmin", text="garmin")),
                    QuickReplyButton(action=MessageAction(label="huawei", text="huawei")),
                    QuickReplyButton(action=MessageAction(label="samsung", text="samsung")),
                    QuickReplyButton(action=MessageAction(label="xiaomi", text="xiaomi"))
                ])
            ))
            # บันทึกประวัติการสนทนาใน Neo4j
            store_chat_history_in_neo4j(user_id, user_message, bot_response)
            return 'OK'

        # Handle brand selection
        if msg in ["amazfit", "garmin", "huawei", "samsung", "xiaomi"]:
            selected_brand = msg  # Track the selected brand globally
            bot_response = "กรุณาเลือกสินค้าตามสีหรือช่วงราคา"
            line_bot_api.reply_message(reply_token, TextSendMessage(
                text=bot_response,
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="เลือกสี", text="เลือกสี")),
                    QuickReplyButton(action=MessageAction(label="เลือกช่วงราคา", text="เลือกช่วงราคา"))
                ])
            ))
            # บันทึกประวัติการสนทนาใน Neo4j
            store_chat_history_in_neo4j(user_id, user_message, bot_response)
            return 'OK'

        # Handle color filter
        if msg == "เลือกสี":
            bot_response = "กรุณาเลือกสีที่ต้องการ"
            line_bot_api.reply_message(reply_token, TextSendMessage(
                text=bot_response,
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="Lava Black", text="Lava Black")),
                    QuickReplyButton(action=MessageAction(label="Lavender Purple", text="Lavender Purple")),
                    QuickReplyButton(action=MessageAction(label="Midnight Black", text="Midnight Black")),
                    QuickReplyButton(action=MessageAction(label="Mint Green", text="Mint Green")),
                    QuickReplyButton(action=MessageAction(label="Ocean Blue", text="Ocean Blue"))
                ])
            ))
            # บันทึกประวัติการสนทนาใน Neo4j
            store_chat_history_in_neo4j(user_id, user_message, bot_response)
            return 'OK'

        # Handle price filter
        if msg == "เลือกช่วงราคา":
            bot_response = "กรุณาเลือกช่วงราคาที่ต้องการ"
            line_bot_api.reply_message(reply_token, TextSendMessage(
                text=bot_response,
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="น้อยกว่า 3000", text="0-3000")),
                    QuickReplyButton(action=MessageAction(label="3001-6000", text="3001-6000")),
                    QuickReplyButton(action=MessageAction(label="6001-9000", text="6001-9000")),
                    QuickReplyButton(action=MessageAction(label="9001-12000", text="9001-12000")),
                    QuickReplyButton(action=MessageAction(label="มากกว่า 12001", text="12001-50000"))
                ])
            ))
            # บันทึกประวัติการสนทนาใน Neo4j
            store_chat_history_in_neo4j(user_id, user_message, bot_response)
            return 'OK'

        # Handle specific color selection
        # Mapping of colors to URL attributes
        # Mapping of colors to URL attributes
        color_map = {
            "lava black": "color%3Alava-black",
            "lavender purple": "color%3Alavender-purple",
            "midnight black": "color%3Amidnight-black",
            "mint green": "color%3Amint-green",
            "ocean blue": "color%3Aocean-blue",
        }

        # Handle specific color selection
        if msg.lower() in color_map and selected_brand:
            # Build the URL with the selected brand and color
            base_url = f"https://www.bnn.in.th/th/p/sport-health-and-gadgets/smartwatch/{selected_brand}-smartwatch"
            color_param = color_map[msg.lower()]  # Get the color parameter for the URL
            color_url = f"{base_url}?in_stock=false&sort_by=relevance&page=1&attributes={color_param}"
            print(f"Generated URL for color: {color_url}")  # For debugging purposes

            # Scrape products based on color
            products = scrape_product_page(color_url)

            if products:
                bot_response = "รายการสินค้าที่ค้นพบ"
                send_flex_message(reply_token, products)  # Send Flex message with the products
                store_chat_history_in_neo4j(user_id, user_message, bot_response)
            else:
                bot_response = "ไม่พบสินค้าที่มีสีที่เลือก"
                line_bot_api.reply_message(reply_token, TextSendMessage(text=bot_response))
                store_chat_history_in_neo4j(user_id, user_message, bot_response)

            return 'OK'



        # Handle specific price range selection
        if "-" in msg:
            min_price, max_price = map(int, msg.split('-'))

            # Build the URL with the selected brand and price range (no color)
            base_url = f"https://www.bnn.in.th/th/p/sport-health-and-gadgets/smartwatch/{selected_brand}-smartwatch"
            price_url = f"{base_url}?in_stock=false&sort_by=relevance&page=1&min_price={min_price}&max_price={max_price}"

            # Scrape products based on price range
            products = scrape_product_page(price_url)

            if products:
                bot_response = "รายการสินค้าที่ค้นพบ"
                send_flex_message(reply_token, products)  # Send Flex message with the products
                store_chat_history_in_neo4j(user_id, user_message, bot_response)
            else:
                bot_response = "ไม่พบสินค้าที่มีช่วงราคาที่เลือก"
                line_bot_api.reply_message(reply_token, TextSendMessage(text=bot_response))
                store_chat_history_in_neo4j(user_id, user_message, bot_response)

            return 'OK'
        
        if msg in ["ขอบคุณ","ขอบคุณมาก","ขอบคุณครับ","ขอบคุณค่ะ","ขอบคุณค่า","ขอบคุณจ้า","จบการสนทนา"]:
            bot_response = "ขอบคุณที่ใช้บริการ หวังว่าจะได้ช่วยคุณอีกในครั้งถัดไปครับ สวัสดีครับ"
            line_bot_api.reply_message(reply_token, TextSendMessage(text=bot_response))
            store_chat_history_in_neo4j(user_id, user_message, bot_response)

        # Default case
        bot_response = "ขออภัย เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง"
        line_bot_api.reply_message(reply_token, TextSendMessage(text=bot_response))
        store_chat_history_in_neo4j(user_id, user_message, bot_response)

    except Exception as e:
        print(f"Error processing the LINE event: {e}")
        line_bot_api.reply_message(reply_token, TextSendMessage(text="ขออภัย เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่อีกครั้ง"))

    return 'OK'

if __name__ == '__main__':
    app.run(port=5000, debug=True)
